"""Zero-persistence guarantees for analysis results.

Extends the Phase 2 document-privacy suite: an analysis result derived from a canary resume must
never appear in logs and must be destroyed along with the session that produced it, the same
properties already proven for the document pipeline it sits on top of.
"""

from __future__ import annotations

from pathlib import Path

import pytest
from httpx import ASGITransport, AsyncClient

from app.config import Settings
from app.main import create_app
from tests.conftest import new_session
from tests.privacy.test_document_privacy import CANARY_RESUME_TEXT
from tests.privacy.test_zero_persistence import CANARY_TOKENS


@pytest.fixture
def privacy_settings(tmp_path: Path) -> Settings:
    return Settings(
        app_env="development",
        temp_dir=str(tmp_path / "tmp"),
        session_store_backend="memory",
        rate_limit_enabled=False,
        log_format="json",
    )


async def _upload_and_analyze(http: AsyncClient, session_id: str) -> None:
    files = {"file": ("resume.txt", CANARY_RESUME_TEXT, "text/plain")}
    upload = await http.post("/v1/documents", files=files, headers={"X-Session-Id": session_id})
    document_id = upload.json()["document_id"]
    response = await http.post(
        "/v1/analysis/resume",
        json={"document_id": document_id},
        headers={"X-Session-Id": session_id},
    )
    assert response.status_code == 201


async def test_analysis_result_carries_no_resume_content_into_logs(
    privacy_settings: Settings, capsys: pytest.CaptureFixture[str]
) -> None:
    app = create_app(privacy_settings)
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as http:
        async with app.router.lifespan_context(app):
            session_id = await new_session(http)
            await _upload_and_analyze(http, session_id)

    output = capsys.readouterr().out
    for token in CANARY_TOKENS:
        assert token not in output


async def test_analysis_is_destroyed_with_the_session(privacy_settings: Settings) -> None:
    app = create_app(privacy_settings)
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as http:
        async with app.router.lifespan_context(app):
            session_id = await new_session(http)
            files = {"file": ("resume.txt", CANARY_RESUME_TEXT, "text/plain")}
            upload = await http.post(
                "/v1/documents", files=files, headers={"X-Session-Id": session_id}
            )
            document_id = upload.json()["document_id"]
            await http.post(
                "/v1/analysis/resume",
                json={"document_id": document_id},
                headers={"X-Session-Id": session_id},
            )

            await http.delete("/v1/session", headers={"X-Session-Id": session_id})

            response = await http.get(
                f"/v1/analysis/{document_id}", headers={"X-Session-Id": session_id}
            )
            assert response.status_code == 410  # the session itself is gone
