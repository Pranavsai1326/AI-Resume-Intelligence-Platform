"""Health and readiness probes.

``/health`` answers whether the process is alive and checks nothing else, so it stays useful
when a dependency is degraded. ``/ready`` checks the dependencies traffic actually needs and
publishes an honest capability map the frontend uses to disable features it cannot deliver -
rather than offering them and faking a result.
"""

from __future__ import annotations

from fastapi import APIRouter, Request, Response, status
from pydantic import BaseModel, ConfigDict

from app.core.deps import SessionManagerDep, SettingsDep

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
