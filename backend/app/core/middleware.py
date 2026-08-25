"""Request middleware and exception handlers.

Responsibilities: correlation ids, security headers, access logging that carries no user
content, global rate limiting, and turning every exception into the sanitised envelope defined
in API.md. Nothing here ever emits a stack trace, a filesystem path or a provider detail to a
client.
"""

from __future__ import annotations

import re
import secrets
import time
from collections.abc import Awaitable, Callable

from fastapi import FastAPI, Request, Response
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException as StarletteHTTPException
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.types import ASGIApp

from app.config import Settings
from app.core.errors import AppError, ErrorCategory, RateLimitedError, ValidationFailedError
from app.core.metrics import metrics, status_category
from app.core.ratelimit import RateLimitRule
from app.logging import get_logger, request_id_var, session_id_var

logger = get_logger(__name__)

RequestHandler = Callable[[Request], Awaitable[Response]]

#: Paths exempt from the global limiter: probes must stay answerable under load.
_RATE_LIMIT_EXEMPT = frozenset({"/health", "/ready", "/openapi.json", "/docs", "/redoc"})

#: Correlation ids are echoed into logs and response headers, so an inbound one is treated as
#: untrusted: bounded length, conservative charset, no header injection, no smuggled content.
_REQUEST_ID_RE = re.compile(r"^[A-Za-z0-9._-]{1,64}$")


def sanitize_request_id(candidate: str | None) -> str | None:
    if candidate and _REQUEST_ID_RE.match(candidate):
        return candidate
    return None


def client_identity(request: Request, *, trust_proxy: bool) -> str:
    """Best-effort client identity for rate limiting.

    ``X-Forwarded-For`` is only honoured when the deployment declares it sits behind a trusted
    proxy; otherwise any client could spoof its identity and bypass limits.
    """
    if trust_proxy:
        forwarded = request.headers.get("x-forwarded-for")
        if forwarded:
            return forwarded.split(",")[0].strip()
    return request.client.host if request.client else "unknown"


class RequestContextMiddleware(BaseHTTPMiddleware):
    """Assign a request id, bind logging context, and emit one content-free access log."""

    async def dispatch(self, request: Request, call_next: RequestHandler) -> Response:
        request_id = sanitize_request_id(
            request.headers.get("x-request-id")
        ) or secrets.token_hex(8)
        request_id_token = request_id_var.set(request_id)
        session_token = session_id_var.set(request.headers.get("x-session-id"))
        request.state.request_id = request_id
        started = time.perf_counter()

        # The context must stay bound until the access log is written, otherwise the one line
        # that describes the request is the only line without its correlation ids.
        try:
            route = _route_of(request)
            try:
                response = await call_next(request)
            except Exception:
                duration_ms = round((time.perf_counter() - started) * 1000, 2)
                # Log the category only; the handler produces the client-safe payload.
                logger.error(
                    "request.unhandled", method=request.method, route=route, duration_ms=duration_ms
                )
                metrics.increment("http_requests_total", route=route, status="5xx")
                metrics.observe_latency_ms("http_request_duration_ms", duration_ms, route=route)
                raise

            duration_ms = round((time.perf_counter() - started) * 1000, 2)
            response.headers["X-Request-Id"] = request_id
            logger.info(
                "request.completed",
                method=request.method,
                route=route,
                status=response.status_code,
                duration_ms=duration_ms,
            )
            metrics.increment(
                "http_requests_total", route=route, status=status_category(response.status_code)
            )
            metrics.observe_latency_ms("http_request_duration_ms", duration_ms, route=route)
            return response
        finally:
            request_id_var.reset(request_id_token)
            session_id_var.reset(session_token)


def _route_of(request: Request) -> str:
    """Route template, not the raw URL - raw paths can carry identifiers we must not log."""
    route = request.scope.get("route")
    path_format = getattr(route, "path_format", None)
    return path_format or request.url.path


