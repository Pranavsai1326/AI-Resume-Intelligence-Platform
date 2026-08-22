"""FastAPI dependencies.

Session resolution happens here and only here. Every downstream handler receives an already
validated :class:`SessionMeta`; no handler ever reads a caller-supplied key, namespace or path,
which is what makes cross-session access impossible by construction.
"""

from __future__ import annotations

from typing import Annotated

from fastapi import Depends, Header, Request

from app.config import Settings
from app.core.errors import SessionRequiredError
from app.core.ratelimit import RateLimiter
from app.sessions.manager import SessionManager
from app.sessions.models import SessionMeta


def get_app_settings(request: Request) -> Settings:
    """Settings of the running application.

    Deliberately *not* ``config.get_settings()``: that returns the process-global cached
    instance, which would silently ignore the configuration an app was constructed with and
    make per-request limits differ from what the deployment actually configured.
    """
    settings: Settings = request.app.state.settings
    return settings


def get_session_manager(request: Request) -> SessionManager:
    manager: SessionManager = request.app.state.session_manager
    return manager


def get_rate_limiter(request: Request) -> RateLimiter:
    limiter: RateLimiter = request.app.state.rate_limiter
    return limiter


SettingsDep = Annotated[Settings, Depends(get_app_settings)]
SessionManagerDep = Annotated[SessionManager, Depends(get_session_manager)]
RateLimiterDep = Annotated[RateLimiter, Depends(get_rate_limiter)]


async def require_session(
    manager: SessionManagerDep,
    x_session_id: Annotated[str | None, Header(alias="X-Session-Id")] = None,
) -> SessionMeta:
    """Resolve the caller's session or fail.

    A missing header is a client mistake (400). An unknown, malformed or expired id is reported
    uniformly as 410 SESSION_EXPIRED so the three cases are indistinguishable to a prober.
    """
    if not x_session_id:
        raise SessionRequiredError
    return await manager.require(x_session_id)


async def require_active_session(
    manager: SessionManagerDep,
    session: Annotated[SessionMeta, Depends(require_session)],
) -> SessionMeta:
    """Resolve the session and record activity, sliding the idle deadline."""
    return await manager.touch(session)


SessionDep = Annotated[SessionMeta, Depends(require_session)]
ActiveSessionDep = Annotated[SessionMeta, Depends(require_active_session)]
