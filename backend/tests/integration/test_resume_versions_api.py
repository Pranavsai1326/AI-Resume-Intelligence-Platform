"""Integration tests for GET/POST /v1/resume/versions."""

from __future__ import annotations

from httpx import AsyncClient

from tests.conftest import new_session
from tests.fixtures import make_txt_bytes


async def _upload_document(client: AsyncClient, session_id: str) -> str:
    files = {"file": ("resume.txt", make_txt_bytes(), "text/plain")}
    upload = await client.post(
        "/v1/documents", files=files, headers={"X-Session-Id": session_id}
    )
    assert upload.status_code == 201
    return str(upload.json()["document_id"])


async def test_list_versions_lazily_creates_original(client: AsyncClient) -> None:
    session_id = await new_session(client)
    document_id = await _upload_document(client, session_id)

    response = await client.get(
        "/v1/resume/versions",
        params={"document_id": document_id},
        headers={"X-Session-Id": session_id},
    )
    assert response.status_code == 200
    versions = response.json()
    assert len(versions) == 1
    assert versions[0]["label"] == "Original"
    assert versions[0]["source"] == "original"
    assert "resume" not in versions[0]


async def test_get_version_by_id(client: AsyncClient) -> None:
    session_id = await new_session(client)
    document_id = await _upload_document(client, session_id)

    listed = await client.get(
        "/v1/resume/versions",
        params={"document_id": document_id},
        headers={"X-Session-Id": session_id},
    )
    version_id = listed.json()[0]["version_id"]

    response = await client.get(
        f"/v1/resume/versions/{version_id}", headers={"X-Session-Id": session_id}
    )
    assert response.status_code == 200
    body = response.json()
    assert body["version_id"] == version_id
    assert "resume" in body
    assert body["resume"]["contact"]["full_name"]["value"] == "Jordan Ellery Vance"


async def test_get_unknown_version_is_404(client: AsyncClient) -> None:
    session_id = await new_session(client)
    response = await client.get(
        "/v1/resume/versions/does-not-exist", headers={"X-Session-Id": session_id}
    )
    assert response.status_code == 404


async def test_create_version_with_explicit_resume(client: AsyncClient) -> None:
    session_id = await new_session(client)
    document_id = await _upload_document(client, session_id)

    original = await client.get(
        "/v1/resume/versions",
        params={"document_id": document_id},
        headers={"X-Session-Id": session_id},
    )
    resume_payload = (
        await client.get(
            f"/v1/resume/versions/{original.json()[0]['version_id']}",
            headers={"X-Session-Id": session_id},
        )
    ).json()["resume"]
    resume_payload["summary"]["value"] = "An edited summary."

    response = await client.post(
        "/v1/resume/versions",
        json={
            "document_id": document_id,
            "label": "My edit",
            "resume": resume_payload,
            "source": "manual_edit",
        },
        headers={"X-Session-Id": session_id},
    )
    assert response.status_code == 201
    body = response.json()
    assert body["label"] == "My edit"
    assert body["source"] == "manual_edit"
    assert body["resume"]["summary"]["value"] == "An edited summary."


async def test_create_version_based_on_another_version(client: AsyncClient) -> None:
    session_id = await new_session(client)
    document_id = await _upload_document(client, session_id)

    original = (
        await client.get(
            "/v1/resume/versions",
            params={"document_id": document_id},
            headers={"X-Session-Id": session_id},
        )
    ).json()[0]

    response = await client.post(
        "/v1/resume/versions",
        json={
            "document_id": document_id,
            "label": "Copy",
            "based_on_version_id": original["version_id"],
        },
        headers={"X-Session-Id": session_id},
    )
    assert response.status_code == 201
    body = response.json()
    assert body["based_on_version_id"] == original["version_id"]


async def test_create_version_requires_resume_or_based_on(client: AsyncClient) -> None:
    session_id = await new_session(client)
    document_id = await _upload_document(client, session_id)

    response = await client.post(
        "/v1/resume/versions",
        json={"document_id": document_id, "label": "Bad"},
        headers={"X-Session-Id": session_id},
    )
    assert response.status_code == 422


async def test_create_version_with_unknown_based_on_is_404(client: AsyncClient) -> None:
    session_id = await new_session(client)
    document_id = await _upload_document(client, session_id)

    response = await client.post(
        "/v1/resume/versions",
        json={
            "document_id": document_id,
            "label": "Copy",
            "based_on_version_id": "does-not-exist",
        },
        headers={"X-Session-Id": session_id},
    )
    assert response.status_code == 404


async def test_versions_require_a_session(client: AsyncClient) -> None:
    response = await client.get("/v1/resume/versions", params={"document_id": "d1"})
    assert response.status_code == 400
