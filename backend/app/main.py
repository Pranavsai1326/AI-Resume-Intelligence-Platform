"""Application entrypoint and wiring."""

from __future__ import annotations

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api.v1 import api_router
from app.api.v1 import health as health_routes
from app.config import Settings, get_settings
from app.core.middleware import (
    GlobalRateLimitMiddleware,
    RequestContextMiddleware,
    SecurityHeadersMiddleware,
    register_exception_handlers,
)
from app.core.ratelimit import RateLimiter
from app.logging import configure_logging, get_logger
from app.queue.inprocess import InProcessJobQueue
from app.sessions.janitor import Janitor, startup_recovery
from app.sessions.manager import SessionManager
from app.sessions.memory import MemorySessionStore
from app.sessions.store import SessionStore

logger = get_logger(__name__)


def build_store(settings: Settings) -> SessionStore:
    """Select the ephemeral store backend (ADR-0002)."""
    if settings.session_store_backend == "redis":
        from app.sessions.redis_store import RedisSessionStore

        return RedisSessionStore.from_url(settings.redis_url)
    return MemorySessionStore()


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    settings: Settings = app.state.settings

    await startup_recovery(settings.temp_path)

    store = getattr(app.state, "session_store", None) or build_store(settings)
    app.state.session_store = store
    app.state.session_manager = SessionManager(
        store,
        idle_ttl_seconds=settings.session_idle_ttl_seconds,
        absolute_ttl_seconds=settings.session_absolute_ttl_seconds,
        release_grace_seconds=settings.session_release_grace_seconds,
    )
    app.state.rate_limiter = RateLimiter(store, enabled=settings.rate_limit_enabled)
    app.state.job_queue = InProcessJobQueue(settings.screening_worker_concurrency)

    janitor = Janitor(store, settings.temp_path, settings.janitor_interval_seconds)
    janitor.start()
    app.state.janitor = janitor

    logger.info(
        "app.started",
        environment=settings.app_env.value,
        store=settings.session_store_backend,
        idle_ttl=settings.session_idle_ttl_seconds,
        absolute_ttl=settings.session_absolute_ttl_seconds,
    )
    try:
        yield
    finally:
        await janitor.stop()
        await store.close()
        logger.info("app.stopped")


def create_app(settings: Settings | None = None) -> FastAPI:
    settings = settings or get_settings()
    settings.validate_runtime()
    configure_logging(level=settings.log_level, fmt=settings.log_format)

    app = FastAPI(
        title="AI Resume Intelligence Platform",
        version=settings.app_version,
        description=(
            "Accountless, zero-persistence resume intelligence. All user data lives in an "
            "ephemeral session and is destroyed when it expires."
        ),
        lifespan=lifespan,
        docs_url=None if settings.is_production else "/docs",
        redoc_url=None,
        openapi_url=None if settings.is_production else "/openapi.json",
    )
    app.state.settings = settings

    # Middleware runs bottom-up: request context is outermost so every response, including
    # rate-limit rejections, carries a request id.
    app.add_middleware(SecurityHeadersMiddleware, settings=settings)
    app.add_middleware(GlobalRateLimitMiddleware, settings=settings)
    app.add_middleware(RequestContextMiddleware)
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origins,
        allow_credentials=False,  # no cookies are used; the session id travels in a header
        allow_methods=["GET", "POST", "PUT", "PATCH", "DELETE", "OPTIONS"],
        allow_headers=["Content-Type", "X-Session-Id", "X-Request-Id", "Idempotency-Key"],
        expose_headers=["X-Request-Id", "Retry-After", "X-RateLimit-Remaining"],
        max_age=600,
    )

    register_exception_handlers(app)
    app.include_router(health_routes.router)
    app.include_router(api_router)
    return app


app = create_app()
