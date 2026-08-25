"""In-process, content-free operational metrics (ARCHITECTURE.md section 10).

No external metrics backend is configured in this environment (no Prometheus, no StatsD, no
CloudWatch) - this is a minimal in-process registry, exposed as JSON via ``GET /metrics``, not a
Prometheus exporter. Wiring a real exporter behind the same recording calls is Phase 9 work.

Every label comes from a fixed, closed set the caller controls (a route template, an HTTP status
category, a job state) - user content can never become a label value
(PRIVACY_ARCHITECTURE.md section 9, "metric labels are drawn from a fixed enum"). Nothing here
ever receives resume text, a filename, or any other free-form string.
"""

from __future__ import annotations

import threading
from collections import defaultdict

_LabelKey = tuple[tuple[str, str], ...]


def _label_key(labels: dict[str, str]) -> _LabelKey:
    return tuple(sorted(labels.items()))


def _format_key(name: str, labels: _LabelKey) -> str:
    if not labels:
        return name
    return name + "{" + ",".join(f"{k}={v}" for k, v in labels) + "}"


class MetricsRegistry:
    """Thread-safe (the in-process job queue's worker threads may record concurrently)."""

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._counters: dict[tuple[str, _LabelKey], int] = defaultdict(int)
        self._latency_sum_ms: dict[tuple[str, _LabelKey], float] = defaultdict(float)
        self._latency_count: dict[tuple[str, _LabelKey], int] = defaultdict(int)

    def increment(self, name: str, by: int = 1, **labels: str) -> None:
        key = (name, _label_key(labels))
        with self._lock:
            self._counters[key] += by

    def observe_latency_ms(self, name: str, duration_ms: float, **labels: str) -> None:
        key = (name, _label_key(labels))
        with self._lock:
            self._latency_sum_ms[key] += duration_ms
            self._latency_count[key] += 1

    def snapshot(self) -> dict[str, dict[str, object]]:
        """A content-free point-in-time view - counters and average latency per label set."""
        with self._lock:
            counters: dict[str, object] = {
                _format_key(name, labels): value for (name, labels), value in self._counters.items()
            }
            latencies: dict[str, object] = {}
            for key, total_ms in self._latency_sum_ms.items():
                name, labels = key
                count = self._latency_count[key]
                avg_ms = round(total_ms / count, 2) if count else 0.0
                latencies[_format_key(name, labels)] = {"count": count, "avg_ms": avg_ms}
            return {"counters": counters, "latencies": latencies}

    def reset(self) -> None:
        """Test-only: clears all recorded data so tests don't see another test's counters."""
        with self._lock:
            self._counters.clear()
            self._latency_sum_ms.clear()
            self._latency_count.clear()


#: One process-wide registry, matching the rate limiter and job queue's own one-per-process
#: model - metrics describe this running process, not a distributed count.
metrics = MetricsRegistry()


def status_category(status_code: int) -> str:
    """Coarse-grained bucket for a status code - never the raw code as a label on its own,
    which would create an unbounded label cardinality as new specific codes appear."""
    if status_code < 300:
        return "2xx"
    if status_code < 400:
        return "3xx"
    if status_code < 500:
        return "4xx"
    return "5xx"
