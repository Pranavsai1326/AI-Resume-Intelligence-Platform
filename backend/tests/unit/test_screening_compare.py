"""Unit tests for app.screening.compare."""

from __future__ import annotations

from app.analysis.models import ComponentScore
from app.matching.gaps import SkillGapResult
from app.matching.models import JobMatchResult
from app.screening.compare import compare_candidates
from app.screening.models import CandidateResult, RedactionInfo
from tests.fixtures import make_resume


def _candidate(candidate_id: str, overall: float, required_skills_score: float) -> CandidateResult:
    match = JobMatchResult(
        overall=overall,
        components={
            "required_skills": ComponentScore(
                key="required_skills",
                label="Required Skills",
                score=required_skills_score,
                weight=1.0,
                available=True,
                evidence=[],
                explanation="x",
            )
        },
        degraded=[],
        methodology={"profile": "default", "version": "1.0.0"},
        skill_gaps=SkillGapResult(entries=[], semantic_available=False),
    )
    return CandidateResult(
        candidate_id=candidate_id,
        match=match,
        redaction=RedactionInfo(applied=True, fields=["name"]),
        resume=make_resume(),
    )


def test_compare_produces_one_row_per_candidate_with_no_recomputation() -> None:
    candidates = [_candidate("a", 80.0, 90.0), _candidate("b", 60.0, 50.0)]
    result = compare_candidates(candidates)
    assert [row.candidate_id for row in result.rows] == ["a", "b"]
    assert result.rows[0].overall == 80.0
    assert result.rows[0].components["required_skills"] == 90.0
    assert result.rows[1].overall == 60.0


def test_compare_empty_list() -> None:
    result = compare_candidates([])
    assert result.rows == []
