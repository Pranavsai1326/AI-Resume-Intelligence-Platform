"""Word-boundary-safe skill matching (app.analysis.taxonomy).

These tests exist because naive substring matching (``skill in text``) is wrong for anything
short: "r" matches inside "your"/"were"/"programmer", "go" matches inside "google"/"algorithm".
Both app.jobs.parse (requirement keyword extraction) and app.analysis.skills_coverage (grounded-
skill detection) depend on getting this right.
"""

from __future__ import annotations

from app.analysis.taxonomy import contains_skill_mention, find_skills_in_text


def test_short_skill_does_not_match_inside_a_longer_word() -> None:
    assert contains_skill_mention("Reached out to your manager", "r") is False
    assert contains_skill_mention("They were on the team", "r") is False
    assert contains_skill_mention("Improved reliability", "go") is False


def test_short_skill_matches_as_a_standalone_word() -> None:
    assert contains_skill_mention("Proficient in R for data analysis", "r") is True
    assert contains_skill_mention("Built services in Go and Python", "go") is True


def test_case_insensitive() -> None:
    assert contains_skill_mention("Experience with PYTHON", "python") is True
    assert contains_skill_mention("experience with python", "Python") is True


def test_symbol_containing_skill_is_bounded_correctly() -> None:
    assert contains_skill_mention("Wrote services in C++ for years", "c++") is True
    assert contains_skill_mention("Set up CI/CD pipelines", "ci/cd") is True
    # Known limitation of alphanumeric-boundary matching: a symbol immediately after the match
    # (as in "C+++") is not itself alphanumeric, so the boundary check still passes. This is an
    # accepted tradeoff for symbol-containing skills like "c++" and "c#", where a strict boundary
    # would instead fail to match the far more common "C++," / "C++." cases.
    assert contains_skill_mention("Wrote services in C+++ for years", "c++") is True
    assert contains_skill_mention("Wrote services in Objective-C++ recently", "c++") is True


def test_multi_word_skill_matches() -> None:
    assert contains_skill_mention("Strong project management skills", "project management") is True
    assert contains_skill_mention("Strong project skills", "project management") is False


def test_empty_skill_never_matches() -> None:
    assert contains_skill_mention("anything at all", "") is False
    assert contains_skill_mention("anything at all", "   ") is False


def test_find_skills_in_text_returns_only_actual_mentions() -> None:
    found = find_skills_in_text(
        "Built backend services in Python and Go, deployed with Kubernetes",
        ["python", "go", "kubernetes", "rust", "r"],
    )
    assert set(found) == {"python", "go", "kubernetes"}
