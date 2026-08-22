"""Injectable clock.

TTL correctness is a core guarantee, so it must be testable without real waiting. Everything
that reasons about time takes a :class:`Clock`; tests substitute :class:`FakeClock` and advance
it deliberately.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from typing import Protocol, runtime_checkable


@runtime_checkable
class Clock(Protocol):
    def now(self) -> datetime:
        """Current time, timezone-aware UTC."""

    def monotonic(self) -> float:
        """Monotonic seconds, immune to wall-clock adjustments. Used for TTL bookkeeping."""


class SystemClock:
    __slots__ = ()

    def now(self) -> datetime:
        return datetime.now(UTC)

    def monotonic(self) -> float:
        import time

        return time.monotonic()


class FakeClock:
    """Deterministic clock for tests."""

    __slots__ = ("_monotonic", "_now")

    def __init__(self, start: datetime | None = None) -> None:
        self._now = start or datetime(2026, 1, 1, 12, 0, 0, tzinfo=UTC)
        self._monotonic = 1_000.0

    def now(self) -> datetime:
        return self._now

    def monotonic(self) -> float:
        return self._monotonic

    def advance(self, seconds: float) -> None:
        self._now += timedelta(seconds=seconds)
        self._monotonic += seconds
