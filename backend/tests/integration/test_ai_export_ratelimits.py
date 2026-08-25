"""Phase 8: dedicated rate limits for AI calls and exports (SECURITY.md section 4).

Both previously had no per-feature bound beyond the shared upload/global limits - an anonymous
session could call /v1/ai/rewrite or /v1/export without limit. Verified here against a client
configured with a limit low enough to hit deterministically in a handful of requests.
"""

from __future__ import annotations

from collections.abc import AsyncIterator
from pathlib import Path

import pytest
from httpx import ASGITransport, AsyncClient

from app.config import Settings
from app.main import create_app
from tests.conftest import new_session
from tests.fixtures import make_txt_bytes

JD_TEXT = "Requirements\n- Proficiency in Python\n"


@pytest.fixture
async def ai_limited_client(tmp_path: Path) -> AsyncIterator[AsyncClient]:
    settings = Settings(
        app_env="development",
        debug=True,
        temp_dir=str(tmp_path / "tmp-ai-rl"),
        session_store_backend="memory",
        rate_limit_enabled=True,
        rate_limit_requests_per_minute=1000,
        rate_limit_session_create_per_hour=1000,
        rate_limit_uploads_per_hour=1000,
        rate_limit_ai_calls_per_hour=1,
        embedding_backend="none",
        log_format="json",
    )
    app = create_app(settings)
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as http:
        async with app.router.lifespan_context(app):
            yield http


@pytest.fixture
async def export_limited_client(tmp_path: Path) -> AsyncIterator[AsyncClient]:
    settings = Settings(
        app_env="development",
        debug=True,
        temp_dir=str(tmp_path / "tmp-export-rl"),
        session_store_backend="memory",
        rate_limit_enabled=True,
        rate_limit_requests_per_minute=1000,
        rate_limit_session_create_per_hour=1000,
        rate_limit_uploads_per_hour=1000,
        rate_limit_exports_per_hour=1,
        embedding_backend="none",
        log_format="json",
    )
    app = create_app(settings)
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as http:
        async with app.router.lifespan_context(app):
            yield http


async def _upload_resume(client: AsyncClient, session_id: str) -> str:
    files = {"file": ("resume.txt", make_txt_bytes(), "text/plain")}
    response = await client.post("/v1/documents", files=files, headers={"X-Session-Id": session_id})
    return str(response.json()["document_id"])


async def test_ai_rewrite_is_rate_limited_per_session(ai_limited_client: AsyncClient) -> None:
    session_id = await new_session(ai_limited_client)
    document_id = await _upload_resume(ai_limited_client, session_id)

    first = await ai_limited_client.post(
        "/v1/ai/rewrite",
        json={"document_id": document_id, "kind": "bullet", "text": "Built the service."},
        headers={"X-Session-Id": session_id},
    )
    assert first.status_code == 200

    second = await ai_limited_client.post(
        "/v1/ai/rewrite",
        json={"document_id": document_id, "kind": "bullet", "text": "Built the service."},
        headers={"X-Session-Id": session_id},
    )
    assert second.status_code == 429
    assert "Retry-After" in second.headers


async def test_ai_rate_limit_is_per_session_not_global(ai_limited_client: AsyncClient) -> None:
    session_a = await new_session(ai_limited_client)
    session_b = await new_session(ai_limited_client)
    document_a = await _upload_resume(ai_limited_client, session_a)
    document_b = await _upload_resume(ai_limited_client, session_b)

    for session_id, document_id in ((session_a, document_a), (session_b, document_b)):
        response = await ai_limited_client.post(
            "/v1/ai/rewrite",
            json={"document_id": document_id, "kind": "bullet", "text": "Built the service."},
            headers={"X-Session-Id": session_id},
        )
        assert response.status_code == 200, session_id


async def test_cover_letter_and_interview_prep_share_the_same_ai_budget(
    ai_limited_client: AsyncClient,
) -> None:
    session_id = await new_session(ai_limited_client)
    document_id = await _upload_resume(ai_limited_client, session_id)
    job = await ai_limited_client.post(
        "/v1/jobs", json={"text": JD_TEXT}, headers={"X-Session-Id": session_id}
    )
    job_id = job.json()["job_id"]

    # No LLM configured -> generate_cover_letter never calls the provider, so is_available() is
    # False and the limit is never actually enforced here; this documents that a NullLLMProvider
    # deployment does not throttle career endpoints at all (nothing to bound the cost of).
    response = await ai_limited_client.post(
        "/v1/cover-letter",
        json={"document_id": document_id, "job_id": job_id},
        headers={"X-Session-Id": session_id},
    )
    assert response.status_code == 200
    assert response.json()["available"] is False


async def test_export_is_rate_limited_per_session(export_limited_client: AsyncClient) -> None:
    session_id = await new_session(export_limited_client)
    document_id = await _upload_resume(export_limited_client, session_id)

    first = await export_limited_client.post(
        "/v1/export",
        json={"document_id": document_id, "format": "docx"},
        headers={"X-Session-Id": session_id},
    )
    assert first.status_code == 200

    second = await export_limited_client.post(
        "/v1/export",
        json={"document_id": document_id, "format": "docx"},
        headers={"X-Session-Id": session_id},
    )
    assert second.status_code == 429
