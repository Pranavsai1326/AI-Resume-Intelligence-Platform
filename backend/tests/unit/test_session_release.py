"""Release semantics: the tab-teardown signal shortens a session, it does not destroy it.

`pagehide` fires on a reload and on ordinary navigation as well as on a real tab close, and the
browser gives no way to tell them apart. Destroying on that signal would discard the user's work
every time they pressed refresh, so the signal collapses the session to a short grace window
instead - keeping the cleanup benefit without the data loss.
"""

from __future__ import annotations

from app.core.clock import FakeClock
from app.sessions.manager import SessionManager
from app.sessions.memory import MemorySessionStore
from app.sessions.models import SessionMode
from app.sessions.store import object_key

GRACE = 120
IDLE = 3600
ABSOLUTE = 28_800


def build(store: MemorySessionStore, clock: FakeClock) -> SessionManager:
    return SessionManager(
        store,
        idle_ttl_seconds=IDLE,
        absolute_ttl_seconds=ABSOLUTE,
        release_grace_seconds=GRACE,
        clock=clock,
    )


async def test_release_keeps_the_session_alive_inside_the_grace_window(
    memory_store: MemorySessionStore, clock: FakeClock
) -> None:
    manager = build(memory_store, clock)
    meta = await manager.create(SessionMode.CANDIDATE)

    assert await manager.release(meta.session_id) is True

    clock.advance(GRACE - 10)
    assert await manager.get(meta.session_id) is not None, "a reload must be able to rejoin"


async def test_release_expires_the_session_after_the_grace_window(
    memory_store: MemorySessionStore, clock: FakeClock
) -> None:
    """A genuinely closed tab is cleaned up in minutes rather than after the full idle TTL."""
    manager = build(memory_store, clock)
    meta = await manager.create(SessionMode.CANDIDATE)
    await manager.put_object(meta, "document", "d1", "resume text")

    await manager.release(meta.session_id)
    clock.advance(GRACE + 1)

    assert await manager.get(meta.session_id) is None
    assert memory_store.live_key_count() == 0


async def test_release_shortens_object_ttls_too(
    memory_store: MemorySessionStore, clock: FakeClock
) -> None:
    """Objects carry their own TTLs, so they must be collapsed with the session."""
    manager = build(memory_store, clock)
    meta = await manager.create(SessionMode.CANDIDATE)
    await manager.put_object(meta, "document", "d1", "resume text")

    await manager.release(meta.session_id)

    ttl = await memory_store.ttl(object_key(meta.session_id, "document", "d1"))
    assert ttl is not None and ttl <= GRACE


async def test_resuming_restores_the_full_idle_ttl(
    memory_store: MemorySessionStore, clock: FakeClock
) -> None:
    manager = build(memory_store, clock)
    meta = await manager.create(SessionMode.CANDIDATE)
    await manager.release(meta.session_id)

    clock.advance(5)
    resumed = await manager.require(meta.session_id)
    assert resumed.released is True
    touched = await manager.touch(resumed)

    assert touched.released is False
    assert touched.remaining_lifetime(clock.now()) > GRACE
    clock.advance(GRACE + 1)
    assert await manager.get(meta.session_id) is not None


async def test_resuming_restores_object_ttls(
    memory_store: MemorySessionStore, clock: FakeClock
) -> None:
    manager = build(memory_store, clock)
    meta = await manager.create(SessionMode.CANDIDATE)
    await manager.put_object(meta, "document", "d1", "resume text")
    await manager.release(meta.session_id)

    resumed = await manager.require(meta.session_id)
    await manager.touch(resumed)

    ttl = await memory_store.ttl(object_key(meta.session_id, "document", "d1"))
    assert ttl is not None and ttl > GRACE

    clock.advance(GRACE + 1)
    assert await manager.get_object(meta, "document", "d1") == "resume text"


async def test_release_never_extends_a_session(
    memory_store: MemorySessionStore, clock: FakeClock
) -> None:
    """If the session is already closer to expiry than the grace window, leave it alone."""
    manager = build(memory_store, clock)
    meta = await manager.create(SessionMode.CANDIDATE)

    clock.advance(IDLE - 30)
    assert await manager.release(meta.session_id) is True

    clock.advance(31)
    assert await manager.get(meta.session_id) is None


async def test_release_respects_the_absolute_deadline(
    memory_store: MemorySessionStore, clock: FakeClock
) -> None:
    manager = build(memory_store, clock)
    meta = await manager.create(SessionMode.CANDIDATE)

    clock.advance(ABSOLUTE - 30)
    await manager.release(meta.session_id)
    clock.advance(31)
    assert await manager.get(meta.session_id) is None


async def test_release_of_unknown_session_is_a_no_op(
    memory_store: MemorySessionStore, clock: FakeClock
) -> None:
    manager = build(memory_store, clock)
    assert await manager.release("does-not-exist") is False
    assert await manager.release("") is False


async def test_release_does_not_affect_other_sessions(
    memory_store: MemorySessionStore, clock: FakeClock
) -> None:
    manager = build(memory_store, clock)
    a = await manager.create(SessionMode.CANDIDATE)
    b = await manager.create(SessionMode.CANDIDATE)
    await manager.put_object(b, "document", "d1", "session B content")

    await manager.release(a.session_id)
    clock.advance(GRACE + 1)

    assert await manager.get(a.session_id) is None
    assert await manager.get(b.session_id) is not None
    assert await manager.get_object(b, "document", "d1") == "session B content"
