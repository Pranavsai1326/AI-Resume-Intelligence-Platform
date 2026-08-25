"""Curated word lists used by the deterministic analysis components.

These are lexicons, not models - the same kind of fixed reference data a spell-checker or a
style-linter uses. They are necessarily incomplete (English has far more strong verbs than the
list below), which is why they are only ever used to add *positive* or *informational* evidence,
never to penalise a bullet for using a verb the list happens not to contain.
"""

from __future__ import annotations

import re
from collections.abc import Iterable
from functools import lru_cache

#: Verbs that lead a resume bullet clearly and directly ("Led the migration...").
ACTION_VERBS = frozenset(
    {
        "achieved", "analyzed", "architected", "automated", "authored", "built", "collaborated",
        "coordinated", "created", "debugged", "delivered", "deployed", "designed", "developed",
        "directed", "drove", "established", "evaluated", "executed", "expanded", "facilitated",
        "founded", "generated", "grew", "guided", "implemented", "improved", "increased",
        "influenced", "initiated", "integrated", "introduced", "launched", "led", "leveraged",
        "maintained", "managed", "mentored", "migrated", "negotiated", "operated", "optimized",
        "orchestrated", "organized", "overhauled", "owned", "partnered", "pioneered", "planned",
        "presented", "produced", "reduced", "refactored", "researched", "resolved", "restructured",
        "scaled", "shipped", "simplified", "spearheaded", "standardized", "streamlined",
        "strengthened", "supervised", "supported", "tested", "trained", "transformed",
        "translated", "upgraded", "validated", "wrote",
    }
)

#: Subset of ACTION_VERBS that specifically signal a measurable outcome rather than an activity.
OUTCOME_VERBS = frozenset(
    {
        "achieved", "automated", "delivered", "drove", "expanded", "generated", "grew",
        "improved", "increased", "launched", "optimized", "reduced", "resolved", "scaled",
        "saved", "shipped", "streamlined", "strengthened", "transformed", "upgraded",
    }
)

#: Passive, vague phrasing that a resume bullet is usually better off without. Detected by
#: substring match on the lowercased bullet; presence adds a warning, never blocks anything.
WEAK_PHRASES = (
    "responsible for", "duties included", "worked on", "helped with", "in charge of",
    "was tasked with", "assisted with", "participated in", "involved in", "familiar with",
)

#: A representative, non-exhaustive sample of common professional/technical skills, used only to
#: give positive credit for recognisable entries - an uncommon or niche skill is never penalised
#: for being absent from this list.
COMMON_SKILLS = frozenset(
    {
        # languages
        "python", "javascript", "typescript", "java", "c++", "c#", "go", "rust", "ruby", "php",
        "swift", "kotlin", "scala", "r", "sql", "html", "css",
        # frameworks / libraries
        "react", "angular", "vue", "next.js", "django", "flask", "fastapi", "spring", "express",
        "node.js", ".net", "rails", "tensorflow", "pytorch", "pandas", "numpy",
        # infrastructure / cloud
        "aws", "azure", "gcp", "docker", "kubernetes", "terraform", "ansible", "jenkins",
        "github actions", "ci/cd", "linux", "nginx",
        # data
        "postgresql", "mysql", "mongodb", "redis", "elasticsearch", "kafka", "spark", "airflow",
        "snowflake", "bigquery",
        # practice
        "agile", "scrum", "product management", "project management", "technical writing",
    }
)

#: Non-technical skills, kept separate from COMMON_SKILLS so "leadership" or "communication"
#: is never conflated with a technical/tooling skill by a caller that only wants one or the
#: other (app.jobs.parse classifies a requirement as SOFT_SKILL vs SKILL using this split).
SOFT_SKILLS = frozenset(
    {
        "communication", "leadership", "teamwork", "collaboration", "problem-solving",
        "problem solving", "adaptability", "time management", "critical thinking",
        "attention to detail", "interpersonal skills", "stakeholder management",
        "cross-functional collaboration", "mentoring", "public speaking",
    }
)


@lru_cache(maxsize=4096)
def _mention_pattern(skill: str) -> re.Pattern[str]:
    """A regex matching ``skill`` as a whole token, not merely as a substring.

    Naive ``skill in text`` matching is wrong for anything short: "r" (the language) matches
    inside "your", "were", "programmer"; "go" matches inside "google", "algorithm". Word
    boundaries via lookaround (rather than ``\\b``) so symbol-containing skills like "c++" and
    "ci/cd" are still bounded correctly - ``\\b`` does not behave usefully around punctuation.
    """
    escaped = re.escape(skill.strip().lower())
    return re.compile(rf"(?<![A-Za-z0-9]){escaped}(?![A-Za-z0-9])", re.IGNORECASE)


def contains_skill_mention(text: str, skill: str) -> bool:
    """Whether ``skill`` appears in ``text`` as a whole token, case-insensitively."""
    if not skill.strip():
        return False
    return bool(_mention_pattern(skill).search(text))


def find_skills_in_text(text: str, skills: Iterable[str]) -> list[str]:
    """Every skill from ``skills`` that appears in ``text`` as a whole token."""
    return [skill for skill in skills if contains_skill_mention(text, skill)]
