"""Conformance suite run against every SessionStore backend.

Both backends must satisfy the same contract; the Redis parametrisation is skipped when no
Redis is reachable so local development never depends on it (ADR-0002).
"""

from __future__ import annotations

import asyncio
import os
from collections.abc import AsyncIterator

import pytest

from app.sessions.memory import MemorySessionStore
from app.sessions.store import SessionStore, object_key, session_namespace

REDIS_URL = os.environ.get("TEST_REDIS_URL", "redis://localhost:6379/15")


async def _redis_available() -> bool:
    try:
        from app.sessions.redis_store import RedisSessionStore
    except ImportError:
        return False
    store = RedisSessionStore.from_url(REDIS_URL)
    try:
        return await asyncio.wait_for(store.ping(), timeout=1.0)
    except Exception:
        return False
    finally:
        await store.close()


@pytest.fixture(params=["memory", "redis"])
async def store(request: pytest.FixtureRequest) -> AsyncIterator[SessionStore]:
    if request.param == "memory":
        yield MemorySessionStore()
        return

    if not await _redis_available():
        pytest.skip("Redis not available; set TEST_REDIS_URL to run the Redis conformance suite")
    from app.sessions.redis_store import RedisSessionStore

    redis_store = RedisSessionStore.from_url(REDIS_URL)
    await redis_store.delete_namespace(session_namespace("conformance"))
    try:
        yield redis_store
    finally:
        await redis_store.delete_namespace(session_namespace("conformance"))
        await redis_store.close()


NS = session_namespace("conformance")


async def test_set_and_get_roundtrip(store: SessionStore) -> None:
    key = object_key("conformance", "doc", "a")
    await store.set(key, "value", 60)
    assert await store.get(key) == "value"
    assert await store.exists(key) is True


async def test_missing_key_returns_none(store: SessionStore) -> None:
    assert await store.get(object_key("conformance", "doc", "absent")) is None
    assert await store.exists(object_key("conformance", "doc", "absent")) is False
    assert await store.ttl(object_key("conformance", "doc", "absent")) is None


async def test_ttl_is_mandatory_and_positive(store: SessionStore) -> None:
    """The store has no way to express persistence: a non-positive TTL is a programming error."""
    with pytest.raises(ValueError):
        await store.set(object_key("conformance", "doc", "b"), "v", 0)
    with pytest.raises(ValueError):
        await store.set(object_key("conformance", "doc", "b"), "v", -5)


async def test_ttl_reported(store: SessionStore) -> None:
    key = object_key("conformance", "doc", "c")
    await store.set(key, "v", 60)
    ttl = await store.ttl(key)
    assert ttl is not None and 0 < ttl <= 60


async def test_expire_resets_ttl(store: SessionStore) -> None:
    key = object_key("conformance", "doc", "d")
    await store.set(key, "v", 60)
    assert await store.expire(key, 120) is True
    ttl = await store.ttl(key)
    assert ttl is not None and ttl > 60
    assert await store.expire(object_key("conformance", "doc", "gone"), 60) is False


async def test_delete(store: SessionStore) -> None:
    key = object_key("conformance", "doc", "e")
    await store.set(key, "v", 60)
    assert await store.delete(key) is True
    assert await store.delete(key) is False
    assert await store.get(key) is None


async def test_incr_counts_and_expires(store: SessionStore) -> None:
    key = f"{NS}:counter"
    assert await store.incr(key, 60) == 1
    assert await store.incr(key, 60) == 2
    ttl = await store.ttl(key)
    assert ttl is not None and ttl <= 60


async def test_namespace_listing_and_deletion(store: SessionStore) -> None:
    for index in range(3):
        await store.set(object_key("conformance", "doc", str(index)), "v", 60)
    keys = await store.keys_in_namespace(NS)
    assert len(keys) >= 3

    removed = await store.delete_namespace(NS)
    assert removed >= 3
    assert await store.keys_in_namespace(NS) == []
    assert await store.get(object_key("conformance", "doc", "0")) is None


async def test_namespace_deletion_is_isolated(store: SessionStore) -> None:
    """Destroying one session must not touch another's data."""
    await store.set(object_key("conformance", "doc", "mine"), "mine", 60)
    other_ns = session_namespace("conformance-other")
    await store.set(object_key("conformance-other", "doc", "theirs"), "theirs", 60)

    await store.delete_namespace(NS)
    assert await store.get(object_key("conformance-other", "doc", "theirs")) == "theirs"
    await store.delete_namespace(other_ns)


async def test_ping(store: SessionStore) -> None:
    assert await store.ping() is True
