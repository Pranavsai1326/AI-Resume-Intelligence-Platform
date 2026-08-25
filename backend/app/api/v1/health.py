"""Health, readiness, and operational metrics.

``/health`` answers whether the process is alive and checks nothing else, so it stays useful
when a dependency is degraded. ``/ready`` checks the dependencies traffic actually needs and
publishes an honest capability map the frontend uses to disable features it cannot deliver -
rather than offering them and faking a result. ``/metrics`` exposes the in-process, content-free
counters and latency stats ``app.core.metrics`` collects (ARCHITECTURE.md section 10) - JSON, not
a Prometheus exporter, since no metrics backend is configured in this environment yet.
"""

from __future__ import annotations

from fastapi import APIRouter, Request, Response, status
from pydantic import BaseModel, ConfigDict

from app.core.deps import JobQueueDep, SessionManagerDep, SettingsDep
from app.core.metrics import metrics

router = APIRouter(tags=["health"])


class HealthResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    status: str
    version: str
    environment: str


class ReadyResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    ready: bool
    session_store: str
    session_store_reachable: bool
    capabilities: dict[str, bool]


@router.get("/health", response_model=HealthResponse)
async def health(settings: SettingsDep) -> HealthResponse:
    return HealthResponse(
        status="ok", version=settings.app_version, environment=settings.app_env.value
    )


@router.get("/ready", response_model=ReadyResponse)
async def ready(
    request: Request,
    response: Response,
    settings: SettingsDep,
    manager: SessionManagerDep,
) -> ReadyResponse:
    reachable = await manager.store.ping()
    if not reachable:
        response.status_code = status.HTTP_503_SERVICE_UNAVAILABLE
    return ReadyResponse(
        ready=reachable,
        session_store=settings.session_store_backend,
        session_store_reachable=reachable,
        capabilities=settings.capabilities(),
    )


class MetricsResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    #: PENDING/PROCESSING/RETRYING screening jobs across every session right now.
    queue_depth: int
    #: "http_requests_total{route=...,status=...}" -> count.
    counters: dict[str, object]
    #: "http_request_duration_ms{route=...}" -> {count, avg_ms}.
    latencies: dict[str, object]


@router.get("/metrics", response_model=MetricsResponse)
async def metrics_endpoint(
    settings: SettingsDep, queue: JobQueueDep, response: Response
) -> MetricsResponse | Response:
    """Not exposed in production - no auth layer exists in this app to gate it behind, and
    route-level latency data is internal operational detail, not something to serve to an
    anonymous caller. A production deployment should scrape this from an internal network path
    (reverse proxy allowlist) once a real exporter replaces this JSON endpoint (Phase 9)."""
    if settings.is_production:
        response.status_code = status.HTTP_404_NOT_FOUND
        return response
    snapshot = metrics.snapshot()
    return MetricsResponse(
        queue_depth=queue.depth(),
        counters=snapshot["counters"],
        latencies=snapshot["latencies"],
    )