class SecurityHeadersMiddleware(BaseHTTPMiddleware):
    """Apply hardening headers to every response (SECURITY.md section 5)."""

    def __init__(self, app: ASGIApp, *, settings: Settings) -> None:
        super().__init__(app)
        self._settings = settings

    async def dispatch(self, request: Request, call_next: RequestHandler) -> Response:
        response = await call_next(request)
        headers = response.headers
        headers.setdefault("X-Content-Type-Options", "nosniff")
        headers.setdefault("X-Frame-Options", "DENY")
        headers.setdefault("Referrer-Policy", "no-referrer")
        headers.setdefault(
            "Permissions-Policy", "camera=(), microphone=(), geolocation=(), interest-cohort=()"
        )
        headers.setdefault(
            "Content-Security-Policy",
            "default-src 'none'; frame-ancestors 'none'; base-uri 'none'; form-action 'none'",
        )
        # API responses may carry session content: never cache them anywhere.
        headers.setdefault("Cache-Control", "no-store")
        if self._settings.is_production:
            headers.setdefault(
                "Strict-Transport-Security", "max-age=31536000; includeSubDomains"
            )
        return response


class GlobalRateLimitMiddleware(BaseHTTPMiddleware):
    """Coarse per-client request ceiling, ahead of any per-route limits."""

    def __init__(self, app: ASGIApp, *, settings: Settings) -> None:
        super().__init__(app)
        self._settings = settings
        self._rule = RateLimitRule(
            name="global", limit=settings.rate_limit_requests_per_minute, window_seconds=60
        )

    async def dispatch(self, request: Request, call_next: RequestHandler) -> Response:
        limiter = getattr(request.app.state, "rate_limiter", None)
        if limiter is None or request.url.path in _RATE_LIMIT_EXEMPT:
            return await call_next(request)

        identity = client_identity(request, trust_proxy=self._settings.trust_proxy)
        result = await limiter.check(self._rule, identity)
        if not result.allowed:
            error = RateLimitedError(result.retry_after)
            return _error_response(error, getattr(request.state, "request_id", None))
        response = await call_next(request)
        response.headers.setdefault("X-RateLimit-Limit", str(result.limit))
        response.headers.setdefault("X-RateLimit-Remaining", str(result.remaining))
        return response


def _error_response(error: AppError, request_id: str | None) -> JSONResponse:
    return JSONResponse(
        status_code=error.status_code,
        content=error.to_payload(request_id),
        headers=error.headers,
    )


def register_exception_handlers(app: FastAPI) -> None:
    @app.exception_handler(AppError)
    async def _app_error(request: Request, exc: AppError) -> JSONResponse:
        logger.info(
            "request.error",
            code=exc.code,
            category=exc.category.value,
            route=_route_of(request),
        )
        return _error_response(exc, getattr(request.state, "request_id", None))

    @app.exception_handler(RequestValidationError)
    async def _validation_error(
        request: Request, exc: RequestValidationError
    ) -> JSONResponse:
        # Report which fields failed and why, but never echo the submitted values back.
        fields = sorted(
            {".".join(str(part) for part in err.get("loc", ())[1:]) for err in exc.errors()}
        )
        error = ValidationFailedError(details={"fields": [f for f in fields if f]})
        logger.info("request.validation_failed", route=_route_of(request))
        return _error_response(error, getattr(request.state, "request_id", None))

    @app.exception_handler(StarletteHTTPException)
    async def _http_error(request: Request, exc: StarletteHTTPException) -> JSONResponse:
        mapped = AppError(str(exc.detail) if exc.status_code < 500 else None)
        mapped.status_code = exc.status_code
        mapped.code = "HTTP_ERROR" if exc.status_code < 500 else "INTERNAL_ERROR"
        mapped.category = (
            ErrorCategory.VALIDATION if exc.status_code < 500 else ErrorCategory.INTERNAL
        )
        return _error_response(mapped, getattr(request.state, "request_id", None))

    @app.exception_handler(Exception)
    async def _unhandled(request: Request, exc: Exception) -> JSONResponse:
        # The exception type is logged; the client sees only the generic envelope.
        logger.error(
            "request.internal_error",
            error_type=type(exc).__name__,
            route=_route_of(request),
        )
        return _error_response(AppError(), getattr(request.state, "request_id", None))
