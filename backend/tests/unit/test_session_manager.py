"""Session lifecycle rules: sliding idle TTL, absolute cap, object TTLs, destruction."""

from __future__ import annotations

import pytest

from app.core.clock import FakeClock
from app.core.errors import SessionExpiredError
from app.sessions.manager import SessionManager
from app.sessions.memory import MemorySessionStore
from app.sessions.models import SessionMode, generate_session_id

IDLE = 3600
ABSOLUTE = 28_800


async def test_create_sets_both_deadlines(manager: SessionManager) -> None:
    meta = await manager.create(SessionMode.CANDIDATE)
    assert (meta.expires_at - meta.created_at).total_seconds() == IDLE
    assert (meta.hard_expires_at - meta.created_at).total_seconds() == ABSOLUTE
    assert meta.counters.documents == 0


async def test_session_id_is_opaque_and_unique() -> None:
    ids = {generate_session_id() for _ in range(500)}
    assert len(ids) == 500
    assert all(len(value) >= 40 for value in ids)


async def test_get_returns_none_for_unknown_id(manager: SessionManager) -> None:
    assert await manager.get("does-not-exist") is None
    assert await manager.get("") is None


async def test_require_raises_for_unknown_id(manager: SessionManager) -> None:
    with pytest.raises(SessionExpiredError):
        await manager.require("nope")


async def test_idle_expiry(manager: SessionManager, clock: FakeClock) -> None:
    meta = await manager.create(SessionMode.CANDIDATE)
    clock.advance(IDLE - 10)
    assert await manager.get(meta.session_id) is not None

    clock.advance(20)
    assert await manager.get(meta.session_id) is None


async def test_touch_slides_idle_deadline(manager: SessionManager, clock: FakeClock) -> None:
    meta = await manager.create(SessionMode.CANDIDATE)
    clock.advance(IDLE - 60)
    refreshed = await manager.touch(meta)

    clock.advance(IDLE - 60)
    assert await manager.get(refreshed.session_id) is not None, "activity should extend idle TTL"


async def test_activity_never_extends_absolute_lifetime(
    manager: SessionManager, clock: FakeClock
) -> None:
    """The 8-hour cap is the hard rule: heartbeating forever must not defeat it."""
    meta = await manager.create(SessionMode.CANDIDATE)
    elapsed = 0
    while elapsed < ABSOLUTE - 600:
        clock.advance(600)
        elapsed += 600
        current = await manager.get(meta.session_id)
        assert current is not None
        meta = await manager.touch(current)
        assert meta.expires_at <= meta.hard_expires_at

    clock.advance(1200)  # cross the absolute deadline
    assert await manager.get(meta.session_id) is None


async def test_touch_clamps_expiry_to_hard_deadline(
    manager: SessionManager, clock: FakeClock
) -> None:
    meta = await manager.create(SessionMode.CANDIDATE)
    clock.advance(ABSOLUTE - 120)
    refreshed = await manager.touch(meta)
    assert refreshed.expires_at == refreshed.hard_expires_at


async def test_destroy_removes_session_and_objects(manager: SessionManager) -> None:
    meta = await manager.create(SessionMode.CANDIDATE)
    await manager.put_object(meta, "document", "d1", "extracted text")
    await manager.put_object(meta, "analysis", "a1", "{}")
    assert len(await manager.list_object_keys(meta)) == 3  # meta + 2 objects

    removed = await manager.destroy(meta.session_id)
    assert removed == 3
    assert await manager.get(meta.session_id) is None
    assert await manager.list_object_keys(meta) == []


async def test_objects_expire_with_the_session(
    manager: SessionManager, clock: FakeClock, memory_store: MemorySessionStore
) -> None:
    """No object may outlive the session that owns it."""
    meta = await manager.create(SessionMode.CANDIDATE)
    await manager.put_object(meta, "document", "d1", "extracted text")

    clock.advance(IDLE + 1)
    assert await manager.get(meta.session_id) is None
    assert await manager.get_object(meta, "document", "d1") is None
    assert memory_store.live_key_count() == 0


async def test_object_ttl_capped_at_session_lifetime(manager: SessionManager) -> None:
    meta = await manager.create(SessionMode.CANDIDATE)
    await manager.put_object(meta, "document", "d1", "text", ttl_seconds=999_999)

    from app.sessions.store import object_key

    ttl = await manager.store.ttl(object_key(meta.session_id, "document", "d1"))
    assert ttl is not None and ttl <= IDLE


async def test_object_shorter_ttl_is_respected(manager: SessionManager, clock: FakeClock) -> None:
    meta = await manager.create(SessionMode.CANDIDATE)
    await manager.put_object(meta, "cache", "c1", "value", ttl_seconds=60)

    clock.advance(61)
    assert await manager.get(meta.session_id) is not None
    assert await manager.get_object(meta, "cache", "c1") is None


async def test_sessions_are_isolated(manager: SessionManager) -> None:
    a = await manager.create(SessionMode.CANDIDATE)
    b = await manager.create(SessionMode.RECRUITER)
    await manager.put_object(a, "document", "d1", "session A content")
    await manager.put_object(b, "document", "d1", "session B content")

    assert await manager.get_object(a, "document", "d1") == "session A content"
    assert await manager.get_object(b, "document", "d1") == "session B content"

    await manager.destroy(a.session_id)
    assert await manager.get_object(b, "document", "d1") == "session B content"
    assert await manager.get(b.session_id) is not None


async def test_corrupt_metadata_is_discarded(
    manager: SessionManager, memory_store: MemorySessionStore
) -> None:
    from app.sessions.store import meta_key

    meta = await manager.create(SessionMode.CANDIDATE)
    await memory_store.set(meta_key(meta.session_id), "not json", 600)
    assert await manager.get(meta.session_id) is None
    assert await memory_store.get(meta_key(meta.session_id)) is None


async def test_put_object_on_expired_session_raises(
    manager: SessionManager, clock: FakeClock
) -> None:
    meta = await manager.create(SessionMode.CANDIDATE)
    clock.advance(IDLE + 1)
    with pytest.raises(SessionExpiredError):
        await manager.put_object(meta, "document", "d1", "text")
