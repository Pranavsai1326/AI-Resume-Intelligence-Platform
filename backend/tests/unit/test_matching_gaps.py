"""Skill gap analysis: Strong / Moderate / Missing / Insufficient-evidence buckets."""

from __future__ import annotations

from app.documents.structure import build_resume
from app.jobs.parse import parse_job_description
from app.matching.gaps import SkillGapBucket, compute_skill_gaps
from tests.matching_fakes import FakeEmbeddingProvider

RESUME_TEXT = """EXPERIENCE
Backend Engineer, Acme
2020 - 2022
- Built distributed backend systems in Python

SKILLS
Languages: Python, Kubernetes
"""


def resume():
    return build_resume(RESUME_TEXT)


def test_skill_in_list_and_experience_is_strong() -> None:
    job = parse_job_description("Requirements\n- Proficiency in Python\n")
    result = compute_skill_gaps(job, resume(), FakeEmbeddingProvider(available=False))
    entry = next(e for e in result.entries if e.skill == "python")
    assert entry.bucket == SkillGapBucket.STRONG


def test_skill_in_list_only_is_moderate() -> None:
    job = parse_job_description("Requirements\n- Proficiency in Kubernetes\n")
    resume_no_experience_mention = build_resume(
        "EXPERIENCE\nEngineer, Acme\n2020 - 2022\n- Did general backend work\n\n"
        "SKILLS\nKubernetes\n"
    )
    result = compute_skill_gaps(
        job, resume_no_experience_mention, FakeEmbeddingProvider(available=False)
    )
    entry = next(e for e in result.entries if e.skill == "kubernetes")
    assert entry.bucket == SkillGapBucket.MODERATE


def test_completely_absent_skill_without_embeddings_is_missing() -> None:
    job = parse_job_description("Requirements\n- Proficiency in Rust\n")
    result = compute_skill_gaps(job, resume(), FakeEmbeddingProvider(available=False))
    entry = next(e for e in result.entries if e.skill == "rust")
    assert entry.bucket == SkillGapBucket.MISSING
    assert result.semantic_available is False


def test_missing_skill_can_be_upgraded_to_insufficient_evidence_with_embeddings() -> None:
    """The fake provider's similarity is marker-word overlap (tests/matching_fakes.py): the
    requirement text and a listed skill both need to share a marker word for the "plausibly
    related" upgrade to fire. Neither "billing" nor "Billing Systems" is a recognised taxonomy
    skill, so the requirement's full text is used as its own unmatched "keyword" (see
    app.matching.gaps: keywords falls back to [requirement.text] when empty) - and it shares the
    "billing" marker with the listed skill once template-wrapped ("Experience with Billing
    Systems"), which is exactly the plausibly-related case this bucket exists for.
    """
    job = parse_job_description("Requirements\n- Experience with billing systems\n")
    resume_with_unrelated_skill_name = build_resume(
        "EXPERIENCE\nEngineer, Acme\n2020 - 2022\n- Wrote services\n\nSKILLS\nBilling Systems\n"
    )
    result = compute_skill_gaps(job, resume_with_unrelated_skill_name, FakeEmbeddingProvider())
    entry = next(e for e in result.entries)
    assert entry.bucket == SkillGapBucket.INSUFFICIENT_EVIDENCE
    assert result.semantic_available is True


def test_no_requirements_yields_no_entries() -> None:
    job = parse_job_description("Responsibilities\n- Build things\n")
    result = compute_skill_gaps(job, resume(), FakeEmbeddingProvider())
    assert result.entries == []


def test_duplicate_keywords_across_requirements_are_deduplicated() -> None:
    job = parse_job_description(
        "Requirements\n- Proficiency in Python\n- Strong Python skills preferred\n"
    )
    result = compute_skill_gaps(job, resume(), FakeEmbeddingProvider(available=False))
    python_entries = [e for e in result.entries if e.skill == "python"]
    assert len(python_entries) == 1


def test_soft_skills_are_included_in_gap_analysis() -> None:
    job = parse_job_description("Requirements\n- Strong communication skills\n")
    result = compute_skill_gaps(job, resume(), FakeEmbeddingProvider(available=False))
    assert any(e.skill == "communication" for e in result.entries)
