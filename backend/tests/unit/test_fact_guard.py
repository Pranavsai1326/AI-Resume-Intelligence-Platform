"""Unit tests for app.ai.fact_guard.

The key regression covered here: a sentence-initial capitalized word (an ordinary rewrite
opening like "Migrated...") must never be flagged just because English capitalizes the first
word of a sentence - but a genuine fabrication elsewhere in the same sentence must still be
caught. See app/ai/fact_guard.py's module docstring for the reasoning.
"""

from __future__ import annotations

from app.ai.fact_guard import FactIndex, check
from tests.fixtures import make_resume


def _index() -> FactIndex:
    return FactIndex.build(make_resume())


def test_fact_index_build_collects_words_and_numbers() -> None:
    index = _index()
    assert "python" in index.words
    assert "kubernetes" in index.words
    assert "cascade" in index.words  # from the organization name


def test_sentence_initial_capitalized_word_is_not_flagged_when_source_word_matches() -> None:
    index = _index()
    text = "Migrated the billing pipeline to event sourcing for better reliability."
    findings = check(text, index)
    assert findings == []


def test_sentence_initial_word_absent_from_source_is_not_flagged_for_position_alone() -> None:
    """The sentence-initial exemption is positional, not content-based - by design, a false
    positive here costs nothing since the very first word is disproportionately likely to be a
    rewritten action verb, not a fabricated proper noun."""
    index = _index()
    text = "Spearheaded the migration project across three teams."
    findings = check(text, index)
    # "Spearheaded" (position 0) is exempted; no other capitalized/technical token is present.
    assert findings == []


def test_mid_sentence_fabricated_technology_is_flagged() -> None:
    index = _index()
    text = "Migrated the billing pipeline using Snowflake and Databricks for analytics."
    findings = check(text, index)
    flagged_tokens = {f.token for f in findings}
    assert "Snowflake" in flagged_tokens
    assert "Databricks" in flagged_tokens


def test_fabricated_number_is_flagged() -> None:
    index = _index()
    text = "Migrated the billing pipeline, improving throughput by 47%."
    findings = check(text, index)
    flagged_tokens = {f.token for f in findings}
    assert "47" in flagged_tokens


def test_number_present_in_source_is_not_flagged() -> None:
    from app.resume.models import ExperienceEntry
    from app.resume.provenance import Provenance, ProvenancedValue

    resume = make_resume()
    resume.experience.append(
        ProvenancedValue(
            value=ExperienceEntry(
                title="Engineer",
                organization="Acme",
                bullets=["Improved throughput by 47%"],
            ),
            provenance=Provenance.extracted(confidence=0.9),
        )
    )
    index = FactIndex.build(resume)
    findings = check("Migrated the pipeline, improving throughput by 47%.", index)
    assert findings == []


def test_common_english_words_are_not_flagged() -> None:
    index = _index()
    text = "Led the team while supporting cross-functional delivery and using established tools."
    findings = check(text, index)
    assert findings == []


def test_words_present_in_source_are_not_flagged() -> None:
    index = _index()
    text = "Continued building on the Python and Kubernetes work from Cascade Systems."
    findings = check(text, index)
    assert findings == []
