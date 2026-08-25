"""Shared text metrics used across the scoring components."""

from __future__ import annotations

from app.analysis.text_metrics import (
    bullets_of,
    has_quantification,
    leading_verb,
    starts_with_action_verb,
    starts_with_outcome_verb,
    uses_first_person,
    weak_phrases_in,
    word_count,
)
from app.documents.structure import build_resume


def test_leading_verb_strips_bullet_markers() -> None:
    assert leading_verb("- Led the migration") == "led"
    assert leading_verb("* Built a service") == "built"
    assert leading_verb("Managed a team") == "managed"


def test_leading_verb_none_for_empty_or_symbol_only() -> None:
    assert leading_verb("") is None
    assert leading_verb("- ") is None


def test_starts_with_action_verb() -> None:
    assert starts_with_action_verb("Led the migration") is True
    assert starts_with_action_verb("Responsible for the migration") is False


def test_starts_with_outcome_verb() -> None:
    assert starts_with_outcome_verb("Reduced latency by 30%") is True
    assert starts_with_outcome_verb("Attended meetings") is False


def test_action_verb_but_not_outcome_verb() -> None:
    """"Managed" is a strong action verb but not specifically outcome-oriented."""
    assert starts_with_action_verb("Managed a team of five") is True
    assert starts_with_outcome_verb("Managed a team of five") is False


def test_has_quantification() -> None:
    assert has_quantification("Reduced latency by 30%") is True
    assert has_quantification("Led a team of 8 engineers") is True
    assert has_quantification("Improved code quality") is False


def test_weak_phrases_in() -> None:
    assert weak_phrases_in("Responsible for the billing system") == ["responsible for"]
    assert weak_phrases_in("Led the billing system rewrite") == []


def test_multiple_weak_phrases_all_detected() -> None:
    hits = weak_phrases_in("Was tasked with helping with the migration, assisted with rollout")
    assert "was tasked with" in hits
    assert "assisted with" in hits


def test_uses_first_person() -> None:
    assert uses_first_person("I led the migration") is True
    assert uses_first_person("My team shipped the feature") is True
    assert uses_first_person("Led the migration") is False


def test_uses_first_person_does_not_false_positive_on_substrings() -> None:
    """"Improved" contains "i" but is not the pronoun "I"."""
    assert uses_first_person("Improved the deployment pipeline") is False


def test_word_count() -> None:
    assert word_count("Led the migration") == 3
    assert word_count("") == 0


def test_bullets_of_combines_experience_and_project_bullets() -> None:
    resume = build_resume(
        "EXPERIENCE\nEngineer, Acme\n2020 - 2021\n- Did a thing\n\n"
        "PROJECTS\nSide Project\n- Built a widget\n"
    )
    bullets = bullets_of(resume)
    assert "Did a thing" in bullets
    assert "Built a widget" in bullets


def test_bullets_of_includes_project_description_when_no_bullets() -> None:
    resume = build_resume("PROJECTS\nSide Project\nA single-line description of the project\n")
    bullets = bullets_of(resume)
    assert bullets == ["A single-line description of the project"]


def test_bullets_of_excludes_empty_strings() -> None:
    resume = build_resume("EXPERIENCE\nEngineer, Acme\n2020 - 2021\n")
    assert bullets_of(resume) == []
