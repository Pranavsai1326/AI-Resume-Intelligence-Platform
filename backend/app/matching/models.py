"""Job-match result shape. Mirrors app.resume health's ResumeHealthResult (same explainability
contract: every score is a component with evidence and an explanation), kept as a distinct model
because it also carries a skill-gap breakdown resume health has no equivalent of.
"""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field

from app.analysis.models import ComponentScore
from app.matching.gaps import SkillGapResult


class JobMatchResult(BaseModel):
    model_config = ConfigDict(extra="forbid")

    overall: float = Field(ge=0, le=100)
    components: dict[str, ComponentScore]
    #: Keys of any component excluded from the overall because it could not be computed (its
    #: weight was redistributed across the rest) - see ARCHITECTURE.md section 7.
    degraded: list[str] = Field(default_factory=list)
    methodology: dict[str, str] = Field(default_factory=dict)
    skill_gaps: SkillGapResult
