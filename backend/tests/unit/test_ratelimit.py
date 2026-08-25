"""Rate limiter behaviour."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest

from app.core.clock import FakeClock
from app.core.errors import RateLimitedError
from app.core.ratelimit import (
    RateLimiter,
    RateLimitRule,
    enforce_session_ai_token_budget,
    hash_identity,
)
from app.sessions.memory import MemorySessionStore
from app.sessions.models import SessionCounters, SessionMeta, SessionMode, generate_session_id

RULE = RateLimitRule("test", limit=3, window_seconds=60)


def _session(ai_tokens: int) -> SessionMeta:
    now = datetime.now(UTC)
    return SessionMeta(
        session_id=generate_session_id(),
        mode=SessionMode.CANDIDATE,
        created_at=now,
        last_activity_at=now,
        expires_at=now + timedelta(hours=1),
        hard_expires_at=now + timedelta(hours=8),
        counters=SessionCounters(ai_tokens=ai_tokens),
    )


async def test_allows_up_to_limit(memory_store: MemorySessionStore) -> None:
    limiter = RateLimiter(memory_store)
    for expected_remaining in (2, 1, 0):
        result = await limiter.check(RULE, "1.2.3.4")
        assert result.allowed is True
        assert result.remaining == expected_remaining


async def test_blocks_past_limit(memory_store: MemorySessionStore) -> None:
    limiter = RateLimiter(memory_store)
    for _ in range(3):
        await limiter.check(RULE, "1.2.3.4")
    result = await limiter.check(RULE, "1.2.3.4")
    assert result.allowed is False
    assert result.retry_after > 0


async def test_window_resets(memory_store: MemorySessionStore, clock: FakeClock) -> None:
    limiter = RateLimiter(memory_store)
    for _ in range(4):
        await limiter.check(RULE, "1.2.3.4")
    clock.advance(61)
    assert (await limiter.check(RULE, "1.2.3.4")).allowed is True


async def test_identities_are_independent(memory_store: MemorySessionStore) -> None:
    limiter = RateLimiter(memory_store)
    for _ in range(4):
        await limiter.check(RULE, "1.2.3.4")
    assert (await limiter.check(RULE, "5.6.7.8")).allowed is True


async def test_enforce_raises(memory_store: MemorySessionStore) -> None:
    limiter = RateLimiter(memory_store)
    for _ in range(3):
        await limiter.enforce(RULE, "1.2.3.4")
    with pytest.raises(RateLimitedError) as excinfo:
        await limiter.enforce(RULE, "1.2.3.4")
    assert excinfo.value.status_code == 429
    assert "Retry-After" in excinfo.value.headers


async def test_disabled_limiter_allows_everything(memory_store: MemorySessionStore) -> None:
    limiter = RateLimiter(memory_store, enabled=False)
    for _ in range(50):
        assert (await limiter.check(RULE, "1.2.3.4")).allowed is True


async def test_store_failure_fails_open(memory_store: MemorySessionStore) -> None:
    """A limiter outage must not take the API down with it."""

    class BrokenStore(MemorySessionStore):
        async def incr(self, key: str, ttl_seconds: int) -> int:
            raise ConnectionError("store down")

    limiter = RateLimiter(BrokenStore())
    assert (await limiter.check(RULE, "1.2.3.4")).allowed is True


def test_identity_is_hashed_not_stored_raw() -> None:
    """Rate-limit keys must not contain the raw IP address."""
    digest = hash_identity("203.0.113.7")
    assert "203.0.113.7" not in digest
    assert digest == hash_identity("203.0.113.7")
    assert digest != hash_identity("203.0.113.8")


async def test_counter_keys_carry_a_ttl(memory_store: MemorySessionStore) -> None:
    limiter = RateLimiter(memory_store)
    await limiter.check(RULE, "1.2.3.4")
    key = f"rl:test:{hash_identity('1.2.3.4')}"
    ttl = await memory_store.ttl(key)
    assert ttl is not None and 0 < ttl <= 60


class TestSessionAiTokenBudget:
    """Phase 9G: a session-lifetime AI token cap, distinct from the sliding-window limiter
    above - it never resets mid-session, since the point is to bound total spend, not pace it."""

    def test_allows_spend_under_the_limit(self) -> None:
        enforce_session_ai_token_budget(_session(ai_tokens=50), limit=100)  # must not raise

    def test_blocks_once_the_limit_is_reached(self) -> None:
        with pytest.raises(RateLimitedError) as excinfo:
            enforce_session_ai_token_budget(_session(ai_tokens=100), limit=100)
        assert excinfo.value.status_code == 429
        assert "Retry-After" in excinfo.value.headers

    def test_blocks_once_the_limit_is_exceeded(self) -> None:
        with pytest.raises(RateLimitedError):
            enforce_session_ai_token_budget(_session(ai_tokens=150), limit=100)

    def test_a_fresh_session_is_never_blocked(self) -> None:
        enforce_session_ai_token_budget(_session(ai_tokens=0), limit=100)  # must not raise
