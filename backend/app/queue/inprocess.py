"""In-process job queue: a bounded-concurrency ``asyncio`` worker pool, no extra infrastructure.

Dev-appropriate the same way ``MemorySessionStore`` is (ADR-0002): this environment has no Redis,
so async bulk work runs as ``asyncio`` tasks bounded by a semaphore rather than a separate worker
process. Retries are capped and apply uniformly - every screening pipeline stage (extract,
structure, redact, match) is idempotent given the same input bytes, so a retry is always safe to
attempt, never a risk of double-applying an effect.
"""

from __future__ import annotations

import asyncio
import time
from collections.abc import Awaitable, Callable

from app.core.metrics import metrics
from app.logging import get_logger
from app.queue.base import JobState, QueuedJob

logger = get_logger(__name__)

#: Retries apply only to idempotent stages, capped rather than unbounded (ARCHITECTURE.md
#: section 8) - one retry catches a transient hiccup without turning a genuinely broken input
#: into a long retry loop.
_MAX_RETRIES = 1
_RETRY_DELAY_SECONDS = 0.5


class InProcessJobQueue:
    """Bounded-concurrency ``asyncio`` task pool. One instance per running app process."""

    def __init__(self, max_concurrency: int) -> None:
        self._semaphore = asyncio.Semaphore(max_concurrency)
        self._jobs: dict[str, QueuedJob] = {}
        self._tasks: dict[str, asyncio.Task[None]] = {}
        self._jobs_by_session: dict[str, set[str]] = {}

    async def enqueue(
        self, job_id: str, work: Callable[[], Awaitable[None]], *, session_id: str | None = None
    ) -> None:
        self._jobs[job_id] = QueuedJob(job_id=job_id, state=JobState.PENDING)
        self._tasks[job_id] = asyncio.create_task(self._run(job_id, work))
        if session_id is not None:
            self._jobs_by_session.setdefault(session_id, set()).add(job_id)

    def get_state(self, job_id: str) -> QueuedJob | None:
        return self._jobs.get(job_id)

    async def cancel(self, job_id: str) -> None:
        task = self._tasks.get(job_id)
        if task is not None and not task.done():
            task.cancel()
        job = self._jobs.get(job_id)
        in_flight = (JobState.PENDING, JobState.PROCESSING, JobState.RETRYING)
        if job is not None and job.state in in_flight:
            self._jobs[job_id] = job.model_copy(
                update={"state": JobState.FAILED, "error": "cancelled"}
            )

    async def cancel_for_session(self, session_id: str) -> int:
        job_ids = self._jobs_by_session.pop(session_id, set())
        cancelled = 0
        in_flight = (JobState.PENDING, JobState.PROCESSING, JobState.RETRYING)
        for job_id in job_ids:
            job = self._jobs.get(job_id)
            if job is not None and job.state in in_flight:
                await self.cancel(job_id)
                cancelled += 1
        return cancelled

    def depth(self) -> int:
        in_flight = (JobState.PENDING, JobState.PROCESSING, JobState.RETRYING)
        return sum(1 for job in self._jobs.values() if job.state in in_flight)

    async def _run(self, job_id: str, work: Callable[[], Awaitable[None]]) -> None:
        async with self._semaphore:
            started = time.perf_counter()
            attempts = 0
            while True:
                attempts += 1
                self._set(job_id, JobState.PROCESSING, attempts=attempts)
                try:
                    await work()
                except asyncio.CancelledError:
                    raise
                except Exception:
                    if attempts <= _MAX_RETRIES:
                        logger.warning("queue.job_retrying", job_id=job_id, attempt=attempts)
                        metrics.increment("screening_jobs_retried_total")
                        self._set(
                            job_id, JobState.RETRYING, attempts=attempts, error="processing_failed"
                        )
                        await asyncio.sleep(_RETRY_DELAY_SECONDS)
                        continue
                    logger.warning("queue.job_failed", job_id=job_id, attempts=attempts)
                    metrics.increment("screening_jobs_total", status="failed")
                    metrics.observe_latency_ms(
                        "screening_job_duration_ms",
                        (time.perf_counter() - started) * 1000,
                        status="failed",
                    )
                    self._set(job_id, JobState.FAILED, attempts=attempts, error="processing_failed")
                    return
                else:
                    metrics.increment("screening_jobs_total", status="completed")
                    metrics.observe_latency_ms(
                        "screening_job_duration_ms",
                        (time.perf_counter() - started) * 1000,
                        status="completed",
                    )
                    self._set(job_id, JobState.COMPLETED, attempts=attempts)
                    return

    def _set(
        self, job_id: str, state: JobState, *, attempts: int, error: str | None = None
    ) -> None:
        self._jobs[job_id] = QueuedJob(job_id=job_id, state=state, attempts=attempts, error=error)
