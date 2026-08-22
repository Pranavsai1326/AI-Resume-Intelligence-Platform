"""Redis-backed ephemeral store (production backend).

Same contract as the in-memory backend, verified by the same conformance suite. Redis is not
required for development and is imported lazily so the package stays optional.

Namespace deletion uses a per-session index set rather than ``SCAN MATCH``, which would be
O(keyspace) on every session teardown. The index's own TTL is only ever extended (``EXPIRE ...
GT``) so it always outlives its longest-lived member; stale members are harmless because
deleting an already-expired key is a no-op.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from app.sessions.store import SESSION_PREFIX

if TYPE_CHECKING:  # pragma: no cover - typing only
    from redis.asyncio import Redis

INDEX_SUFFIX = "__index"


def _as_str(value: bytes | str) -> str:
    """Normalise a Redis reply to text.

    The client is constructed with ``decode_responses=True``, but a caller may inject one that
    is not, so decoding here keeps the store correct either way.
    """
    return value.decode("utf-8") if isinstance(value, bytes) else value


def _namespace_of(key: str) -> str | None:
    """Return the session namespace a key belongs to, if any."""
    parts = key.split(":", 2)
    if len(parts) >= 2 and parts[0] == SESSION_PREFIX:
        return f"{parts[0]}:{parts[1]}"
    return None


class RedisSessionStore:
    __slots__ = ("_redis",)

    def __init__(self, redis: Redis) -> None:
        self._redis = redis

    @classmethod
    def from_url(cls, url: str, **kwargs: Any) -> RedisSessionStore:
        from redis.asyncio import Redis as AsyncRedis

        return cls(AsyncRedis.from_url(url, decode_responses=True, **kwargs))

    @staticmethod
    def _check_ttl(ttl_seconds: int) -> None:
        if ttl_seconds <= 0:
            raise ValueError("ttl_seconds must be positive: every stored value must expire")

    async def _index(self, key: str, ttl_seconds: int) -> None:
        namespace = _namespace_of(key)
        if namespace is None or key.endswith(INDEX_SUFFIX):
            return
        index_key = f"{namespace}:{INDEX_SUFFIX}"
        pipe = self._redis.pipeline()
        pipe.sadd(index_key, key)
        # GT: never shorten the index lifetime below that of its longest-lived member.
        pipe.expire(index_key, ttl_seconds, gt=True)
        pipe.expire(index_key, ttl_seconds, nx=True)
        await pipe.execute()

    # -- SessionStore --------------------------------------------------------------------

    async def get(self, key: str) -> str | None:
        value: bytes | str | None = await self._redis.get(key)
        return None if value is None else _as_str(value)

    async def set(self, key: str, value: str, ttl_seconds: int) -> None:
        self._check_ttl(ttl_seconds)
        await self._redis.set(key, value, ex=ttl_seconds)
        await self._index(key, ttl_seconds)

    async def delete(self, key: str) -> bool:
        return bool(await self._redis.delete(key))

    async def exists(self, key: str) -> bool:
        return bool(await self._redis.exists(key))

    async def ttl(self, key: str) -> int | None:
        value = await self._redis.ttl(key)
        # -2: key does not exist. -1: exists without TTL, which this store never creates.
        return None if value < 0 else int(value)

    async def expire(self, key: str, ttl_seconds: int) -> bool:
        self._check_ttl(ttl_seconds)
        changed = bool(await self._redis.expire(key, ttl_seconds))
        if changed:
            await self._index(key, ttl_seconds)
        return changed

    async def incr(self, key: str, ttl_seconds: int) -> int:
        self._check_ttl(ttl_seconds)
        pipe = self._redis.pipeline()
        pipe.incr(key)
        pipe.expire(key, ttl_seconds, nx=True)
        result = await pipe.execute()
        await self._index(key, ttl_seconds)
        return int(result[0])

    async def keys_in_namespace(self, namespace: str) -> list[str]:
        index_key = f"{namespace}:{INDEX_SUFFIX}"
        members = {_as_str(member) for member in await self._redis.smembers(index_key)}
        if not members:
            return []
        ordered = sorted(members)
        pipe = self._redis.pipeline()
        for member in ordered:
            pipe.exists(member)
        alive = await pipe.execute()
        return [key for key, is_alive in zip(ordered, alive, strict=True) if is_alive]

    async def delete_namespace(self, namespace: str) -> int:
        index_key = f"{namespace}:{INDEX_SUFFIX}"
        members = {_as_str(member) for member in await self._redis.smembers(index_key)}
        targets = [*members, index_key]
        removed = int(await self._redis.delete(*targets)) if targets else 0
        # Subtract the index key itself so callers get a count of session objects removed.
        return max(0, removed - 1) if members else 0

    async def sweep(self) -> int:
        # Redis expires keys itself; nothing to reclaim. Reported as zero rather than faked.
        return 0

    async def ping(self) -> bool:
        try:
            return bool(await self._redis.ping())
        except Exception:
            return False

    async def close(self) -> None:
        await self._redis.aclose()
