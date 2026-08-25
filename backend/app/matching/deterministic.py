"""Deterministic matching components: skills, experience, education.

Layer 1 (AI_ARCHITECTURE.md section 1) - exact/alias keyword matching and threshold comparison,
no embeddings needed. These four components are always available; the semantic ones in
``app.matching.semantic`` are not.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import date

from app.analysis.models import ComponentScore, Evidence, EvidenceSeverity
from app.analysis.scoring_utils import clamp_score
from app.analysis.taxonomy import contains_skill_mention
from app.analysis.text_metrics import bullets_of
from app.jobs.education import classify_education_level, education_level_rank
from app.jobs.models import (
    EducationLevel,
    JobDescription,
    Requirement,
    RequirementImportance,
    RequirementKind,
)
from app.resume.models import Resume

_YEAR_MONTH_RE = re.compile(r"^(\d{4})(?:-(\d{2}))?$")


def _year_month_to_float(value: str) -> float | None:
    match = _YEAR_MONTH_RE.match(value)
    if not match:
        return None
    year = int(match.group(1))
    month = int(match.group(2)) if match.group(2) else 6  # bare year: assume mid-year
    return year + (month - 1) / 12


def total_years_experience(resume: Resume, today: date | None = None) -> float:
    """Sum of each role's duration, in years.

    A standard, defensible proxy - it does not detect overlapping roles (which would double
    count) or unexplained gaps (which it does not penalise). Both are acceptable simplifications
    for a deterministic first pass; documented rather than silently assumed precise.
    """
    reference = today or date.today()
    now_float = reference.year + (reference.month - 1) / 12
    total = 0.0
    for entry in resume.experience:
        dates = entry.value.dates
        if dates is None or dates.start is None:
            continue
        start = _year_month_to_float(dates.start)
        if start is None:
            continue
        end: float | None
        if dates.is_current or dates.end is None:
            end = now_float
        else:
            end = _year_month_to_float(dates.end)
        if end is None:
            end = now_float
        total += max(0.0, end - start)
    return total


def highest_education_level(resume: Resume) -> EducationLevel:
    best = EducationLevel.NONE
    for entry in resume.education:
        for field in (entry.value.degree, entry.value.field_of_study):
            if not field:
                continue
            level = classify_education_level(field)
            if level is not None and education_level_rank(level) > education_level_rank(best):
                best = level
    return best


def _resume_matchable_text(resume: Resume) -> str:
    parts: list[str] = [s for group in resume.skills for s in group.value.skills]
    parts.extend(bullets_of(resume))
    return " ".join(parts)


@dataclass(slots=True)
class _Check:
    requirement: Requirement
    matched: bool | None  # None = no recognised keyword, so it could not be automatically checked


def _check_requirements(requirements: list[Requirement], resume_text: str) -> list[_Check]:
    checks = []
    for requirement in requirements:
        if not requirement.keywords:
            checks.append(_Check(requirement, None))
            continue
        matched = any(contains_skill_mention(resume_text, kw) for kw in requirement.keywords)
        checks.append(_Check(requirement, matched))
    return checks


def _score_skill_requirements(
    requirements: list[Requirement], resume_text: str, key: str, label: str, weight: float
) -> ComponentScore:
    explanation = (
        f"Compares each {label.lower()} requirement against the resume's skills section and "
        "experience bullets. A requirement using a term outside the recognised skill list is "
        "flagged as unverifiable rather than guessed at."
    )
    if not requirements:
        return ComponentScore(
            key=key,
            label=label,
            score=100.0,
            weight=weight,
            evidence=[
                Evidence(
                    message=f"The job description lists no {label.lower()} requirements.",
                    severity=EvidenceSeverity.INFO,
                )
            ],
            explanation=explanation,
        )

    checks = _check_requirements(requirements, resume_text)
    checkable = [c for c in checks if c.matched is not None]
    evidence: list[Evidence] = []

    if not checkable:
        return ComponentScore(
            key=key,
            label=label,
            score=50.0,
            weight=weight,
            evidence=[
                Evidence(
                    message="None of these requirements matched a recognised skill keyword, so "
                    "they could not be automatically verified.",
                    severity=EvidenceSeverity.INFO,
                )
            ],
            explanation=explanation,
        )

    matched_count = sum(1 for c in checkable if c.matched)
    score = (matched_count / len(checkable)) * 100

    for check in checkable:
        if check.matched:
            evidence.append(
                Evidence(
                    message=f"Matched: {check.requirement.text}",
                    severity=EvidenceSeverity.POSITIVE,
                )
            )
        else:
            evidence.append(
                Evidence(
                    message=f"Not found in resume: {check.requirement.text}",
                    severity=EvidenceSeverity.WARNING,
                )
            )

    unverifiable = len(checks) - len(checkable)
    if unverifiable:
        evidence.append(
            Evidence(
                message=f"{unverifiable} requirement"
                f"{'s' if unverifiable != 1 else ''} used terms outside the recognised skill "
                "list and could not be automatically checked.",
                severity=EvidenceSeverity.INFO,
            )
        )

    return ComponentScore(
        key=key, label=label, score=clamp_score(score), weight=weight, evidence=evidence,
        explanation=explanation,
    )


def score_required_skills(job: JobDescription, resume: Resume, weight: float) -> ComponentScore:
    skill_kinds = (RequirementKind.SKILL, RequirementKind.SOFT_SKILL, RequirementKind.CERTIFICATION)
    requirements = [
        r for r in job.by_importance(RequirementImportance.REQUIRED) if r.kind in skill_kinds
    ]
    return _score_skill_requirements(
        requirements, _resume_matchable_text(resume), "required_skills", "Required Skills", weight
    )


def score_preferred_skills(job: JobDescription, resume: Resume, weight: float) -> ComponentScore:
    skill_kinds = (RequirementKind.SKILL, RequirementKind.SOFT_SKILL, RequirementKind.CERTIFICATION)
    requirements = [
        r for r in job.by_importance(RequirementImportance.PREFERRED) if r.kind in skill_kinds
    ]
    return _score_skill_requirements(
        requirements, _resume_matchable_text(resume), "preferred_skills", "Preferred Skills", weight
    )


def score_experience(job: JobDescription, resume: Resume, weight: float) -> ComponentScore:
    explanation = (
        "Compares the job's stated minimum years of experience against the total duration of "
        "the resume's experience entries (summed per role - overlapping roles are not "
        "de-duplicated, and gaps between roles are not penalised)."
    )
    required_years = max(
        (
            r.min_years
            for r in job.by_kind(RequirementKind.EXPERIENCE)
            if r.importance == RequirementImportance.REQUIRED and r.min_years is not None
        ),
        default=None,
    )
    candidate_years = total_years_experience(resume)

    if required_years is None:
        return ComponentScore(
            key="experience",
            label="Experience",
            score=100.0,
            weight=weight,
            evidence=[
                Evidence(
                    message="The job description does not specify a minimum years of experience.",
                    severity=EvidenceSeverity.INFO,
                ),
                Evidence(
                    message=f"The resume shows approximately {candidate_years:.1f} years of "
                    "experience.",
                    severity=EvidenceSeverity.INFO,
                ),
            ],
            explanation=explanation,
        )

    score = 100.0 if required_years <= 0 else min(1.0, candidate_years / required_years) * 100
    meets = candidate_years >= required_years
    evidence = [
        Evidence(
            message=f"The resume shows approximately {candidate_years:.1f} years of experience, "
            f"{'meeting' if meets else 'short of'} the {required_years:.0f}+ year requirement.",
            severity=EvidenceSeverity.POSITIVE if meets else EvidenceSeverity.WARNING,
        )
    ]
    return ComponentScore(
        key="experience", label="Experience", score=clamp_score(score), weight=weight,
        evidence=evidence, explanation=explanation,
    )


def score_education(job: JobDescription, resume: Resume, weight: float) -> ComponentScore:
    explanation = (
        "Compares the highest education level requested by the job description against the "
        "highest level detected in the resume's education section."
    )
    required_levels = [
        r.education_level
        for r in job.by_kind(RequirementKind.EDUCATION)
        if r.importance == RequirementImportance.REQUIRED and r.education_level is not None
    ]

    if not required_levels:
        return ComponentScore(
            key="education",
            label="Education",
            score=100.0,
            weight=weight,
            evidence=[
                Evidence(
                    message="The job description does not specify a minimum education level.",
                    severity=EvidenceSeverity.INFO,
                )
            ],
            explanation=explanation,
        )

    required_level = max(required_levels, key=education_level_rank)
    candidate_level = highest_education_level(resume)
    meets = education_level_rank(candidate_level) >= education_level_rank(required_level)

    if meets:
        score = 100.0
        message = (
            f"The resume's education ({candidate_level.value}) meets the "
            f"requirement ({required_level.value})."
        )
        severity = EvidenceSeverity.POSITIVE
    else:
        span = max(1, education_level_rank(EducationLevel.PHD))
        gap = education_level_rank(required_level) - education_level_rank(candidate_level)
        score = max(0.0, 100.0 - (gap / span) * 100.0)
        message = (
            f"The resume's education ({candidate_level.value}) is below the requirement "
            f"({required_level.value})."
        )
        severity = EvidenceSeverity.WARNING

    return ComponentScore(
        key="education", label="Education", score=clamp_score(score), weight=weight,
        evidence=[Evidence(message=message, severity=severity)], explanation=explanation,
    )
