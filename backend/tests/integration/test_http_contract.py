"""Health probes, security headers, request ids, error sanitisation, CORS and rate limits."""

from __future__ import annotations

import pytest
from httpx import ASGITransport, AsyncClient

from app.config import Settings
from app.core.errors import AppError
from app.main import create_app
from tests.conftest import new_session


async def test_health_is_dependency_free(client: AsyncClient) -> None:
    response = await client.get("/health")
    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "ok"
    assert body["environment"] == "development"


async def test_ready_reports_store_and_capabilities(client: AsyncClient) -> None:
    response = await client.get("/ready")
    assert response.status_code == 200
    body = response.json()
    assert body["ready"] is True
    assert body["session_store"] == "memory"
    assert set(body["capabilities"]) == {"llm", "embeddings", "ocr", "pdf_export", "redis"}


async def test_ready_capabilities_are_honest(client: AsyncClient) -> None:
    """Nothing is configured, so nothing may claim to be available."""
    capabilities = (await client.get("/ready")).json()["capabilities"]
    assert capabilities["llm"] is False
    assert capabilities["embeddings"] is False
    assert capabilities["redis"] is False


async def test_ready_reports_unready_when_store_is_down(tmp_path: object) -> None:
    settings = Settings(
        app_env="development", temp_dir=str(tmp_path), session_store_backend="memory"
    )
    app = create_app(settings)

    class DownStore:
        async def ping(self) -> bool:
            return False

        async def sweep(self) -> int:
            return 0

        async def close(self) -> None:
            return None

    app.state.session_store = DownStore()
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as http:
        async with app.router.lifespan_context(app):
            response = await http.get("/ready")
    assert response.status_code == 503
    assert response.json()["ready"] is False


async def test_metrics_reports_content_free_counters_and_latencies(client: AsyncClient) -> None:
    await client.get("/health")  # generate at least one recorded request
    response = await client.get("/metrics")
    assert response.status_code == 200
    body = response.json()
    assert "queue_depth" in body
    assert isinstance(body["counters"], dict)
    assert isinstance(body["latencies"], dict)
    assert any(key.startswith("http_requests_total") for key in body["counters"])
    assert any(key.startswith("http_request_duration_ms") for key in body["latencies"])


async def test_metrics_is_not_exposed_in_production(tmp_path: object) -> None:
    settings = Settings(
        app_env="production",
        temp_dir=str(tmp_path),
        session_store_backend="redis",
        redis_url="redis://localhost:6379/0",
        debug=False,
        log_format="json",
        cors_origins=["https://example.test"],
    )
    app = create_app(settings)
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as http:
        async with app.router.lifespan_context(app):
            response = await http.get("/metrics")
    assert response.status_code == 404


async def test_security_headers_present(client: AsyncClient) -> None:
    headers = (await client.get("/health")).headers
    assert headers["X-Content-Type-Options"] == "nosniff"
    assert headers["X-Frame-Options"] == "DENY"
    assert headers["Referrer-Policy"] == "no-referrer"
    assert "frame-ancestors 'none'" in headers["Content-Security-Policy"]
    assert headers["Cache-Control"] == "no-store"
    assert "camera=()" in headers["Permissions-Policy"]


async def test_hsts_only_in_production(client: AsyncClient, tmp_path: object) -> None:
    assert "Strict-Transport-Security" not in (await client.get("/health")).headers

    prod = create_app(
        Settings(
            app_env="production",
            debug=False,
            log_format="json",
            session_store_backend="redis",
            redis_url="redis://localhost:6379/0",
            cors_origins=["https://app.example.com"],
            temp_dir=str(tmp_path),
        )
    )
    transport = ASGITransport(app=prod)
    async with AsyncClient(transport=transport, base_url="http://test") as http:
        response = await http.get("/health")  # no lifespan: probe must not need the store
    assert "Strict-Transport-Security" in response.headers


async def test_request_id_returned_and_echoed(client: AsyncClient) -> None:
    generated = (await client.get("/health")).headers["X-Request-Id"]
    assert generated

    supplied = await client.get("/health", headers={"X-Request-Id": "trace-abc"})
    assert supplied.headers["X-Request-Id"] == "trace-abc"


