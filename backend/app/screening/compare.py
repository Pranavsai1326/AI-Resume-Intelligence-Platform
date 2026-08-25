"""Comparison matrix over already-stored candidate results.

No recomputation and no extra LLM calls (ARCHITECTURE.md section 6, "Comparison = matrix over
stored component scores") - every score compared here was already computed once when that
candidate's screening job ran.
"""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field

from app.screening.models import CandidateResult


class ComparisonRow(BaseModel):
    model_config = ConfigDict(extra="forbid")

    candidate_id: str
    overall: float
    components: dict[str, float]


class ComparisonResult(BaseModel):
    model_config = ConfigDict(extra="forbid")

    rows: list[ComparisonRow] = Field(default_factory=list)


def compare_candidates(results: list[CandidateResult]) -> ComparisonResult:
    rows = [
        ComparisonRow(
            candidate_id=result.candidate_id,
            overall=result.match.overall,
            components={key: score.score for key, score in result.match.components.items()},
        )
        for result in results
    ]
    return ComparisonResult(rows=rows)
