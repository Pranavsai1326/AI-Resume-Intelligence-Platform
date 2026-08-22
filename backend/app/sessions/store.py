"""Ephemeral key/value store interface.

Every value written through this interface carries a TTL. There is no "store forever" method,
by design: the type system itself refuses to express persistence (ADR-0003).

Two implementations exist behind this protocol - ``MemorySessionStore`` for development and
tests, ``RedisSessionStore`` for production - and both are held to the same conformance suite.
"""

from __future__ import annotations

from typing import Protocol, runtime_checkable

#: Key namespace helpers. Every object belonging to a session lives beneath its prefix so the
#: whole session can be destroyed in one operation, leaving nothing orphaned.
SESSION_PREFIX = "sess"


def session_namespace(session_id: str) -> str:
    return f"{SESSION_PREFIX}:{session_id}"


def meta_key(session_id: str) -> str:
    return f"{session_namespace(session_id)}:meta"


def object_key(session_id: str, kind: str, object_id: str) -> str:
    return f"{session_namespace(session_id)}:obj:{kind}:{object_id}"


@runtime_checkable
class SessionStore(Protocol):
    """Ephemeral store contract. All methods are async so backends are interchangeable."""

    async def get(self, key: str) -> str | None:
        """Return the value, or ``None`` if absent or expired."""

    async def set(self, key: str, value: str, ttl_seconds: int) -> None:
        """Write a value with a mandatory TTL (seconds, must be > 0)."""

    async def delete(self, key: str) -> bool:
        """Delete one key. Returns whether it existed."""

    async def exists(self, key: str) -> bool: ...

    async def ttl(self, key: str) -> int | None:
        """Remaining lifetime in seconds, or ``None`` if the key is absent/expired."""

    async def expire(self, key: str, ttl_seconds: int) -> bool:
        """Reset the TTL of an existing key."""

    async def incr(self, key: str, ttl_seconds: int) -> int:
        """Atomically increment a counter, setting the TTL on creation. Used by rate limiting."""

    async def keys_in_namespace(self, namespace: str) -> list[str]:
        """List live keys beneath ``namespace``."""

    async def delete_namespace(self, namespace: str) -> int:
        """Delete every key beneath ``namespace``. Returns the number removed."""

    async def sweep(self) -> int:
        """Remove expired entries eagerly. Returns the number reclaimed."""

    async def ping(self) -> bool:
        """Liveness check for readiness probes."""

    async def close(self) -> None: ...
