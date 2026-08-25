"""Unit tests for app.queue.inprocess.InProcessJobQueue."""

from __future__ import annotations

import asyncio

from app.queue.base import JobState
from app.queue.inprocess import InProcessJobQueue


async def _wait_until_settled(
    queue: InProcessJobQueue, job_id: str, timeout_seconds: float = 2.0
) -> None:
    settled = {JobState.COMPLETED, JobState.FAILED}
    async with asyncio.timeout(timeout_seconds):
        while True:
            job = queue.get_state(job_id)
            if job is not None and job.state in settled:
                return
            await asyncio.sleep(0.01)


async def test_unknown_job_id_returns_none() -> None:
    queue = InProcessJobQueue(max_concurrency=2)
    assert queue.get_state("nope") is None


async def test_successful_job_completes() -> None:
    queue = InProcessJobQueue(max_concurrency=2)

    async def work() -> None:
        await asyncio.sleep(0.01)

    await queue.enqueue("j1", work)
    await _wait_until_settled(queue, "j1")
    job = queue.get_state("j1")
    assert job is not None
    assert job.state == JobState.COMPLETED
    assert job.attempts == 1
    assert job.error is None


async def test_failing_job_retries_once_then_fails() -> None:
    queue = InProcessJobQueue(max_concurrency=2)
    calls = 0

    async def always_fails() -> None:
        nonlocal calls
        calls += 1
        raise RuntimeError("boom - never surfaced")

    await queue.enqueue("j2", always_fails)
    await _wait_until_settled(queue, "j2")
    job = queue.get_state("j2")
    assert job is not None
    assert job.state == JobState.FAILED
    assert job.attempts == 2  # one retry, per _MAX_RETRIES = 1
    assert calls == 2
    # The error is a fixed, content-free category - never the raw exception message.
    assert job.error == "processing_failed"
    assert "boom" not in (job.error or "")


async def test_job_that_fails_once_then_succeeds_completes() -> None:
    queue = InProcessJobQueue(max_concurrency=2)
    attempts = 0

    async def flaky() -> None:
        nonlocal attempts
        attempts += 1
        if attempts == 1:
            raise RuntimeError("transient")

    await queue.enqueue("j3", flaky)
    await _wait_until_settled(queue, "j3")
    job = queue.get_state("j3")
    assert job is not None
    assert job.state == JobState.COMPLETED
    assert job.attempts == 2


async def test_concurrency_is_bounded() -> None:
    queue = InProcessJobQueue(max_concurrency=2)
    in_flight = 0
    max_observed = 0
    lock = asyncio.Lock()

    async def work() -> None:
        nonlocal in_flight, max_observed
        async with lock:
            in_flight += 1
            max_observed = max(max_observed, in_flight)
        await asyncio.sleep(0.05)
        async with lock:
            in_flight -= 1

    for i in range(6):
        await queue.enqueue(f"job-{i}", work)
    for i in range(6):
        await _wait_until_settled(queue, f"job-{i}")

    assert max_observed <= 2


async def test_cancel_marks_in_flight_job_failed() -> None:
    queue = InProcessJobQueue(max_concurrency=1)

    async def slow() -> None:
        await asyncio.sleep(5)

    await queue.enqueue("j4", slow)
    await asyncio.sleep(0.01)  # let it start
    await queue.cancel("j4")
    job = queue.get_state("j4")
    assert job is not None
    assert job.state == JobState.FAILED
    assert job.error == "cancelled"


async def test_cancel_unknown_job_is_a_no_op() -> None:
    queue = InProcessJobQueue(max_concurrency=1)
    await queue.cancel("does-not-exist")  # must not raise
