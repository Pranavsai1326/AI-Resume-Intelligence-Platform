"""Match scoring weights (ARCHITECTURE.md section 7)."""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict, model_validator

MATCH_COMPONENT_LABELS: dict[str, str] = {
    "required_skills": "Required Skills",
    "preferred_skills": "Preferred Skills",
    "experience": "Experience",
    "education": "Education",
    "project_relevance": "Project Relevance",
    "semantic_relevance": "Semantic Relevance",
}


class MatchProfile(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: str = "default"
    version: str = "1.0.0"
    weights: dict[str, float]

    @model_validator(mode="after")
    def _weights_cover_known_components_and_sum_to_one(self) -> MatchProfile:
        if set(self.weights) != set(MATCH_COMPONENT_LABELS):
            raise ValueError("weights must cover exactly the known components")
        total = sum(self.weights.values())
        if abs(total - 1.0) > 1e-6:
            raise ValueError(f"weights must sum to 1.0, got {total}")
        return self


DEFAULT_MATCH_PROFILE = MatchProfile(
    weights={
        "required_skills": 0.40,
        "preferred_skills": 0.15,
        "experience": 0.20,
        "education": 0.05,
        "project_relevance": 0.10,
        "semantic_relevance": 0.10,
    }
)
