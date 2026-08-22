"""Session endpoints.

No signup, no login, no identity: ``POST /v1/session`` hands back an opaque id and the session
exists until it expires or is destroyed.
"""

from __future__ import annotations

import json

from fastapi import APIRouter, Request, Response, status
from pydantic import BaseModel, ConfigDict

from app.core.deps import ActiveSessionDep, RateLimiterDep, SessionManagerDep, SettingsDep
from app.core.middleware import client_identity
from app.core.ratelimit import RateLimitRule
from app.logging import get_logger
from app.sessions.models import SessionMode, SessionPublic

logger = get_logger(__name__)
router = APIRouter(prefix="/session", tags=["session"])


class CreateSessionRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    mode: SessionMode = SessionMode.CANDIDATE


@router.post("", status_code=status.HTTP_201_CREATED, response_model=SessionPublic)
async def create_session(
    payload: CreateSessionRequest,
    request: Request,
    manager: SessionManagerDep,
    limiter: RateLimiterDep,
    settings: SettingsDep,
) -> SessionPublic:
    """Create an ephemeral session. Requires no input beyond the mode."""
    await limiter.enforce(
        RateLimitRule(
            "session_create", settings.rate_limit_session_create_per_hour, 3600
        ),
        client_identity(request, trust_proxy=settings.trust_proxy),
    )
    meta = await manager.create(payload.mode)
    logger.info("session.created", mode=meta.mode.value)
    return SessionPublic.from_meta(meta, manager.now())


@router.get("", response_model=SessionPublic)
async def get_session(session: ActiveSessionDep, manager: SessionManagerDep) -> SessionPublic:
    """Return session metadata. Counts as activity, so it slides the idle deadline."""
    return SessionPublic.from_meta(session, manager.now())


@router.post("/heartbeat", response_model=SessionPublic)
async def heartbeat(session: ActiveSessionDep, manager: SessionManagerDep) -> SessionPublic:
    """Extend the idle TTL. Never extends the absolute lifetime."""
    return SessionPublic.from_meta(session, manager.now())


@router.delete("", status_code=status.HTTP_204_NO_CONTENT)
async def delete_session(
    request: Request, manager: SessionManagerDep
) -> Response:
    """Destroy the session and everything beneath its namespace.

    Idempotent and always 204: a client tearing down should never see an error, and the reply
    must not reveal whether the id existed.
    """
    session_id = request.headers.get("x-session-id", "")
    removed = await manager.destroy(session_id)
    logger.info("session.destroyed", objects_removed=removed, trigger="explicit")
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.post("/release", status_code=status.HTTP_204_NO_CONTENT)
async def release_session(request: Request, manager: SessionManagerDep) -> Response:
    """Signal that the client's page went away, shortening the session to a grace window.

    ``navigator.sendBeacon`` cannot set custom headers, and an ``application/json`` content type
    would trigger a CORS preflight that an unloading page may never complete. So the id arrives
    in a body sent as ``text/plain`` (a CORS-safelisted type), parsed here.

    This shortens rather than destroys, because ``pagehide`` also fires on a plain reload:
    destroying here would discard the user's work every time they refreshed. A page that comes
    back within the grace window resumes the session; a tab that is really gone is cleaned up in
    minutes instead of an hour.

    An optimisation only - TTL expiry, the janitor and startup recovery all still apply if this
    never runs. Always returns 204, revealing nothing about whether the id existed.
    """
    session_id = ""
    try:
        raw = (await request.body()).decode("utf-8", errors="ignore")[:4096]
        if raw:
            parsed = json.loads(raw)
            if isinstance(parsed, dict):
                session_id = str(parsed.get("session_id") or "")
    except (ValueError, UnicodeDecodeError):
        session_id = ""

    if session_id:
        released = await manager.release(session_id)
        logger.info("session.released", found=released, trigger="beacon")
    return Response(status_code=status.HTTP_204_NO_CONTENT)
