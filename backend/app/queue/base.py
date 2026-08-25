"""Async job queue abstraction (ARCHITECTURE.md section 8).

Bulk screening must never run inside an HTTP request - a candidate pool of up to
``settings.max_bulk_resumes`` resumes each need extraction, structuring, redaction and matching,
which is real work a request/response cycle should not block on. ``enqueue`` returns immediately;
the caller polls ``get_state`` until the job leaves ``PENDING``/``PROCESSING``/``RETRYING``.

Only one implementation exists so far (``InProcessJobQueue``, dev-appropriate: no Redis, no extra
process). A production ARQ + Redis implementation is future work behind the same ``JobQueue``
protocol, matching the pattern already used for the session store (ADR-0002) and embeddings
(ADR-0005) - callers never import a concrete queue, only this interface.
"""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from enum import StrEnum
from typing import Protocol

from pydantic import BaseModel, ConfigDict


class JobState(StrEnum):
    PENDING = "pending"
    PROCESSING = "processing"
    COMPLETED = "completed"
    FAILED = "failed"
    RETRYING = "retrying"


#: States a job can still transition out of - used by status aggregation and cancellation.
IN_FLIGHT_STATES = frozenset({JobState.PENDING, JobState.PROCESSING, JobState.RETRYING})


class QueuedJob(BaseModel):
    model_config = ConfigDict(extra="forbid")

    job_id: str
    state: JobState
    attempts: int = 0
    #: A short, content-free failure category - never the underlying exception message, which
    #: could carry resume content through a stack trace or a library's error string
    #: (SECURITY.md section 4 - no provider/library details ever reach a client or a log).
    error: str | None = None


class JobQueue(Protocol):
    async def enqueue(
        self, job_id: str, work: Callable[[], Awaitable[None]], *, session_id: str | None = None
    ) -> None:
        """Schedule ``work`` to run under the queue's concurrency bound. Returns immediately.

        ``session_id``, when given, lets ``cancel_for_session`` find this job later - the queue
        itself has no other notion of which session owns a job.
        """

    def get_state(self, job_id: str) -> QueuedJob | None:
        """``None`` if no job with this id was ever enqueued on this queue instance."""

    async def cancel(self, job_id: str) -> None:
        """Best-effort cancellation - a job already past its work is left as it finished."""

    async def cancel_for_session(self, session_id: str) -> int:
        """Cancel every still-in-flight job enqueued with this ``session_id``.

        Called from session destruction (``DELETE /v1/session``) so a candidate job does not
        keep running, and potentially keep writing, after the session that owns it is gone.
        Returns the number of jobs actually cancelled.
        """

    def depth(self) -> int:
        """Count of jobs currently PENDING, PROCESSING, or RETRYING across every session -
        a content-free operational gauge (ARCHITECTURE.md section 10), never per-session detail.
        """
