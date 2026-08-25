"""Scoring weights.

Configuration, not literals scattered through the component modules (ARCHITECTURE.md section 7):
every call site pulls weights from here, so retuning the profile never means hunting through the
scoring code.
"""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict, model_validator

COMPONENT_LABELS: dict[str, str] = {
    "ats_compatibility": "ATS Compatibility",
    "content_quality": "Content Quality",
    "skills_coverage": "Skills Coverage",
    "experience_quality": "Experience Quality",
    "formatting": "Formatting",
    "impact": "Impact",
}


class ScoringProfile(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: str = "default"
    version: str = "1.0.0"
    weights: dict[str, float]

    @model_validator(mode="after")
    def _weights_cover_known_components_and_sum_to_one(self) -> ScoringProfile:
        if set(self.weights) != set(COMPONENT_LABELS):
            raise ValueError("weights must cover exactly the known components")
        total = sum(self.weights.values())
        if abs(total - 1.0) > 1e-6:
            raise ValueError(f"weights must sum to 1.0, got {total}")
        return self


DEFAULT_PROFILE = ScoringProfile(
    weights={
        "ats_compatibility": 0.20,
        "content_quality": 0.20,
        "experience_quality": 0.20,
        "skills_coverage": 0.15,
        "formatting": 0.15,
        "impact": 0.10,
    }
)
