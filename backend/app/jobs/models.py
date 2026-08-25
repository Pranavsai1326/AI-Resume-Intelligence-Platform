"""Structured job description model.

Deterministic extraction only (AI_ARCHITECTURE.md Layer 1) - the same discipline as
``app.resume.models``: every requirement is what the text actually said, classified by
regex/keyword heuristics, never invented or reworded by a model.
"""

from __future__ import annotations

from enum import StrEnum

from pydantic import BaseModel, ConfigDict, Field


class RequirementImportance(StrEnum):
    REQUIRED = "required"
    PREFERRED = "preferred"
    #: Extracted from a responsibilities/context section - informational, not a matching target.
    OPTIONAL = "optional"


class RequirementKind(StrEnum):
    SKILL = "skill"
    SOFT_SKILL = "soft_skill"
    EXPERIENCE = "experience"
    EDUCATION = "education"
    CERTIFICATION = "certification"
    RESPONSIBILITY = "responsibility"


class EducationLevel(StrEnum):
    """Ordered so levels can be compared: ``list(EducationLevel).index(level)``."""

    NONE = "none"
    ASSOCIATE = "associate"
    BACHELOR = "bachelor"
    MASTER = "master"
    PHD = "phd"


class Requirement(BaseModel):
    model_config = ConfigDict(extra="forbid")

    text: str
    kind: RequirementKind
    importance: RequirementImportance
    #: Taxonomy skills recognised inside ``text`` (app.analysis.taxonomy.COMMON_SKILLS), used as
    #: matching keys. Empty when the requirement mentions no recognised skill - it is still kept
    #: verbatim in ``text`` rather than discarded.
    keywords: list[str] = Field(default_factory=list)
    #: Minimum years of experience this requirement states, if any (``kind == EXPERIENCE``).
    min_years: float | None = None
    #: Minimum education level this requirement states, if any (``kind == EDUCATION``).
    education_level: EducationLevel | None = None


class JobDescription(BaseModel):
    model_config = ConfigDict(extra="forbid")

    title: str | None = None
    requirements: list[Requirement] = Field(default_factory=list)
    #: Responsibility bullets kept for display/context; not matching targets themselves.
    responsibilities: list[str] = Field(default_factory=list)
    raw_text: str

    def by_kind(self, kind: RequirementKind) -> list[Requirement]:
        return [r for r in self.requirements if r.kind == kind]

    def by_importance(self, importance: RequirementImportance) -> list[Requirement]:
        return [r for r in self.requirements if r.importance == importance]
