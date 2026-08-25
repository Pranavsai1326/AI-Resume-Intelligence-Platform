"""Unit tests for app.core.metrics."""

from __future__ import annotations

from app.core.metrics import MetricsRegistry, status_category


def test_increment_counts_by_label_set() -> None:
    registry = MetricsRegistry()
    registry.increment("requests_total", route="/v1/session", status="2xx")
    registry.increment("requests_total", route="/v1/session", status="2xx")
    registry.increment("requests_total", route="/v1/session", status="4xx")

    snapshot = registry.snapshot()
    assert snapshot["counters"]["requests_total{route=/v1/session,status=2xx}"] == 2
    assert snapshot["counters"]["requests_total{route=/v1/session,status=4xx}"] == 1


def test_increment_by_custom_amount() -> None:
    registry = MetricsRegistry()
    registry.increment("candidates_total", by=5, status="completed")
    snapshot = registry.snapshot()
    assert snapshot["counters"]["candidates_total{status=completed}"] == 5


def test_latency_averages_across_observations() -> None:
    registry = MetricsRegistry()
    registry.observe_latency_ms("request_duration_ms", 10.0, route="/v1/session")
    registry.observe_latency_ms("request_duration_ms", 30.0, route="/v1/session")

    snapshot = registry.snapshot()
    entry = snapshot["latencies"]["request_duration_ms{route=/v1/session}"]
    assert entry == {"count": 2, "avg_ms": 20.0}


def test_different_label_sets_are_independent() -> None:
    registry = MetricsRegistry()
    registry.increment("x", route="/a")
    registry.increment("x", route="/b")
    snapshot = registry.snapshot()
    assert snapshot["counters"]["x{route=/a}"] == 1
    assert snapshot["counters"]["x{route=/b}"] == 1


def test_no_labels_formats_as_bare_name() -> None:
    registry = MetricsRegistry()
    registry.increment("startups_total")
    snapshot = registry.snapshot()
    assert snapshot["counters"]["startups_total"] == 1


def test_reset_clears_everything() -> None:
    registry = MetricsRegistry()
    registry.increment("x")
    registry.observe_latency_ms("y", 5.0)
    registry.reset()
    snapshot = registry.snapshot()
    assert snapshot["counters"] == {}
    assert snapshot["latencies"] == {}


def test_status_category_buckets() -> None:
    assert status_category(200) == "2xx"
    assert status_category(201) == "2xx"
    assert status_category(302) == "3xx"
    assert status_category(404) == "4xx"
    assert status_category(429) == "4xx"
    assert status_category(500) == "5xx"
    assert status_category(503) == "5xx"
