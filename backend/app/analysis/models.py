"""Explainable scoring output.

Per ARCHITECTURE.md section 7: every score is a component with its inputs, weight and evidence
attached, never a bare number. A score with no evidence is a defect, not an edge case - every
component builder in this package is expected to produce at least one piece of evidence,
positive or otherwise, explaining what it found.
"""

from __future__ import annotations

from enum import StrEnum

from pydantic import BaseModel, ConfigDict, Field


class EvidenceSeverity(StrEnum):
    #: Something the resume does well - shown so a good resume isn't just told "looks fine".
    POSITIVE = "positive"
    #: Neutral, informational observation.
    INFO = "info"
    #: A specific, actionable issue.
    WARNING = "warning"


class Evidence(BaseModel):
    model_config = ConfigDict(extra="forbid")

    message: str
    severity: EvidenceSeverity


class ComponentScore(BaseModel):
    model_config = ConfigDict(extra="forbid")

    key: str
    label: str
    #: 0-100.
    score: float = Field(ge=0, le=100)
    #: The weight actually used in the overall score - post-renormalisation if any component in
    #: the same result was unavailable (ARCHITECTURE.md section 7).
    weight: float = Field(ge=0, le=1)
    available: bool = True
    evidence: list[Evidence] = Field(default_factory=list)
    #: One or two sentences summarising how the score was derived - never just the number.
    explanation: str


class ResumeHealthResult(BaseModel):
    model_config = ConfigDict(extra="forbid")

    overall: float = Field(ge=0, le=100)
    components: dict[str, ComponentScore]
    #: Keys of any component that could not be computed and was excluded from the overall,
    #: with the remaining weights renormalised. Empty in Phase 3 - every component here is
    #: deterministic and needs no external dependency - but the field exists so later components
    #: (e.g. one needing embeddings) degrade the same visible way rather than a special case.
    degraded: list[str] = Field(default_factory=list)
    methodology: dict[str, str] = Field(default_factory=dict)
