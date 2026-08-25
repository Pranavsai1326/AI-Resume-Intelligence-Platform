"""The match engine: weighting, overall computation, and the degrade/renormalise mechanism.

Exercised here with ``embedding_backend="none"`` (the real ``NullEmbeddingProvider``, not a
fake) - the fast, hermetic, and also the most important case to get right, since it is this
deployment's default whenever the fastembed package or model cannot load. The "everything
available" path is covered by the live smoke test and by ``tests/unit/test_embeddings.py``,
which exercises the real model and skips gracefully if it cannot load.
"""

from __future__ import annotations

import pytest

from app.config import Settings
from app.documents.structure import build_resume
from app.jobs.parse import parse_job_description
from app.matching.config import DEFAULT_MATCH_PROFILE, MATCH_COMPONENT_LABELS, MatchProfile
from app.matching.engine import compute_job_match
from app.resume.models import Resume

RESUME_TEXT = """EXPERIENCE
Backend Engineer, Acme
2020 - 2023
- Built distributed backend systems in Python, cutting latency by 20%

EDUCATION
State University, Bachelor of Science in Computer Science
2016 - 2020

SKILLS
Languages: Python
"""

JD_TEXT = """Requirements
- 3+ years of experience
- Bachelor degree
- Proficiency in Python
"""


@pytest.fixture
def settings_no_embeddings(tmp_path: object) -> Settings:
    return Settings(app_env="development", temp_dir=str(tmp_path), embedding_backend="none")


def test_default_weights_sum_to_one() -> None:
    assert abs(sum(DEFAULT_MATCH_PROFILE.weights.values()) - 1.0) < 1e-9


def test_profile_rejects_weights_not_summing_to_one() -> None:
    with pytest.raises(ValueError, match="sum to 1"):
        MatchProfile(weights={key: 0.1 for key in MATCH_COMPONENT_LABELS})


def test_profile_rejects_unknown_component_keys() -> None:
    with pytest.raises(ValueError, match="known components"):
        MatchProfile(weights={"made_up": 1.0})


def test_all_six_components_present(settings_no_embeddings: Settings) -> None:
    resume = build_resume(RESUME_TEXT)
    job = parse_job_description(JD_TEXT)
    result = compute_job_match(resume, job, settings_no_embeddings)
    assert set(result.components) == set(MATCH_COMPONENT_LABELS)


def test_semantic_components_degrade_when_embeddings_unavailable(
    settings_no_embeddings: Settings,
) -> None:
    resume = build_resume(RESUME_TEXT)
    job = parse_job_description(JD_TEXT)
    result = compute_job_match(resume, job, settings_no_embeddings)

    assert set(result.degraded) == {"project_relevance", "semantic_relevance"}
    assert result.components["project_relevance"].available is False
    assert result.components["semantic_relevance"].available is False


def test_degraded_weights_are_redistributed_across_available_components(
    settings_no_embeddings: Settings,
) -> None:
    resume = build_resume(RESUME_TEXT)
    job = parse_job_description(JD_TEXT)
    result = compute_job_match(resume, job, settings_no_embeddings)

    available_weight = sum(
        c.weight for key, c in result.components.items() if key not in result.degraded
    )
    assert abs(available_weight - 1.0) < 1e-6

    # required_skills started at 0.40 of 1.0; excluding the two semantic components (0.10+0.10 of
    # weight) redistributes proportionally across the remaining 0.80, so it should now be higher.
    assert result.components["required_skills"].weight > 0.40


def test_overall_uses_only_available_components(settings_no_embeddings: Settings) -> None:
    resume = build_resume(RESUME_TEXT)
    job = parse_job_description(JD_TEXT)
    result = compute_job_match(resume, job, settings_no_embeddings)

    available = {k: c for k, c in result.components.items() if k not in result.degraded}
    expected = sum(c.score * c.weight for c in available.values())
    assert abs(result.overall - round(expected, 1)) < 0.15


def test_empty_resume_and_job_does_not_crash(settings_no_embeddings: Settings) -> None:
    result = compute_job_match(Resume(), parse_job_description(""), settings_no_embeddings)
    assert 0.0 <= result.overall <= 100.0


def test_skill_gaps_are_included_and_reflect_unavailable_semantics(
    settings_no_embeddings: Settings,
) -> None:
    resume = build_resume(RESUME_TEXT)
    job = parse_job_description(JD_TEXT)
    result = compute_job_match(resume, job, settings_no_embeddings)
    assert result.skill_gaps.semantic_available is False


def test_methodology_names_the_profile(settings_no_embeddings: Settings) -> None:
    resume = build_resume(RESUME_TEXT)
    job = parse_job_description(JD_TEXT)
    result = compute_job_match(resume, job, settings_no_embeddings)
    assert result.methodology == {"profile": "default", "version": "1.0.0"}


def test_every_component_score_stays_within_bounds(settings_no_embeddings: Settings) -> None:
    resume = build_resume(RESUME_TEXT)
    job = parse_job_description(JD_TEXT)
    result = compute_job_match(resume, job, settings_no_embeddings)
    for component in result.components.values():
        assert 0.0 <= component.score <= 100.0
        assert component.evidence, f"{component.key} produced no evidence"