async def test_error_envelope_shape(client: AsyncClient) -> None:
    response = await client.get("/v1/session")
    error = response.json()["error"]
    assert set(error) >= {"code", "category", "message", "retryable", "request_id"}
    assert error["request_id"] == response.headers["X-Request-Id"]


async def test_errors_never_leak_internals(client: AsyncClient) -> None:
    """An unhandled exception must produce the generic envelope, not a traceback."""
    app = client.app  # type: ignore[attr-defined]

    @app.get("/v1/_boom")
    async def boom() -> None:
        raise RuntimeError("secret detail: C:/srv/app/tmp/upload-9f2a.pdf")

    transport = ASGITransport(app=app, raise_app_exceptions=False)
    async with AsyncClient(transport=transport, base_url="http://test") as http:
        response = await http.get("/v1/_boom")

    assert response.status_code == 500
    text = response.text
    assert "secret detail" not in text
    assert "Traceback" not in text
    assert "C:/srv" not in text, "filesystem paths must never reach a client"
    assert response.json()["error"]["code"] == "INTERNAL_ERROR"


async def test_validation_errors_do_not_echo_values(client: AsyncClient) -> None:
    response = await client.post("/v1/session", json={"mode": "priya.raman@example.com"})
    assert response.status_code == 422
    assert "priya.raman@example.com" not in response.text
    assert response.json()["error"]["details"]["fields"] == ["mode"]


async def test_cors_allows_configured_origin(client: AsyncClient) -> None:
    response = await client.options(
        "/v1/session",
        headers={
            "Origin": "http://localhost:3000",
            "Access-Control-Request-Method": "POST",
            "Access-Control-Request-Headers": "X-Session-Id",
        },
    )
    assert response.status_code == 200
    assert response.headers["access-control-allow-origin"] == "http://localhost:3000"


async def test_cors_rejects_unknown_origin(client: AsyncClient) -> None:
    response = await client.options(
        "/v1/session",
        headers={
            "Origin": "https://evil.example.com",
            "Access-Control-Request-Method": "POST",
        },
    )
    assert "access-control-allow-origin" not in response.headers


async def test_cookies_are_never_allowed(client: AsyncClient) -> None:
    """The session id travels in a header; no cookie is ever set, so CSRF has no vector."""
    response = await client.post("/v1/session", json={})
    assert "set-cookie" not in response.headers
    assert response.headers.get("access-control-allow-credentials") != "true"


async def test_global_rate_limit_enforced(rate_limited_client: AsyncClient) -> None:
    statuses = [(await rate_limited_client.get("/v1/session")).status_code for _ in range(8)]
    assert 429 in statuses
    blocked = await rate_limited_client.get("/v1/session")
    assert blocked.status_code == 429
    assert int(blocked.headers["Retry-After"]) > 0
    assert blocked.json()["error"]["code"] == "RATE_LIMITED"


async def test_session_creation_rate_limited(rate_limited_client: AsyncClient) -> None:
    codes = [
        (await rate_limited_client.post("/v1/session", json={})).status_code for _ in range(4)
    ]
    assert codes[:2] == [201, 201]
    assert 429 in codes[2:]


async def test_health_exempt_from_rate_limit(rate_limited_client: AsyncClient) -> None:
    for _ in range(20):
        assert (await rate_limited_client.get("/health")).status_code == 200


def test_app_error_payload_is_serialisable() -> None:
    payload = AppError("boom").to_payload("req-1")
    assert payload["error"]["request_id"] == "req-1"
    assert payload["error"]["retryable"] is False


async def test_session_endpoints_are_not_cached(client: AsyncClient) -> None:
    session_id = await new_session(client)
    response = await client.get("/v1/session", headers={"X-Session-Id": session_id})
    assert response.headers["Cache-Control"] == "no-store"


@pytest.mark.parametrize("path", ["/docs", "/openapi.json"])
async def test_docs_available_in_development(client: AsyncClient, path: str) -> None:
    assert (await client.get(path)).status_code == 200
