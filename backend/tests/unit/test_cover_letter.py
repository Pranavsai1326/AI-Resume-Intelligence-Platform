"""Unit tests for app.ai.cover_letter."""

from __future__ import annotations

import json

from app.ai.cover_letter import generate_cover_letter
from app.ai.providers import NullLLMProvider
from tests.ai_fakes import FailingLLMProvider, FakeLLMProvider
from tests.fixtures import make_job, make_resume

_GOOD_RESPONSE = json.dumps(
    {
        "salutation": "Dear Hiring Team",
        "body_paragraphs": [
            "I'm excited to apply for the Senior Backend Engineer role. My work migrating "
            "the billing pipeline to event sourcing at Cascade Systems is directly relevant.",
            "I also bring hands-on experience with Python and Kubernetes.",
        ],
        "closing": "Sincerely,",
    }
)


async def test_null_provider_is_honestly_unavailable() -> None:
    proposal = await generate_cover_letter(make_resume(), make_job(), NullLLMProvider())
    assert proposal.available is False
    assert proposal.unavailable_reason == "AI writing is not configured on this deployment."
    assert proposal.body_paragraphs == []


async def test_failing_provider_is_unavailable_not_an_error() -> None:
    proposal = await generate_cover_letter(make_resume(), make_job(), FailingLLMProvider())
    assert proposal.available is False
    assert proposal.unavailable_reason == "The AI provider did not return a usable cover letter."


async def test_grounded_letter_has_no_fact_guard_findings() -> None:
    fake = FakeLLMProvider(response_text=_GOOD_RESPONSE)
    proposal = await generate_cover_letter(make_resume(), make_job(), fake)
    assert proposal.available is True
    assert proposal.salutation == "Dear Hiring Team"
    assert len(proposal.body_paragraphs) == 2
    assert proposal.fact_guard_findings == []


async def test_fabricated_letter_content_is_flagged() -> None:
    fabricated = json.dumps(
        {
            "salutation": "Dear Hiring Team",
            "body_paragraphs": ["I led a team of 50 engineers using MongoDB and Snowflake."],
            "closing": "Sincerely,",
        }
    )
    fake = FakeLLMProvider(response_text=fabricated)
    proposal = await generate_cover_letter(make_resume(), make_job(), fake)
    assert proposal.available is True
    assert len(proposal.fact_guard_findings) >= 1


async def test_job_title_is_not_flagged_as_a_fabrication() -> None:
    """The job title/requirements are legitimate context, not a resume claim - referencing them
    verbatim must not trip the guard (app.ai.fact_guard.FactIndex.build's job-context widening)."""
    letter = json.dumps(
        {
            "salutation": "Dear Hiring Team",
            "body_paragraphs": ["I'm applying for the Senior Backend Engineer position."],
            "closing": "Sincerely,",
        }
    )
    fake = FakeLLMProvider(response_text=letter)
    proposal = await generate_cover_letter(make_resume(), make_job(), fake)
    assert proposal.fact_guard_findings == []


async def test_malformed_output_that_cannot_be_repaired_is_unavailable() -> None:
    fake = FakeLLMProvider(response_text="not json")
    proposal = await generate_cover_letter(make_resume(), make_job(), fake)
    assert proposal.available is False
    assert proposal.unavailable_reason == "The AI provider did not return a usable cover letter."
