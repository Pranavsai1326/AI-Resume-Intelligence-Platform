"""Unit tests for app.ai.rewrite."""

from __future__ import annotations

from app.ai.providers import NullLLMProvider
from app.ai.rewrite import rewrite_bullet, rewrite_summary
from tests.ai_fakes import FailingLLMProvider, FakeLLMProvider
from tests.fixtures import make_resume


async def test_rewrite_bullet_with_null_provider_is_honestly_unavailable() -> None:
    resume = make_resume()
    proposal = await rewrite_bullet("Built the ingestion service.", resume, NullLLMProvider())
    assert proposal.available is False
    assert proposal.after is None
    assert proposal.unavailable_reason == "AI writing is not configured on this deployment."
    assert proposal.fact_guard_findings == []
    assert proposal.before == "Built the ingestion service."


async def test_rewrite_summary_with_null_provider_is_honestly_unavailable() -> None:
    resume = make_resume()
    proposal = await rewrite_summary("Backend engineer.", resume, NullLLMProvider())
    assert proposal.available is False
    assert proposal.unavailable_reason == "AI writing is not configured on this deployment."


async def test_rewrite_bullet_with_available_provider_returns_after_text() -> None:
    resume = make_resume()
    fake = FakeLLMProvider(response_text="Migrated the billing pipeline to event sourcing.")
    proposal = await rewrite_bullet("migrated pipeline", resume, fake)
    assert proposal.available is True
    assert proposal.after == "Migrated the billing pipeline to event sourcing."
    assert proposal.unavailable_reason is None


async def test_rewrite_bullet_flags_fabricated_content() -> None:
    resume = make_resume()
    fake = FakeLLMProvider(response_text="Migrated the pipeline using Snowflake and Databricks.")
    proposal = await rewrite_bullet("migrated pipeline", resume, fake)
    assert proposal.available is True
    assert len(proposal.fact_guard_findings) >= 1
    assert any("Snowflake" in msg or "Databricks" in msg for msg in proposal.fact_guard_findings)


async def test_rewrite_bullet_with_provider_that_fails_at_runtime_is_unavailable() -> None:
    resume = make_resume()
    proposal = await rewrite_bullet("bullet text", resume, FailingLLMProvider())
    assert proposal.available is False
    assert proposal.unavailable_reason == "The AI provider did not return a usable response."


async def test_rewrite_truncates_input_before_sending_to_provider() -> None:
    resume = make_resume()
    fake = FakeLLMProvider(transform=lambda user: f"len={len(user)}")
    long_text = "x" * 1000
    proposal = await rewrite_bullet(long_text, resume, fake)
    assert proposal.available is True
    assert proposal.after == "len=400"  # REWRITE_BULLET.max_input_chars
    assert proposal.before == long_text
