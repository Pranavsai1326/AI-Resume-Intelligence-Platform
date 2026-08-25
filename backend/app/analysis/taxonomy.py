"""Curated word lists used by the deterministic analysis components.

These are lexicons, not models - the same kind of fixed reference data a spell-checker or a
style-linter uses. They are necessarily incomplete (English has far more strong verbs than the
list below), which is why they are only ever used to add *positive* or *informational* evidence,
never to penalise a bullet for using a verb the list happens not to contain.
"""

from __future__ import annotations

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
        # practice / soft skills
        "agile", "scrum", "product management", "project management", "leadership",
        "communication", "stakeholder management", "cross-functional collaboration",
        "mentoring", "public speaking", "technical writing",
    }
)
