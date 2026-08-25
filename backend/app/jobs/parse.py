"""Job description parsing: title, sections, and requirement-level classification.

Deterministic only (AI_ARCHITECTURE.md Layer 1). Mirrors the resume pipeline's shape
(``app.documents.sections`` + ``app.documents.structure``) but for a different document: a JD's
"sections" separate required from preferred from purely informational content, and each bullet
inside a requirements section becomes one classified :class:`~app.jobs.models.Requirement`.
"""

from __future__ import annotations

import re
from enum import StrEnum

from app.analysis.taxonomy import COMMON_SKILLS, SOFT_SKILLS, find_skills_in_text
from app.documents.heading_split import find_headers, slice_bodies
from app.jobs.education import classify_education_level
from app.jobs.models import JobDescription, Requirement, RequirementImportance, RequirementKind

# -- section detection -------------------------------------------------------------------------


class _JdSection(StrEnum):
    REQUIRED = "required"
    PREFERRED = "preferred"
    RESPONSIBILITIES = "responsibilities"
    #: Benefits, "about us", compensation, equal-opportunity boilerplate - not a matching target.
    IGNORED = "ignored"


_SECTION_KEYWORDS: dict[str, _JdSection] = {
    "requirements": _JdSection.REQUIRED,
    "required qualifications": _JdSection.REQUIRED,
    "minimum qualifications": _JdSection.REQUIRED,
    "basic qualifications": _JdSection.REQUIRED,
    "qualifications": _JdSection.REQUIRED,
    "must have": _JdSection.REQUIRED,
    "what you'll need": _JdSection.REQUIRED,
    "what you need": _JdSection.REQUIRED,
    "who you are": _JdSection.REQUIRED,
    "about you": _JdSection.REQUIRED,
    "skills": _JdSection.REQUIRED,
    "required skills": _JdSection.REQUIRED,
    "preferred qualifications": _JdSection.PREFERRED,
    "preferred skills": _JdSection.PREFERRED,
    "preferred": _JdSection.PREFERRED,
    "nice to have": _JdSection.PREFERRED,
    "nice-to-have": _JdSection.PREFERRED,
    "bonus points": _JdSection.PREFERRED,
    "bonus": _JdSection.PREFERRED,
    "responsibilities": _JdSection.RESPONSIBILITIES,
    "key responsibilities": _JdSection.RESPONSIBILITIES,
    "what you'll do": _JdSection.RESPONSIBILITIES,
    "what you will do": _JdSection.RESPONSIBILITIES,
    "the role": _JdSection.RESPONSIBILITIES,
    "duties": _JdSection.RESPONSIBILITIES,
    "day to day": _JdSection.RESPONSIBILITIES,
    "benefits": _JdSection.IGNORED,
    "perks": _JdSection.IGNORED,
    "compensation": _JdSection.IGNORED,
    "about us": _JdSection.IGNORED,
    "about the company": _JdSection.IGNORED,
    "about the team": _JdSection.IGNORED,
    "equal opportunity": _JdSection.IGNORED,
    "how to apply": _JdSection.IGNORED,
}

_BULLET_PREFIX_RE = re.compile(r"^[\-•\*●▪]\s*")


def _clean_bullet(line: str) -> str:
    return _BULLET_PREFIX_RE.sub("", line.strip()).strip()


def _bullet_lines(body: str) -> list[str]:
    return [cleaned for line in body.split("\n") if (cleaned := _clean_bullet(line))]


def _extract_title(lines: list[str], first_header_line: int) -> str | None:
    """The first non-empty line before any section header, if short enough to be a title."""
    for line in lines[:first_header_line]:
        stripped = line.strip()
        if stripped and len(stripped) <= 100:
            return stripped
    return None


# -- requirement classification --------------------------------------------------------------

_YEARS_RE = re.compile(
    r"(\d+(?:\.\d+)?)\+?\s*(?:-\s*\d+\+?\s*)?years?", re.IGNORECASE
)

_CERTIFICATION_RE = re.compile(r"\bcertifi|\blicense[ds]?\b|\bcredential", re.IGNORECASE)


def classify_requirement(text: str, importance: RequirementImportance) -> Requirement:
    """Classify one requirement bullet by what kind of thing it is asking for.

    Order matters: education and years-of-experience patterns are checked first because they
    are the most specific and least ambiguous signals; a bullet that matches neither falls back
    to skill/soft-skill keyword matching, and if nothing at all is recognised it is still kept
    verbatim as a plain skill requirement rather than dropped.
    """
    years_match = _YEARS_RE.search(text)
    if years_match:
        return Requirement(
            text=text,
            kind=RequirementKind.EXPERIENCE,
            importance=importance,
            min_years=float(years_match.group(1)),
        )

    education_level = classify_education_level(text)
    if education_level is not None:
        return Requirement(
            text=text,
            kind=RequirementKind.EDUCATION,
            importance=importance,
            education_level=education_level,
        )

    if _CERTIFICATION_RE.search(text):
        return Requirement(
            text=text,
            kind=RequirementKind.CERTIFICATION,
            importance=importance,
            keywords=find_skills_in_text(text, COMMON_SKILLS),
        )

    soft_skills = find_skills_in_text(text, SOFT_SKILLS)
    skill_keywords = find_skills_in_text(text, COMMON_SKILLS)
    if soft_skills and not skill_keywords:
        return Requirement(
            text=text, kind=RequirementKind.SOFT_SKILL, importance=importance, keywords=soft_skills
        )

    return Requirement(
        text=text, kind=RequirementKind.SKILL, importance=importance, keywords=skill_keywords
    )


# -- top level -----------------------------------------------------------------------------


def parse_job_description(text: str) -> JobDescription:
    lines = text.split("\n")
    headers = find_headers(lines, _SECTION_KEYWORDS)

    title = _extract_title(lines, headers[0].line_index if headers else len(lines))

    requirements: list[Requirement] = []
    responsibilities: list[str] = []

    for header, body in slice_bodies(lines, headers):
        bullets = _bullet_lines(body)
        if header.kind is _JdSection.REQUIRED:
            requirements.extend(
                classify_requirement(b, RequirementImportance.REQUIRED) for b in bullets
            )
        elif header.kind is _JdSection.PREFERRED:
            requirements.extend(
                classify_requirement(b, RequirementImportance.PREFERRED) for b in bullets
            )
        elif header.kind is _JdSection.RESPONSIBILITIES:
            responsibilities.extend(bullets)
            requirements.extend(
                Requirement(
                    text=b,
                    kind=RequirementKind.RESPONSIBILITY,
                    importance=RequirementImportance.OPTIONAL,
                )
                for b in bullets
            )
        # _JdSection.IGNORED sections contribute nothing.

    return JobDescription(
        title=title,
        requirements=requirements,
        responsibilities=responsibilities,
        raw_text=text,
    )
