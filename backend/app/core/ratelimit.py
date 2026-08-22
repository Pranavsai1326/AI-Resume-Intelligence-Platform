"""Rate limiting.

A fixed-window counter over the ephemeral store, so it works identically on the in-memory
backend (development, no infrastructure) and on Redis (production, shared across instances).
Counter keys hold integers with their own TTL and expire on their own; nothing accumulates.

Client identity for anonymous traffic is the IP address, hashed so raw addresses never reach
the store or the logs.
"""

from __future__ import annotations

import hashlib
from dataclasses import dataclass

from app.core.errors import RateLimitedError
from app.sessions.store import SessionStore


@dataclass(frozen=True, slots=True)
class RateLimitRule:
    name: str
    limit: int
    window_seconds: int


@dataclass(frozen=True, slots=True)
class RateLimitResult:
    allowed: bool
    remaining: int
    retry_after: int
    limit: int


def hash_identity(value: str) -> str:
    """Short, non-reversible identity for rate-limit keys.

    IP addresses are personal data; a truncated digest is enough to bucket requests without
    storing or logging the address itself.
    """
    return hashlib.blake2b(value.encode("utf-8"), digest_size=8).hexdigest()


class RateLimiter:
    """Fixed-window limiter backed by the ephemeral store."""

    __slots__ = ("_enabled", "_store")

    def __init__(self, store: SessionStore, *, enabled: bool = True) -> None:
        self._store = store
        self._enabled = enabled

    async def check(self, rule: RateLimitRule, identity: str) -> RateLimitResult:
        if not self._enabled:
            return RateLimitResult(True, rule.limit, 0, rule.limit)

        key = f"rl:{rule.name}:{hash_identity(identity)}"
        try:
            count = await self._store.incr(key, rule.window_seconds)
        except Exception:
            return RateLimitResult(True, rule.limit, 0, rule.limit)

        if count > rule.limit:
            retry_after = await self._store.ttl(key) or rule.window_seconds
            return RateLimitResult(False, 0, max(1, retry_after), rule.limit)
        return RateLimitResult(True, max(0, rule.limit - count), 0, rule.limit)

    async def enforce(self, rule: RateLimitRule, identity: str) -> RateLimitResult:
        result = await self.check(rule, identity)
        if not result.allowed:
            raise RateLimitedError(result.retry_after)
        return result
