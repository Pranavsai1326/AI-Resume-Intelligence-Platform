"""In-process ephemeral store.

The development and test backend (ADR-0002): no Redis, no Docker, no infrastructure of any
kind. Correctness properties match the Redis backend and are verified by the shared conformance
suite - notably that expiry is lazy-on-read *and* swept, so a key is never observable past its
TTL even if the janitor has not run.

Single-process only. ``Settings.validate_runtime`` refuses to start with WORKERS>1 on this
backend, so the limitation can never become a silent production bug.
"""

from __future__ import annotations

from dataclasses import dataclass

from app.core.clock import Clock, SystemClock


@dataclass(slots=True)
class _Entry:
    value: str
    expires_at: float  # monotonic seconds


class MemorySessionStore:
    """Dict-backed store with per-key TTLs.

    All mutating operations run to completion without awaiting, so they are atomic with respect
    to the event loop and need no lock.
    """

    __slots__ = ("_clock", "_data")

    def __init__(self, clock: Clock | None = None) -> None:
        self._data: dict[str, _Entry] = {}
        self._clock = clock or SystemClock()

    # -- internals -----------------------------------------------------------------------

    def _live(self, key: str) -> _Entry | None:
        entry = self._data.get(key)
        if entry is None:
            return None
        if entry.expires_at <= self._clock.monotonic():
            del self._data[key]
            return None
        return entry

    @staticmethod
    def _check_ttl(ttl_seconds: int) -> None:
        if ttl_seconds <= 0:
            raise ValueError("ttl_seconds must be positive: every stored value must expire")

    # -- SessionStore --------------------------------------------------------------------

    async def get(self, key: str) -> str | None:
        entry = self._live(key)
        return entry.value if entry else None

    async def set(self, key: str, value: str, ttl_seconds: int) -> None:
        self._check_ttl(ttl_seconds)
        self._data[key] = _Entry(value=value, expires_at=self._clock.monotonic() + ttl_seconds)

    async def delete(self, key: str) -> bool:
        existed = self._live(key) is not None
        self._data.pop(key, None)
        return existed

    async def exists(self, key: str) -> bool:
        return self._live(key) is not None

    async def ttl(self, key: str) -> int | None:
        entry = self._live(key)
        if entry is None:
            return None
        return max(0, int(entry.expires_at - self._clock.monotonic()))

    async def expire(self, key: str, ttl_seconds: int) -> bool:
        self._check_ttl(ttl_seconds)
        entry = self._live(key)
        if entry is None:
            return False
        entry.expires_at = self._clock.monotonic() + ttl_seconds
        return True

    async def incr(self, key: str, ttl_seconds: int) -> int:
        self._check_ttl(ttl_seconds)
        entry = self._live(key)
        if entry is None:
            self._data[key] = _Entry("1", self._clock.monotonic() + ttl_seconds)
            return 1
        value = int(entry.value) + 1
        entry.value = str(value)
        return value

    async def keys_in_namespace(self, namespace: str) -> list[str]:
        prefix = f"{namespace}:"
        return [key for key in list(self._data) if key.startswith(prefix) and self._live(key)]

    async def delete_namespace(self, namespace: str) -> int:
        prefix = f"{namespace}:"
        doomed = [key for key in list(self._data) if key.startswith(prefix)]
        for key in doomed:
            del self._data[key]
        return len(doomed)

    async def sweep(self) -> int:
        now = self._clock.monotonic()
        expired = [key for key, entry in self._data.items() if entry.expires_at <= now]
        for key in expired:
            del self._data[key]
        return len(expired)

    async def ping(self) -> bool:
        return True

    async def close(self) -> None:
        self._data.clear()

    # -- diagnostics ---------------------------------------------------------------------

    def live_key_count(self) -> int:
        """Number of unexpired keys. Operational metric only - never exposes values."""
        now = self._clock.monotonic()
        return sum(1 for entry in self._data.values() if entry.expires_at > now)
