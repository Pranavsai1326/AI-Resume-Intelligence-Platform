"""Unit tests for app.screening.rank."""

from __future__ import annotations

from app.analysis.models import ComponentScore
from app.matching.gaps import SkillGapResult
from app.matching.models import JobMatchResult
from app.screening.models import CandidateResult, RedactionInfo
from app.screening.rank import rank_candidates
from tests.fixtures import make_resume


def _match(overall: float) -> JobMatchResult:
    return JobMatchResult(
        overall=overall,
        components={
            "required_skills": ComponentScore(
                key="required_skills",
                label="Required Skills",
                score=overall,
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


def _candidate(candidate_id: str, overall: float) -> CandidateResult:
    return CandidateResult(
        candidate_id=candidate_id,
        match=_match(overall),
        redaction=RedactionInfo(applied=True, fields=["name"]),
        resume=make_resume(),
    )


def test_ranked_descending_by_default() -> None:
    results = [_candidate("a", 40.0), _candidate("b", 90.0), _candidate("c", 60.0)]
    page = rank_candidates(results)
    assert [c.candidate_id for c in page.candidates] == ["b", "c", "a"]


def test_ascending_when_requested() -> None:
    results = [_candidate("a", 40.0), _candidate("b", 90.0)]
    page = rank_candidates(results, descending=False)
    assert [c.candidate_id for c in page.candidates] == ["a", "b"]


def test_min_score_filters_and_total_reflects_filtered_count() -> None:
    results = [_candidate("a", 40.0), _candidate("b", 90.0), _candidate("c", 60.0)]
    page = rank_candidates(results, min_score=50.0)
    assert page.total == 2
    assert {c.candidate_id for c in page.candidates} == {"b", "c"}


def test_pagination_limit_and_offset() -> None:
    results = [_candidate(str(i), float(i)) for i in range(10)]
    page = rank_candidates(results, limit=3, offset=2)
    assert page.total == 10
    assert len(page.candidates) == 3
    # descending by score: 9,8,7,6,5,4,3,2,1,0 -> offset 2 -> 7,6,5
    assert [c.candidate_id for c in page.candidates] == ["7", "6", "5"]


def test_empty_results() -> None:
    page = rank_candidates([])
    assert page.total == 0
    assert page.candidates == []
