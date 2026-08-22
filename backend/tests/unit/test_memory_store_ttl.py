"""TTL behaviour of the in-memory backend, exercised with a controllable clock."""

from __future__ import annotations

from app.core.clock import FakeClock
from app.sessions.memory import MemorySessionStore
from app.sessions.store import object_key, session_namespace


async def test_key_disappears_after_ttl(memory_store: MemorySessionStore, clock: FakeClock) -> None:
    key = object_key("s1", "doc", "a")
    await memory_store.set(key, "v", 60)

    clock.advance(59)
    assert await memory_store.get(key) == "v"

    clock.advance(2)
    assert await memory_store.get(key) is None
    assert await memory_store.exists(key) is False


async def test_expired_key_is_not_listed(
    memory_store: MemorySessionStore, clock: FakeClock
) -> None:
    await memory_store.set(object_key("s1", "doc", "a"), "v", 30)
    await memory_store.set(object_key("s1", "doc", "b"), "v", 300)

    clock.advance(60)
    keys = await memory_store.keys_in_namespace(session_namespace("s1"))
    assert len(keys) == 1
    assert keys[0].endswith(":b")


async def test_sweep_reclaims_expired_entries(
    memory_store: MemorySessionStore, clock: FakeClock
) -> None:
    """Expiry must not depend on someone reading the key: the janitor reclaims it."""
    for index in range(5):
        await memory_store.set(object_key("s1", "doc", str(index)), "v", 30)
    assert memory_store.live_key_count() == 5

    clock.advance(31)
    assert memory_store.live_key_count() == 0
    assert await memory_store.sweep() == 5
    assert await memory_store.sweep() == 0


async def test_incr_window_expires(memory_store: MemorySessionStore, clock: FakeClock) -> None:
    assert await memory_store.incr("rl:test:x", 60) == 1
    assert await memory_store.incr("rl:test:x", 60) == 2
    clock.advance(61)
    assert await memory_store.incr("rl:test:x", 60) == 1


async def test_close_clears_everything(memory_store: MemorySessionStore) -> None:
    await memory_store.set(object_key("s1", "doc", "a"), "v", 60)
    await memory_store.close()
    assert memory_store.live_key_count() == 0
