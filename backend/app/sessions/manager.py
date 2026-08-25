"""Session lifecycle.

Enforces the model documented in ARCHITECTURE.md section 4:

* sliding idle TTL, refreshed by activity;
* an absolute lifetime that activity can never extend;
* a TTL on every object, capped at the session's own remaining lifetime, so nothing a session
  owns can outlive it;
* namespace deletion, so ending a session leaves no orphans.
"""

from __future__ import annotations

from datetime import datetime, timedelta

from app.core.clock import Clock, SystemClock
from app.core.errors import SessionExpiredError
from app.sessions.models import (
    SessionCounters,
    SessionMeta,
    SessionMode,
    generate_session_id,
)
from app.sessions.store import SessionStore, meta_key, object_key, session_namespace


class SessionManager:
    __slots__ = ("_absolute_ttl", "_clock", "_idle_ttl", "_release_grace", "_store")

    def __init__(
        self,
        store: SessionStore,
        *,
        idle_ttl_seconds: int,
        absolute_ttl_seconds: int,
        release_grace_seconds: int = 120,
        clock: Clock | None = None,
    ) -> None:
        self._store = store
        self._clock = clock or SystemClock()
        self._idle_ttl = idle_ttl_seconds
        self._absolute_ttl = absolute_ttl_seconds
        self._release_grace = release_grace_seconds

    @property
    def store(self) -> SessionStore:
        return self._store

    def now(self) -> datetime:
        return self._clock.now()

    # -- lifecycle -----------------------------------------------------------------------

    async def create(self, mode: SessionMode) -> SessionMeta:
        now = self._clock.now()
        meta = SessionMeta(
            session_id=generate_session_id(),
            mode=mode,
            created_at=now,
            last_activity_at=now,
            expires_at=now + timedelta(seconds=self._idle_ttl),
            hard_expires_at=now + timedelta(seconds=self._absolute_ttl),
            counters=SessionCounters(),
        )
        await self._persist(meta, now)
        return meta

    async def get(self, session_id: str) -> SessionMeta | None:
        """Resolve a session, destroying and reporting it as gone once either deadline passes.

        Returns ``None`` for unknown, expired or malformed ids - callers translate that into a
        single ``SESSION_EXPIRED`` response so an attacker cannot distinguish the cases.
        """
        if not session_id:
            return None
        raw = await self._store.get(meta_key(session_id))
        if raw is None:
            return None
        try:
            meta = SessionMeta.model_validate_json(raw)
        except ValueError:
            await self.destroy(session_id)
            return None

        now = self._clock.now()
        if meta.is_expired(now):
            # Belt and braces: the store TTL should already have removed this, but a clock
            # skew or a backend that rounds TTLs must never resurrect an expired session.
            await self.destroy(session_id)
            return None
        return meta

    async def require(self, session_id: str) -> SessionMeta:
        meta = await self.get(session_id)
        if meta is None:
            raise SessionExpiredError
        return meta

    async def touch(self, meta: SessionMeta) -> SessionMeta:
        """Record activity and slide the idle deadline - never past the absolute deadline."""
        now = self._clock.now()
        candidate = now + timedelta(seconds=self._idle_ttl)
        updated = meta.model_copy(
            update={
                "last_activity_at": now,
                "expires_at": min(candidate, meta.hard_expires_at),
                "released": False,
            }
        )
        await self._persist(updated, now)
        if meta.released:
            # The user came back inside the grace window: restore the object TTLs that
            # `release` collapsed. Only done on this rare path, never on every request.
            await self._reset_object_ttls(updated, now)
        return updated

    async def increment_counter(self, meta: SessionMeta, field: str, by: int = 1) -> SessionMeta:
        """Bump an operational counter and persist it.

        Counters are numbers only - never content - so incrementing one is not a privacy-
        sensitive write, just session bookkeeping (documents processed, AI calls made).
        """
        current = getattr(meta.counters, field)
        updated_counters = meta.counters.model_copy(update={field: current + by})
        updated = meta.model_copy(update={"counters": updated_counters})
        await self._persist(updated, self._clock.now())
        return updated

    async def release(self, session_id: str) -> bool:
        """Collapse a session to a short grace window because its page went away.

        Called from the tab-teardown beacon. Deliberately not a destroy: `pagehide` also fires
        on a reload and on ordinary navigation, so destroying here would throw away the user's
        work every time they pressed refresh. Collapsing the deadline instead keeps the cleanup
        benefit for a genuinely closed tab - the session dies in minutes rather than an hour -
        while a page that comes back simply resumes it.

        Like every other client-side signal, this is an optimisation: if it never arrives, the
        ordinary idle TTL still expires the session.
        """
        meta = await self.get(session_id)
        if meta is None:
            return False

        now = self._clock.now()
        grace_deadline = min(
            now + timedelta(seconds=self._release_grace), meta.hard_expires_at
        )
        if grace_deadline >= meta.expires_at:
            # Already closer to expiry than the grace window; nothing to shorten.
            return True

        released = meta.model_copy(update={"expires_at": grace_deadline, "released": True})
        await self._persist(released, now)

        # Objects carry their own TTLs, so they must be shortened too - otherwise they would
        # outlive the session that owns them.
        grace = max(1, released.remaining_lifetime(now))
        for key in await self._store.keys_in_namespace(session_namespace(session_id)):
            if key != meta_key(session_id):
                await self._store.expire(key, grace)
        return True

    async def _reset_object_ttls(self, meta: SessionMeta, now: datetime) -> None:
        ttl = max(1, meta.remaining_lifetime(now))
        for key in await self._store.keys_in_namespace(session_namespace(meta.session_id)):
            if key != meta_key(meta.session_id):
                await self._store.expire(key, ttl)

    async def destroy(self, session_id: str) -> int:
        """Delete the session and every object beneath its namespace."""
        if not session_id:
            return 0
        return await self._store.delete_namespace(session_namespace(session_id))

    async def _persist(self, meta: SessionMeta, now: datetime) -> None:
        ttl = meta.remaining_lifetime(now)
        if ttl <= 0:
            await self.destroy(meta.session_id)
            raise SessionExpiredError
        await self._store.set(meta_key(meta.session_id), meta.model_dump_json(), ttl)

    # -- session-scoped objects ----------------------------------------------------------

    async def put_object(
        self,
        meta: SessionMeta,
        kind: str,
        object_id: str,
        value: str,
        *,
        ttl_seconds: int | None = None,
    ) -> None:
        """Store a session-owned object.

        The TTL is always capped at the session's remaining lifetime, so no object can outlive
        the session that owns it even if a caller asks for longer.
        """
        remaining = meta.remaining_lifetime(self._clock.now())
        if remaining <= 0:
            raise SessionExpiredError
        ttl = remaining if ttl_seconds is None else min(ttl_seconds, remaining)
        await self._store.set(object_key(meta.session_id, kind, object_id), value, max(1, ttl))

    async def get_object(self, meta: SessionMeta, kind: str, object_id: str) -> str | None:
        return await self._store.get(object_key(meta.session_id, kind, object_id))

    async def delete_object(self, meta: SessionMeta, kind: str, object_id: str) -> bool:
        return await self._store.delete(object_key(meta.session_id, kind, object_id))

    async def list_object_keys(self, meta: SessionMeta) -> list[str]:
        return await self._store.keys_in_namespace(session_namespace(meta.session_id))
