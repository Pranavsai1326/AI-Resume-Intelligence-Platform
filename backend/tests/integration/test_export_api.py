"""Integration tests for POST /v1/export."""

from __future__ import annotations

from httpx import AsyncClient

from tests.conftest import new_session
from tests.fixtures import make_txt_bytes


async def _upload_document(client: AsyncClient, session_id: str) -> str:
    files = {"file": ("resume.txt", make_txt_bytes(), "text/plain")}
    upload = await client.post(
        "/v1/documents", files=files, headers={"X-Session-Id": session_id}
    )
    return str(upload.json()["document_id"])


async def test_export_docx_returns_correct_media_type_and_filename(client: AsyncClient) -> None:
    session_id = await new_session(client)
    document_id = await _upload_document(client, session_id)

    response = await client.post(
        "/v1/export",
        json={"document_id": document_id, "format": "docx"},
        headers={"X-Session-Id": session_id},
    )
    assert response.status_code == 200
    assert response.headers["content-type"].startswith(
        "application/vnd.openxmlformats-officedocument.wordprocessingml.document"
    )
    assert 'filename="original.docx"' in response.headers["content-disposition"]
    assert len(response.content) > 0


async def test_export_pdf_returns_correct_media_type_and_filename(client: AsyncClient) -> None:
    session_id = await new_session(client)
    document_id = await _upload_document(client, session_id)

    response = await client.post(
        "/v1/export",
        json={"document_id": document_id, "format": "pdf"},
        headers={"X-Session-Id": session_id},
    )
    if response.status_code == 503:
        # Chromium is not installed for Playwright in this environment - honest degrade, not a bug.
        assert response.json()["error"]["code"] == "SERVICE_UNAVAILABLE"
        return
    assert response.status_code == 200
    assert response.headers["content-type"] == "application/pdf"
    assert 'filename="original.pdf"' in response.headers["content-disposition"]
    assert response.content.startswith(b"%PDF")


async def test_export_unknown_document_is_404(client: AsyncClient) -> None:
    session_id = await new_session(client)
    response = await client.post(
        "/v1/export",
        json={"document_id": "does-not-exist", "format": "docx"},
        headers={"X-Session-Id": session_id},
    )
    assert response.status_code == 404


async def test_export_requires_a_session(client: AsyncClient) -> None:
    response = await client.post("/v1/export", json={"document_id": "d1", "format": "docx"})
    assert response.status_code == 400


async def test_export_rejects_invalid_format(client: AsyncClient) -> None:
    session_id = await new_session(client)
    document_id = await _upload_document(client, session_id)
    response = await client.post(
        "/v1/export",
        json={"document_id": document_id, "format": "txt"},
        headers={"X-Session-Id": session_id},
    )
    assert response.status_code == 422


async def test_export_filename_is_derived_from_version_label_safely(client: AsyncClient) -> None:
    """A version label with path-traversal/header-injection characters must never leak into
    the Content-Disposition header - _safe_filename strips to an [A-Za-z0-9-] allowlist."""
    session_id = await new_session(client)
    document_id = await _upload_document(client, session_id)

    listed = await client.get(
        "/v1/resume/versions",
        params={"document_id": document_id},
        headers={"X-Session-Id": session_id},
    )
    original_version_id = listed.json()[0]["version_id"]

    malicious_label = "../../etc/passwd\r\nX-Injected: 1"
    created = await client.post(
        "/v1/resume/versions",
        json={
            "document_id": document_id,
            "label": malicious_label,
            "based_on_version_id": original_version_id,
        },
        headers={"X-Session-Id": session_id},
    )
    version_id = created.json()["version_id"]

    response = await client.post(
        "/v1/export",
        json={"document_id": document_id, "version_id": version_id, "format": "docx"},
        headers={"X-Session-Id": session_id},
    )
    assert response.status_code == 200
    disposition = response.headers["content-disposition"]
    # The allowlist keeps alphanumeric words from the label ("etc", "passwd") but strips every
    # character that could carry a path-traversal or header-injection payload.
    assert "\r" not in disposition
    assert "\n" not in disposition
    assert ".." not in disposition
    assert "/" not in disposition
    assert disposition == 'attachment; filename="etc-passwd-x-injected-1.docx"'
