"""Skill gap analysis: Strong / Moderate / Missing / Insufficient-evidence buckets (PRD section 22).

Deterministic core (presence in the resume's skills list vs. mention in the experience bullets);
the semantic layer, when available, upgrades a subset of MISSING to INSUFFICIENT_EVIDENCE when a
listed skill is plausibly related but not a confirmed match ("Kubernetes" missing, but "container
orchestration" is listed) - a genuinely different, more useful signal than a flat miss. Without
embeddings, everything not found exactly stays MISSING: a coarser, still honest signal, not a
wrong one.
"""

from __future__ import annotations

from enum import StrEnum

from pydantic import BaseModel, ConfigDict, Field

from app.analysis.taxonomy import contains_skill_mention
from app.analysis.text_metrics import bullets_of
from app.jobs.models import JobDescription, Requirement, RequirementImportance, RequirementKind
from app.matching.embeddings import EmbeddingProvider, cosine_similarity
from app.resume.models import Resume

#: Cosine-similarity floor for treating an unmatched requirement as "plausibly covered by a
#: listed skill" rather than a flat miss. Calibrated empirically against bge-small-en-v1.5: bare
#: single-word comparisons ("communication" vs "Go") cluster around 0.55-0.65 regardless of
#: actual relatedness - far too noisy to threshold on. Embedding short phrases instead
#: ("Experience with Kubernetes" vs "Experience with Docker") widens the gap: genuinely related
#: pairs measured 0.68-0.73, unrelated pairs 0.52-0.57. The threshold sits just above that gap.
_INSUFFICIENT_EVIDENCE_THRESHOLD = 0.68

#: Consistent light framing applied to both a bare requirement keyword and a bare listed skill
#: before embedding, so the comparison is phrase-to-phrase rather than word-to-word - the source
#: of the discrimination improvement above.
_SKILL_PHRASE_TEMPLATE = "Experience with {}"

_SKILL_LIKE_KINDS = (
    RequirementKind.SKILL,
    RequirementKind.SOFT_SKILL,
    RequirementKind.CERTIFICATION,
)


class SkillGapBucket(StrEnum):
    STRONG = "strong"
    MODERATE = "moderate"
    MISSING = "missing"
    INSUFFICIENT_EVIDENCE = "insufficient_evidence"


class SkillGapEntry(BaseModel):
    model_config = ConfigDict(extra="forbid")

    skill: str
    requirement_text: str
    importance: RequirementImportance
    bucket: SkillGapBucket
    evidence: str


class SkillGapResult(BaseModel):
    model_config = ConfigDict(extra="forbid")

    entries: list[SkillGapEntry] = Field(default_factory=list)
    #: Whether the INSUFFICIENT_EVIDENCE distinction was available for this result.
    semantic_available: bool


def _resume_skill_list(resume: Resume) -> list[str]:
    return [skill for group in resume.skills for skill in group.value.skills]


def _relevant_requirements(job: JobDescription) -> list[Requirement]:
    return [
        r
        for r in job.requirements
        if r.kind in _SKILL_LIKE_KINDS and r.importance != RequirementImportance.OPTIONAL
    ]


def compute_skill_gaps(
    job: JobDescription, resume: Resume, provider: EmbeddingProvider
) -> SkillGapResult:
    listed_skills = _resume_skill_list(resume)
    experience_text = " ".join(bullets_of(resume))
    semantic_available = provider.is_available()

    ordered: list[tuple[str, Requirement]] = []
    seen: set[str] = set()
    for requirement in _relevant_requirements(job):
        for keyword in requirement.keywords or [requirement.text]:
            key = keyword.strip().lower()
            if key in seen:
                continue
            seen.add(key)
            ordered.append((keyword, requirement))

    buckets: dict[str, tuple[SkillGapBucket, str]] = {}
    #: (keyword, phrase-with-context) for each MISSING requirement - the requirement's own text
    #: gives the embedding far more context than the bare keyword alone (see threshold docstring).
    missing: list[tuple[str, str]] = []
    for keyword, requirement in ordered:
        key = keyword.strip().lower()
        in_skills_list = any(key == skill.strip().lower() for skill in listed_skills)
        in_experience = contains_skill_mention(experience_text, keyword)

        if in_skills_list and in_experience:
            buckets[key] = (
                SkillGapBucket.STRONG,
                f'"{keyword}" is listed in your skills and demonstrated in your experience.',
            )
        elif in_skills_list or in_experience:
            where = "listed in your skills" if in_skills_list else "mentioned in your experience"
            buckets[key] = (SkillGapBucket.MODERATE, f'"{keyword}" is {where}, but not both.')
        else:
            buckets[key] = (
                SkillGapBucket.MISSING,
                f'"{keyword}" was not found anywhere in the resume.',
            )
            missing.append((keyword, requirement.text))

    if semantic_available and missing and listed_skills:
        missing_phrases = [text for _keyword, text in missing]
        skill_phrases = [_SKILL_PHRASE_TEMPLATE.format(skill) for skill in listed_skills]
        vectors = provider.embed([*missing_phrases, *skill_phrases])
        if vectors is not None:
            keyword_vectors = vectors[: len(missing)]
            skill_vectors = vectors[len(missing) :]
            for (keyword, _text), keyword_vector in zip(missing, keyword_vectors, strict=True):
                best = max(
                    (cosine_similarity(keyword_vector, v) for v in skill_vectors), default=0.0
                )
                if best >= _INSUFFICIENT_EVIDENCE_THRESHOLD:
                    buckets[keyword.strip().lower()] = (
                        SkillGapBucket.INSUFFICIENT_EVIDENCE,
                        f'"{keyword}" was not found directly, but a related listed skill may '
                        "cover it - worth confirming.",
                    )

    entries = [
        SkillGapEntry(
            skill=keyword,
            requirement_text=requirement.text,
            importance=requirement.importance,
            bucket=buckets[keyword.strip().lower()][0],
            evidence=buckets[keyword.strip().lower()][1],
        )
        for keyword, requirement in ordered
    ]
    return SkillGapResult(entries=entries, semantic_available=semantic_available)
