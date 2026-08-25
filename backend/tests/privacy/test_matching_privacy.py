"""Zero-persistence guarantees for job descriptions and match results.

Extends the document/analysis privacy suites: a job description and a match result derived from
canary content must never appear in logs and must be destroyed with the session, the same
properties already proven for the rest of the pipeline this phase builds on.
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

CANARY_JD_TEXT = (
    "Requirements\n"
    "- 3+ years building services for Cindervale Robotics-style platforms\n"
    "- Proficiency in Palewind-flavoured Python\n"
)


@pytest.fixture
def privacy_settings(tmp_path: Path) -> Settings:
    return Settings(
        app_env="development",
        temp_dir=str(tmp_path / "tmp"),
        session_store_backend="memory",
        rate_limit_enabled=False,
        embedding_backend="none",
        log_format="json",
    )


async def test_job_and_match_carry_no_canary_content_into_logs(
    privacy_settings: Settings, capsys: pytest.CaptureFixture[str]
) -> None:
    app = create_app(privacy_settings)
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as http:
        async with app.router.lifespan_context(app):
            session_id = await new_session(http)
            files = {"file": ("resume.txt", CANARY_RESUME_TEXT, "text/plain")}
            upload = await http.post(
                "/v1/documents", files=files, headers={"X-Session-Id": session_id}
            )
            document_id = upload.json()["document_id"]

            job = await http.post(
                "/v1/jobs", json={"text": CANARY_JD_TEXT}, headers={"X-Session-Id": session_id}
            )
            job_id = job.json()["job_id"]

            await http.post(
                "/v1/match",
                json={"document_id": document_id, "job_id": job_id},
                headers={"X-Session-Id": session_id},
            )

    output = capsys.readouterr().out
    for token in CANARY_TOKENS:
        assert token not in output
    assert "Cindervale" not in output
    assert "Palewind" not in output


async def test_job_and_match_are_destroyed_with_the_session(privacy_settings: Settings) -> None:
    app = create_app(privacy_settings)
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as http:
        async with app.router.lifespan_context(app):
            session_id = await new_session(http)
            files = {"file": ("resume.txt", CANARY_RESUME_TEXT, "text/plain")}
            upload = await http.post(
                "/v1/documents", files=files, headers={"X-Session-Id": session_id}
            )
            document_id = upload.json()["document_id"]

            job = await http.post(
                "/v1/jobs", json={"text": CANARY_JD_TEXT}, headers={"X-Session-Id": session_id}
            )
            job_id = job.json()["job_id"]

            await http.post(
                "/v1/match",
                json={"document_id": document_id, "job_id": job_id},
                headers={"X-Session-Id": session_id},
            )

            await http.delete("/v1/session", headers={"X-Session-Id": session_id})

            response = await http.get(
                f"/v1/jobs/{job_id}", headers={"X-Session-Id": session_id}
            )
            assert response.status_code == 410  # the session itself is gone


async def test_session_b_cannot_read_session_a_job_or_match(privacy_settings: Settings) -> None:
    app = create_app(privacy_settings)
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as http:
        async with app.router.lifespan_context(app):
            session_a = await new_session(http)
            session_b = await new_session(http)

            job = await http.post(
                "/v1/jobs", json={"text": CANARY_JD_TEXT}, headers={"X-Session-Id": session_a}
            )
            job_id = job.json()["job_id"]

            response = await http.get(
                f"/v1/jobs/{job_id}", headers={"X-Session-Id": session_b}
            )
            assert response.status_code == 404
