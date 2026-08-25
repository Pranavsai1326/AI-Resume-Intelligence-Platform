"""Unit tests for app.ai.interview."""

from __future__ import annotations

import json

from app.ai.interview import generate_interview_questions
from app.ai.providers import NullLLMProvider
from tests.ai_fakes import FailingLLMProvider, FakeLLMProvider
from tests.fixtures import make_job, make_resume

_GOOD_RESPONSE = json.dumps(
    {
        "questions": [
            {
                "question": "Walk me through migrating the billing pipeline to event sourcing.",
                "category": "technical",
                "rationale": "You mention this migration directly in your experience section.",
                "grounded_in": "Migrated the billing pipeline to event sourcing",
            },
            {
                "question": "How do you approach reducing latency in a production system?",
                "category": "technical",
                "rationale": "Relevant to your query-planner tuning work and the role's needs.",
                "grounded_in": "Reduced latency by tuning the query planner",
            },
        ]
    }
)


async def test_null_provider_is_honestly_unavailable() -> None:
    proposal = await generate_interview_questions(make_resume(), make_job(), NullLLMProvider())
    assert proposal.available is False
    assert proposal.unavailable_reason == "AI writing is not configured on this deployment."
    assert proposal.questions == []


async def test_failing_provider_is_unavailable_not_an_error() -> None:
    proposal = await generate_interview_questions(make_resume(), make_job(), FailingLLMProvider())
    assert proposal.available is False
    assert proposal.unavailable_reason == "The AI provider did not return a usable question set."


async def test_grounded_questions_have_no_fact_guard_findings() -> None:
    fake = FakeLLMProvider(response_text=_GOOD_RESPONSE)
    proposal = await generate_interview_questions(make_resume(), make_job(), fake)
    assert proposal.available is True
    assert len(proposal.questions) == 2
    assert proposal.questions[0].category == "technical"
    assert all(q.fact_guard_findings == [] for q in proposal.questions)


async def test_fabricated_rationale_is_flagged() -> None:
    fabricated = json.dumps(
        {
            "questions": [
                {
                    "question": "Tell me about leading 50 engineers.",
                    "category": "behavioral",
                    "rationale": "You led a team of 50 engineers using MongoDB.",
                    "grounded_in": "led a team of 50 engineers",
                }
            ]
        }
    )
    fake = FakeLLMProvider(response_text=fabricated)
    proposal = await generate_interview_questions(make_resume(), make_job(), fake)
    assert proposal.available is True
    assert len(proposal.questions[0].fact_guard_findings) >= 1


async def test_malformed_output_that_cannot_be_repaired_is_unavailable() -> None:
    fake = FakeLLMProvider(response_text="not json")
    proposal = await generate_interview_questions(make_resume(), make_job(), fake)
    assert proposal.available is False
