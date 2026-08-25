"""Education-level classification.

Shared by JD requirement parsing (a bullet asking for "Bachelor's degree...") and resume
matching (a resume's own education entries), so the two sides of a comparison are classified by
the exact same rules.
"""

from __future__ import annotations

import re

from app.jobs.models import EducationLevel

_EDUCATION_PATTERNS: tuple[tuple[re.Pattern[str], EducationLevel], ...] = (
    (re.compile(r"\bph\.?d\b|\bdoctorate\b", re.IGNORECASE), EducationLevel.PHD),
    (
        re.compile(r"\bmaster'?s?\b|\bm\.?s\.?\b|\bm\.?b\.?a\.?\b|\bm\.?eng\b", re.IGNORECASE),
        EducationLevel.MASTER,
    ),
    (
        re.compile(
            r"\bbachelor'?s?\b|\bb\.?s\.?\b|\bb\.?a\.?\b|\bundergraduate degree\b", re.IGNORECASE
        ),
        EducationLevel.BACHELOR,
    ),
    (re.compile(r"\bassociate'?s?\b", re.IGNORECASE), EducationLevel.ASSOCIATE),
)

_LEVEL_RANK: dict[EducationLevel, int] = {level: rank for rank, level in enumerate(EducationLevel)}


def classify_education_level(text: str) -> EducationLevel | None:
    """The highest education level mentioned in ``text``, or ``None`` if none is recognised."""
    for pattern, level in _EDUCATION_PATTERNS:
        if pattern.search(text):
            return level
    return None


def education_level_rank(level: EducationLevel) -> int:
    """Ordinal rank for comparison: higher means more advanced."""
    return _LEVEL_RANK[level]
