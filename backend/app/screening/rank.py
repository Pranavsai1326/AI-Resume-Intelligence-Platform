"""Ranking: sort, filter, and paginate completed candidate results.

Ranking order itself is always Layer 1 (AI_ARCHITECTURE.md section 9, "ranking order - never 3"):
sorted purely by the scoring engine's ``overall``, the same number ``/v1/match`` produces for a
single candidate - no LLM involvement, no recomputation of scores already stored per candidate.
"""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field

from app.screening.models import CandidateResult


class RankedPage(BaseModel):
    model_config = ConfigDict(extra="forbid")

    total: int
    candidates: list[CandidateResult] = Field(default_factory=list)


def rank_candidates(
    results: list[CandidateResult],
    *,
    min_score: float | None = None,
    descending: bool = True,
    limit: int = 20,
    offset: int = 0,
) -> RankedPage:
    filtered = [r for r in results if min_score is None or r.match.overall >= min_score]
    ordered = sorted(filtered, key=lambda r: r.match.overall, reverse=descending)
    page = ordered[offset : offset + limit]
    return RankedPage(total=len(filtered), candidates=page)
