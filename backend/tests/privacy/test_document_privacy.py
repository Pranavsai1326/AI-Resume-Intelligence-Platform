"""Zero-persistence guarantees for uploaded documents.

Extends tests/privacy/test_zero_persistence.py to the document pipeline specifically: a resume
containing distinctive canary content must never reach durable storage, must vanish with its
session, and must never appear in logs - the same properties already proven for generic session
objects, now proven for the actual upload path a user exercises.
"""

from __future__ import annotations

from pathlib import Path

import pytest
from httpx import ASGITransport, AsyncClient

from app.config import Settings
from app.main import create_app
from tests.conftest import new_session
from tests.privacy.test_zero_persistence import CANARY_TOKENS, _files_containing, _snapshot

CANARY_RESUME_TEXT = (
    b"Zorvath Quillfeather\n"
    b"zorvath.quillfeather@example-canary.test | +1 555 0100 4242\n\n"
    b"EXPERIENCE\n"
    b"Senior Platform Engineer, Cindervale Robotics\n"
    b"Jan 2020 - Present\n"
    b"- Built the Palewind ingestion service\n"
)


@pytest.fixture
def privacy_settings(tmp_path: Path) -> Settings:
    return Settings(
        app_env="development",
        temp_dir=str(tmp_path / "tmp"),
        session_store_backend="memory",
        rate_limit_enabled=False,
        log_format="json",
    )


async def test_uploaded_resume_never_reaches_disk(
    privacy_settings: Settings, tmp_path: Path
) -> None:
    workspace_root = Path(__file__).resolve().parents[2]  # noqa: ASYNC240
    app = create_app(privacy_settings)
    before = _snapshot(workspace_root)

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as http:
        async with app.router.lifespan_context(app):
            session_id = await new_session(http)
            files = {"file": ("resume.txt", CANARY_RESUME_TEXT, "text/plain")}
            response = await http.post(
                "/v1/documents", files=files, headers={"X-Session-Id": session_id}
            )
            assert response.status_code == 201

    after = _snapshot(workspace_root)
    changed = [p for p in after if p not in before or after[p] != before.get(p)]
    assert _files_containing(changed, CANARY_TOKENS) == []
    assert _files_containing(list(tmp_path.rglob("*")), CANARY_TOKENS) == []  # noqa: ASYNC240


async def test_document_and_resume_are_destroyed_with_the_session(
    privacy_settings: Settings,
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

            await http.delete("/v1/session", headers={"X-Session-Id": session_id})

            response = await http.get(
                f"/v1/documents/{document_id}", headers={"X-Session-Id": session_id}
            )
            assert response.status_code == 410  # the session itself is gone


async def test_uploaded_resume_content_never_appears_in_logs(
    privacy_settings: Settings, capsys: pytest.CaptureFixture[str]
) -> None:
    app = create_app(privacy_settings)
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as http:
        async with app.router.lifespan_context(app):
            session_id = await new_session(http)
            files = {"file": ("resume.txt", CANARY_RESUME_TEXT, "text/plain")}
            await http.post("/v1/documents", files=files, headers={"X-Session-Id": session_id})

    output = capsys.readouterr().out
    for token in CANARY_TOKENS:
        assert token not in output


async def test_original_filename_is_not_logged(
    privacy_settings: Settings, capsys: pytest.CaptureFixture[str]
) -> None:
    app = create_app(privacy_settings)
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as http:
        async with app.router.lifespan_context(app):
            session_id = await new_session(http)
            files = {
                "file": (
                    "zorvath-quillfeather-confidential-resume.txt",
                    CANARY_RESUME_TEXT,
                    "text/plain",
                )
            }
            await http.post("/v1/documents", files=files, headers={"X-Session-Id": session_id})

    output = capsys.readouterr().out
    assert "zorvath-quillfeather-confidential-resume" not in output


async def test_session_b_cannot_fetch_session_a_document(
    privacy_settings: Settings,
) -> None:
    app = create_app(privacy_settings)
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as http:
        async with app.router.lifespan_context(app):
            session_a = await new_session(http)
            session_b = await new_session(http)

            files = {"file": ("resume.txt", CANARY_RESUME_TEXT, "text/plain")}
            upload = await http.post(
                "/v1/documents", files=files, headers={"X-Session-Id": session_a}
            )
            document_id = upload.json()["document_id"]

            response = await http.get(
                f"/v1/documents/{document_id}", headers={"X-Session-Id": session_b}
            )
            assert response.status_code == 404
