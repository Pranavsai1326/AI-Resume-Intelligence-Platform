"""Semantic matching components: honest unavailability and the marker-based fake provider."""

from __future__ import annotations

from app.documents.structure import build_resume
from app.jobs.parse import parse_job_description
from app.matching.semantic import score_project_relevance, score_semantic_relevance
from tests.matching_fakes import FakeEmbeddingProvider

RESUME_WITH_PROJECTS = """EXPERIENCE
Backend Engineer, Acme
2020 - 2022
- Built distributed billing systems in Python

PROJECTS
Billing Pipeline (Python)
- Rebuilt the distributed billing pipeline for reliability

Recipe Book (Swift)
- A hobby app for saving pastry recipes
"""

JD_TEXT = "Requirements\n- Experience with Python and distributed backend systems\n"


def test_semantic_relevance_unavailable_without_provider() -> None:
    resume = build_resume(RESUME_WITH_PROJECTS)
    job = parse_job_description(JD_TEXT)
    result = score_semantic_relevance(
        job, resume, FakeEmbeddingProvider(available=False), weight=0.1
    )
    assert result.available is False
    assert result.score == 0.0
    assert "not available" in result.evidence[0].message


def test_semantic_relevance_unavailable_on_runtime_failure() -> None:
    resume = build_resume(RESUME_WITH_PROJECTS)
    job = parse_job_description(JD_TEXT)
    provider = FakeEmbeddingProvider(available=True, fails_at_runtime=True)
    result = score_semantic_relevance(job, resume, provider, weight=0.1)
    assert result.available is False


def test_semantic_relevance_scores_related_content_higher() -> None:
    resume = build_resume(RESUME_WITH_PROJECTS)
    job = parse_job_description(JD_TEXT)
    provider = FakeEmbeddingProvider()
    result = score_semantic_relevance(job, resume, provider, weight=0.1)
    assert result.available is True
    assert result.score > 0


def test_project_relevance_unavailable_without_provider() -> None:
    resume = build_resume(RESUME_WITH_PROJECTS)
    job = parse_job_description(JD_TEXT)
    result = score_project_relevance(
        job, resume, FakeEmbeddingProvider(available=False), weight=0.1
    )
    assert result.available is False


def test_project_relevance_no_projects_is_available_but_scores_zero() -> None:
    """Distinguishes 'nothing to compare' from 'cannot compare' - only the latter is unavailable."""
    resume = build_resume("EXPERIENCE\nEngineer, Acme\n2020 - 2022\n- Did things\n")
    job = parse_job_description(JD_TEXT)
    result = score_project_relevance(job, resume, FakeEmbeddingProvider(), weight=0.1)
    assert result.available is True
    assert result.score == 0.0
    assert "No projects" in result.evidence[0].message


def test_project_relevance_picks_the_best_matching_project() -> None:
    resume = build_resume(RESUME_WITH_PROJECTS)
    job = parse_job_description(JD_TEXT)
    result = score_project_relevance(job, resume, FakeEmbeddingProvider(), weight=0.1)
    assert "Billing Pipeline" in result.evidence[0].message
    assert "Recipe Book" not in result.evidence[0].message
