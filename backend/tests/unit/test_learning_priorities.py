"""Unit tests for app.matching.learning_priorities."""

from __future__ import annotations

from app.jobs.models import RequirementImportance
from app.matching.gaps import SkillGapBucket, SkillGapEntry, SkillGapResult
from app.matching.learning_priorities import compute_learning_priorities


def _entry(skill: str, importance: RequirementImportance, bucket: SkillGapBucket) -> SkillGapEntry:
    return SkillGapEntry(
        skill=skill, requirement_text=skill, importance=importance, bucket=bucket, evidence="x"
    )


def test_strong_skills_are_excluded_entirely() -> None:
    gaps = SkillGapResult(
        entries=[_entry("python", RequirementImportance.REQUIRED, SkillGapBucket.STRONG)],
        semantic_available=False,
    )
    result = compute_learning_priorities(gaps)
    assert result.priorities == []


def test_required_missing_ranks_before_preferred_missing() -> None:
    gaps = SkillGapResult(
        entries=[
            _entry("rust", RequirementImportance.PREFERRED, SkillGapBucket.MISSING),
            _entry("docker", RequirementImportance.REQUIRED, SkillGapBucket.MISSING),
        ],
        semantic_available=False,
    )
    result = compute_learning_priorities(gaps)
    assert [p.skill for p in result.priorities] == ["docker", "rust"]


def test_within_same_importance_missing_ranks_before_insufficient_evidence_before_moderate() -> (
    None
):
    gaps = SkillGapResult(
        entries=[
            _entry("aaa_moderate", RequirementImportance.REQUIRED, SkillGapBucket.MODERATE),
            _entry(
                "bbb_insufficient",
                RequirementImportance.REQUIRED,
                SkillGapBucket.INSUFFICIENT_EVIDENCE,
            ),
            _entry("ccc_missing", RequirementImportance.REQUIRED, SkillGapBucket.MISSING),
        ],
        semantic_available=True,
    )
    result = compute_learning_priorities(gaps)
    assert [p.skill for p in result.priorities] == [
        "ccc_missing",
        "bbb_insufficient",
        "aaa_moderate",
    ]


def test_each_priority_carries_a_human_readable_reason() -> None:
    gaps = SkillGapResult(
        entries=[_entry("docker", RequirementImportance.REQUIRED, SkillGapBucket.MISSING)],
        semantic_available=False,
    )
    result = compute_learning_priorities(gaps)
    assert result.priorities[0].reason  # non-empty, no bare/unexplained ranking
    assert "docker" not in result.priorities[0].reason.lower()  # reason is generic per-bucket text


def test_semantic_available_flag_passes_through() -> None:
    gaps = SkillGapResult(entries=[], semantic_available=True)
    result = compute_learning_priorities(gaps)
    assert result.semantic_available is True
