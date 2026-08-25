"""Strip protected and irrelevant attributes before scoring or any model call (PRD section 8,
SECURITY.md section 10).

Ranking must consume an allowlist of job-relevant features only - skills, experience, education,
certifications, projects, requirement coverage. Everything here removes what is *not* on that
allowlist, before ``app.matching.engine.compute_job_match`` or any LLM ever sees the resume:

* Direct identifiers - name, email, phone, links - are structural fields already isolated by
  Phase 2's extraction (``ContactInfo``), so they are simply cleared, not pattern-matched.
* A photo is never redacted because one is never present to begin with: Phase 2 extraction never
  captures images, only text (``app.documents.extract``) - the guarantee holds by construction,
  not by a scrub step that could miss one.
* Everything else (gender, marital status, nationality, religion, race/ethnicity, age/DOB) has no
  isolated field - it can only appear as free text, so a curated pattern list scrubs explicit
  mentions. Like ``app.analysis.taxonomy``'s word lists, this is necessarily incomplete: it
  catches common, explicit disclosure patterns (a "Nationality:" line, an unambiguous term like
  "married"), not every way a resume could imply a protected attribute. The product states this
  reduces, and does not eliminate, bias (PRD section 8) - this module is one deliberately honest
  layer of that reduction, not a claim of completeness.
"""

from __future__ import annotations

import re

from app.resume.models import Resume

_REDACTED = "[redacted]"

#: Explicit-disclosure and unambiguous-term patterns, grouped by the category reported in
#: ``RedactionResult.fields``. Deliberately narrow: a company name, an institution, or a
#: technology term must never be caught by accident, so patterns favour disclosure-label shapes
#: ("Nationality:", "DOB:") over broad demonym/adjective lists that would risk exactly that.
_PROTECTED_PATTERNS: dict[str, list[re.Pattern[str]]] = {
    "gender": [
        re.compile(r"\bgender\s*:", re.IGNORECASE),
        re.compile(r"\b(?:transgender|non-binary|nonbinary)\b", re.IGNORECASE),
        re.compile(r"\bhe\s*/\s*him\b|\bshe\s*/\s*her\b|\bthey\s*/\s*them\b", re.IGNORECASE),
    ],
    "marital_status": [
        re.compile(r"\bmarital\s*status\s*:", re.IGNORECASE),
        re.compile(r"\b(?:married|divorced|widowed|widower)\b", re.IGNORECASE),
        re.compile(r"\bspouse\s*:", re.IGNORECASE),
    ],
    "nationality": [
        re.compile(r"\bnationality\s*:", re.IGNORECASE),
        re.compile(r"\bcitizen(?:ship)?\s*(?:of|:)", re.IGNORECASE),
        re.compile(r"\bvisa\s*status\s*:", re.IGNORECASE),
    ],
    "religion": [
        re.compile(r"\breligion\s*:", re.IGNORECASE),
        re.compile(
            r"\b(?:christian|muslim|hindu|jewish|buddhist|sikh|atheist)\b", re.IGNORECASE
        ),
    ],
    "race_or_ethnicity": [
        re.compile(r"\b(?:race|ethnicity)\s*:", re.IGNORECASE),
    ],
    "age_or_dob": [
        re.compile(r"\bdate\s*of\s*birth\s*:?|\bd\.?o\.?b\.?\s*:", re.IGNORECASE),
        re.compile(r"\bage\s*:\s*\d{1,3}\b", re.IGNORECASE),
        re.compile(r"\b\d{1,3}\s*years?\s*old\b", re.IGNORECASE),
    ],
}


def _scrub(text: str) -> tuple[str, set[str]]:
    hit_categories: set[str] = set()
    for category, patterns in _PROTECTED_PATTERNS.items():
        for pattern in patterns:
            if pattern.search(text):
                hit_categories.add(category)
                text = pattern.sub(_REDACTED, text)
    return text, hit_categories


def _scrub_list(values: list[str]) -> tuple[list[str], set[str]]:
    hit_categories: set[str] = set()
    scrubbed: list[str] = []
    for value in values:
        cleaned, hits = _scrub(value)
        scrubbed.append(cleaned)
        hit_categories |= hits
    return scrubbed, hit_categories


def redact_resume(resume: Resume) -> tuple[Resume, list[str]]:
    """A redacted copy of ``resume`` plus the sorted list of categories that were actually
    removed - never mutates the input, and never reports a category that found nothing."""
    redacted = resume.model_copy(deep=True)
    fields: set[str] = set()

    if redacted.contact.full_name is not None:
        redacted.contact.full_name = None
        fields.add("name")
    if redacted.contact.email is not None:
        redacted.contact.email = None
        fields.add("email")
    if redacted.contact.phone is not None:
        redacted.contact.phone = None
        fields.add("phone")
    if redacted.contact.links:
        redacted.contact.links = []
        fields.add("links")

    if redacted.summary is not None:
        cleaned, hits = _scrub(redacted.summary.value)
        redacted.summary.value = cleaned
        fields |= hits

    for experience in redacted.experience:
        experience.value.bullets, hits = _scrub_list(experience.value.bullets)
        fields |= hits
        if experience.value.location:
            experience.value.location, hits = _scrub(experience.value.location)
            fields |= hits

    for education in redacted.education:
        education.value.details, hits = _scrub_list(education.value.details)
        fields |= hits
        if education.value.location:
            education.value.location, hits = _scrub(education.value.location)
            fields |= hits

    for project in redacted.projects:
        project.value.bullets, hits = _scrub_list(project.value.bullets)
        fields |= hits
        if project.value.description:
            project.value.description, hits = _scrub(project.value.description)
            fields |= hits

    for custom_section in redacted.custom_sections:
        custom_section.value.bullets, hits = _scrub_list(custom_section.value.bullets)
        fields |= hits

    return redacted, sorted(fields)
