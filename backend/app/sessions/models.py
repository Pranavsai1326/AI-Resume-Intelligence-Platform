"""Session metadata.

Deliberately minimal: an opaque id and timestamps. There is no user, no profile, no identity,
and nothing here that could identify a person. ``counters`` holds operational integers only.
"""

from __future__ import annotations

import secrets
from datetime import datetime
from enum import StrEnum

from pydantic import BaseModel, ConfigDict, Field

#: 32 bytes = 256 bits of entropy, URL-safe. Opaque and unguessable; never a tracking identifier.
SESSION_ID_BYTES = 32


def generate_session_id() -> str:
    return secrets.token_urlsafe(SESSION_ID_BYTES)


class SessionMode(StrEnum):
    CANDIDATE = "candidate"
    RECRUITER = "recruiter"


class SessionCounters(BaseModel):
    """Operational counters. Numbers only - never content, never derived from personal data."""

    model_config = ConfigDict(extra="forbid")

    documents: int = 0
    analyses: int = 0
    ai_calls: int = 0
    ai_tokens: int = 0


class SessionMeta(BaseModel):
    model_config = ConfigDict(extra="forbid")

    session_id: str
    mode: SessionMode
    created_at: datetime
    last_activity_at: datetime
    #: Sliding idle deadline; refreshed by activity.
    expires_at: datetime
    #: Absolute deadline. Activity never extends this.
    hard_expires_at: datetime
    counters: SessionCounters = Field(default_factory=SessionCounters)
    #: Set when the client signalled that its page went away. Purely operational: it tells
    #: ``touch`` that object TTLs were collapsed and need restoring if the user comes back.
    released: bool = False

    def seconds_until(self, deadline: datetime, now: datetime) -> int:
        return max(0, int((deadline - now).total_seconds()))

    def remaining_lifetime(self, now: datetime) -> int:
        """Seconds until this session ends, whichever deadline arrives first."""
        return min(
            self.seconds_until(self.expires_at, now),
            self.seconds_until(self.hard_expires_at, now),
        )

    def is_expired(self, now: datetime) -> bool:
        return now >= self.expires_at or now >= self.hard_expires_at


class SessionPublic(BaseModel):
    """What the API returns. Mirrors SessionMeta plus client-friendly countdowns."""

    model_config = ConfigDict(extra="forbid")

    session_id: str
    mode: SessionMode
    created_at: datetime
    last_activity_at: datetime
    expires_at: datetime
    hard_expires_at: datetime
    idle_ttl_seconds: int
    absolute_ttl_seconds: int
    counters: SessionCounters

    @classmethod
    def from_meta(cls, meta: SessionMeta, now: datetime) -> SessionPublic:
        return cls(
            session_id=meta.session_id,
            mode=meta.mode,
            created_at=meta.created_at,
            last_activity_at=meta.last_activity_at,
            expires_at=meta.expires_at,
            hard_expires_at=meta.hard_expires_at,
            idle_ttl_seconds=meta.seconds_until(meta.expires_at, now),
            absolute_ttl_seconds=meta.seconds_until(meta.hard_expires_at, now),
            counters=meta.counters,
        )
