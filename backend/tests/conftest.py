"""Shared fixtures.

Tests never touch a real Redis unless one is explicitly available, never sleep to observe TTL
behaviour (a :class:`FakeClock` is advanced instead), and never write outside a tmp directory.
"""

from __future__ import annotations

import os
from collections.abc import AsyncIterator, Iterator
from pathlib import Path

import pytest
from httpx import ASGITransport, AsyncClient

from app.config import Settings
from app.core.clock import FakeClock
from app.main import create_app
from app.sessions.manager import SessionManager
from app.sessions.memory import MemorySessionStore

REDIS_TEST_URL = os.environ.get("TEST_REDIS_URL", "")


@pytest.fixture
def clock() -> FakeClock:
    return FakeClock()


@pytest.fixture
def memory_store(clock: FakeClock) -> MemorySessionStore:
    return MemorySessionStore(clock=clock)


@pytest.fixture
def settings(tmp_path: Path) -> Settings:
    return Settings(
        app_env="development",
        debug=True,
        temp_dir=str(tmp_path / "tmp"),
        cors_origins=["http://localhost:3000"],
        session_store_backend="memory",
        rate_limit_enabled=False,
        log_format="json",
        # Keep the default test suite hermetic and fast: no network call, no ~130MB model
        # download mid-run. Tests that specifically exercise real embeddings opt in explicitly
        # and skip gracefully if the model cannot be loaded (tests/unit/test_embeddings.py).
        embedding_backend="none",
    )


@pytest.fixture
def manager(memory_store: MemorySessionStore, clock: FakeClock) -> SessionManager:
    return SessionManager(
        memory_store,
        idle_ttl_seconds=3600,
        absolute_ttl_seconds=28_800,
        clock=clock,
    )


@pytest.fixture
async def client(settings: Settings) -> AsyncIterator[AsyncClient]:
    """App-backed HTTP client using the real middleware stack and lifespan."""
    app = create_app(settings)
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as http:
        async with app.router.lifespan_context(app):
            http.app = app  # type: ignore[attr-defined]
            yield http


@pytest.fixture
async def rate_limited_client(tmp_path: Path) -> AsyncIterator[AsyncClient]:
    """Client with rate limiting switched on and low ceilings, for limiter tests."""
    settings = Settings(
        app_env="development",
        debug=True,
        temp_dir=str(tmp_path / "tmp-rl"),
        session_store_backend="memory",
        rate_limit_enabled=True,
        rate_limit_requests_per_minute=5,
        rate_limit_session_create_per_hour=2,
        embedding_backend="none",
        log_format="json",
    )
    app = create_app(settings)
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as http:
        async with app.router.lifespan_context(app):
            yield http


@pytest.fixture
def captured_logs(capsys: pytest.CaptureFixture[str]) -> Iterator[pytest.CaptureFixture[str]]:
    """Logs are emitted to stdout; tests assert on what they do *not* contain."""
    yield capsys


async def new_session(http: AsyncClient, mode: str = "candidate") -> str:
    response = await http.post("/v1/session", json={"mode": mode})
    assert response.status_code == 201, response.text
    return str(response.json()["session_id"])
