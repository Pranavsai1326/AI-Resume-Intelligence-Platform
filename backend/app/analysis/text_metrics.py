"""Shared text metrics consumed by the scoring components.

Deterministic regex and lexicon matching only - Layer 1 of AI_ARCHITECTURE.md, never an LLM.
Each function measures one narrow, well-defined property so a component's score can point to
exactly which bullet or field triggered which piece of evidence.
"""

from __future__ import annotations

import re

from app.analysis.taxonomy import ACTION_VERBS, OUTCOME_VERBS, WEAK_PHRASES
from app.resume.models import Resume

_LEADING_NON_WORD_RE = re.compile(r"^[^A-Za-z]+")
_FIRST_WORD_RE = re.compile(r"[A-Za-z']+")
_NUMBER_RE = re.compile(r"\d")
_FIRST_PERSON_RE = re.compile(r"\b(i|me|my|myself)\b", re.IGNORECASE)


def bullets_of(resume: Resume) -> list[str]:
    """Every bullet-shaped line in the resume: experience and project bullets/descriptions.

    Education details and certifications are excluded - they are rarely written as achievement
    statements, so scoring them against action-verb/impact criteria would misfire.
    """
    bullets: list[str] = []
    for experience in resume.experience:
        bullets.extend(experience.value.bullets)
    for project in resume.projects:
        bullets.extend(project.value.bullets)
        if project.value.description:
            bullets.append(project.value.description)
    return [b for b in bullets if b.strip()]


def leading_verb(bullet: str) -> str | None:
    """The first word of a bullet, lowercased - typically the verb a strong bullet leads with."""
    stripped = _LEADING_NON_WORD_RE.sub("", bullet.strip())
    match = _FIRST_WORD_RE.match(stripped)
    return match.group(0).lower() if match else None


def starts_with_action_verb(bullet: str) -> bool:
    verb = leading_verb(bullet)
    return verb in ACTION_VERBS if verb else False


def starts_with_outcome_verb(bullet: str) -> bool:
    verb = leading_verb(bullet)
    return verb in OUTCOME_VERBS if verb else False


def has_quantification(text: str) -> bool:
    """Whether a bullet contains a number.

    A standard, widely used proxy for "this claims a measurable result" ("led a team of 8",
    "cut latency by 30%"). It is a proxy, not a certainty - a bullet can contain a number that
    is not an achievement metric (a year, a version number) and this function does not try to
    tell those apart; it is documented as a heuristic everywhere it is consumed.
    """
    return bool(_NUMBER_RE.search(text))


def weak_phrases_in(text: str) -> list[str]:
    lowered = text.lower()
    return [phrase for phrase in WEAK_PHRASES if phrase in lowered]


def uses_first_person(text: str) -> bool:
    return bool(_FIRST_PERSON_RE.search(text))


def word_count(text: str) -> int:
    return len(text.split())
