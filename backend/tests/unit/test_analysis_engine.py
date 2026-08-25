"""The scoring engine: weighting, overall computation, and the degrade/renormalise mechanism."""

from __future__ import annotations

import pytest

from app.analysis.config import COMPONENT_LABELS, DEFAULT_PROFILE, ScoringProfile
from app.analysis.engine import compute_resume_health
from app.documents.extract.base import LayoutSignals
from app.documents.structure import build_resume
from app.resume.models import Resume

LAYOUT = LayoutSignals(page_count=1)


def test_default_weights_sum_to_one() -> None:
    assert abs(sum(DEFAULT_PROFILE.weights.values()) - 1.0) < 1e-9


def test_profile_rejects_weights_not_summing_to_one() -> None:
    with pytest.raises(ValueError, match="sum to 1"):
        ScoringProfile(weights={key: 0.1 for key in COMPONENT_LABELS})


def test_profile_rejects_unknown_component_keys() -> None:
    with pytest.raises(ValueError, match="known components"):
        ScoringProfile(weights={"made_up_component": 1.0})


def test_all_six_components_are_present() -> None:
    result = compute_resume_health(Resume(), LAYOUT)
    assert set(result.components) == set(COMPONENT_LABELS)


def test_overall_is_the_weighted_average_of_components() -> None:
    resume = build_resume("EXPERIENCE\nEngineer, Acme\n2020 - 2021\n- Did a thing\n")
    result = compute_resume_health(resume, LAYOUT)
    expected = sum(c.score * c.weight for c in result.components.values())
    assert abs(result.overall - round(expected, 1)) < 0.15


def test_nothing_is_degraded_in_phase_3() -> None:
    """Every Phase 3 component is fully deterministic and needs no external dependency."""
    result = compute_resume_health(Resume(), LAYOUT)
    assert result.degraded == []
    assert all(c.available for c in result.components.values())


def test_empty_resume_does_not_crash_and_scores_low() -> None:
    result = compute_resume_health(Resume(), LAYOUT)
    assert 0.0 <= result.overall <= 100.0
    assert result.overall < 30


def test_methodology_names_the_profile() -> None:
    result = compute_resume_health(Resume(), LAYOUT)
    assert result.methodology == {"profile": "default", "version": "1.0.0"}


def test_custom_profile_changes_the_overall() -> None:
    resume = build_resume(
        "EXPERIENCE\nEngineer, Acme\n2020 - 2021\n- Did a thing\n\nSKILLS\nPython\n"
    )
    heavy_skills = ScoringProfile(
        name="skills-heavy",
        weights={
            "ats_compatibility": 0.05,
            "content_quality": 0.05,
            "experience_quality": 0.05,
            "skills_coverage": 0.75,
            "formatting": 0.05,
            "impact": 0.05,
        },
    )
    default_result = compute_resume_health(resume, LAYOUT, DEFAULT_PROFILE)
    custom_result = compute_resume_health(resume, LAYOUT, heavy_skills)
    assert default_result.overall != custom_result.overall
    assert custom_result.methodology["profile"] == "skills-heavy"


def test_every_component_score_stays_within_bounds() -> None:
    resume = build_resume(
        "Name\nemail@example.test\n\nEXPERIENCE\nEngineer, Acme\n2020 - 2021\n- Did a thing\n"
    )
    result = compute_resume_health(resume, LAYOUT)
    for component in result.components.values():
        assert 0.0 <= component.score <= 100.0
        assert component.evidence, f"{component.key} produced no evidence"
