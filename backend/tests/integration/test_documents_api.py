"""Document API: upload, retrieval, deletion, caching, validation and rate limits."""

from __future__ import annotations

from httpx import AsyncClient

from tests.conftest import new_session
from tests.fixtures import (
    SYNTHETIC_RESUME_TEXT,
    make_docx_bytes,
    make_pdf_bytes,
    make_random_binary_bytes,
    make_txt_bytes,
    make_zip_bomb_docx_bytes,
)


async def _upload(
    client: AsyncClient, session_id: str, data: bytes, filename: str, content_type: str
) -> dict:
    files = {"file": (filename, data, content_type)}
    response = await client.post(
        "/v1/documents", files=files, headers={"X-Session-Id": session_id}
    )
    return response


async def test_upload_requires_a_session(client: AsyncClient) -> None:
    files = {"file": ("resume.txt", make_txt_bytes(), "text/plain")}
    response = await client.post("/v1/documents", files=files)
    assert response.status_code == 400


async def test_upload_txt_resume_returns_a_structured_summary(client: AsyncClient) -> None:
    session_id = await new_session(client)
    response = await _upload(client, session_id, make_txt_bytes(), "resume.txt", "text/plain")
    assert response.status_code == 201
    body = response.json()
    assert body["kind"] == "txt"
    assert body["cached"] is False
    assert body["resume_summary"]["has_email"] is True
    assert body["resume_summary"]["experience_entries"] == 2


async def test_upload_pdf_resume(client: AsyncClient) -> None:
    session_id = await new_session(client)
    response = await _upload(
        client, session_id, make_pdf_bytes(), "resume.pdf", "application/pdf"
    )
    assert response.status_code == 201
    assert response.json()["kind"] == "pdf"


async def test_upload_docx_resume(client: AsyncClient) -> None:
    session_id = await new_session(client)
    data = make_docx_bytes()
    response = await _upload(
        client,
        session_id,
        data,
        "resume.docx",
        "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
    )
    assert response.status_code == 201
    assert response.json()["kind"] == "docx"


async def test_client_claimed_content_type_is_ignored(client: AsyncClient) -> None:
    """A PDF uploaded with a lying Content-Type is still sniffed and processed correctly."""
    session_id = await new_session(client)
    response = await _upload(
        client, session_id, make_pdf_bytes(), "resume.pdf", "text/plain"
    )
    assert response.status_code == 201
    assert response.json()["kind"] == "pdf"


async def test_unsupported_file_type_rejected(client: AsyncClient) -> None:
    session_id = await new_session(client)
    response = await _upload(
        client, session_id, make_random_binary_bytes(), "file.bin", "application/octet-stream"
    )
    assert response.status_code == 422
    assert response.json()["error"]["code"] == "UNSUPPORTED_FILE_TYPE"


async def test_empty_upload_rejected(client: AsyncClient) -> None:
    session_id = await new_session(client)
    response = await _upload(client, session_id, b"", "empty.txt", "text/plain")
    assert response.status_code == 422
    assert response.json()["error"]["code"] == "EMPTY_FILE"


async def test_oversized_upload_rejected(client: AsyncClient, settings) -> None:
    session_id = await new_session(client)
    oversized = b"a" * (settings.max_upload_bytes + 1)
    response = await _upload(client, session_id, oversized, "big.txt", "text/plain")
    assert response.status_code == 422
    assert response.json()["error"]["code"] == "FILE_TOO_LARGE"


async def test_zip_bomb_shaped_docx_rejected(client: AsyncClient) -> None:
    session_id = await new_session(client)
    data = make_zip_bomb_docx_bytes(entries=10, entry_size=30_000_000)
    response = await _upload(
        client,
        session_id,
        data,
        "bomb.docx",
        "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
    )
    assert response.status_code == 422
    assert response.json()["error"]["code"] == "DOCUMENT_STRUCTURE_REJECTED"


async def test_reupload_of_identical_bytes_is_a_cache_hit(client: AsyncClient) -> None:
    session_id = await new_session(client)
    data = make_txt_bytes()
    first = await _upload(client, session_id, data, "resume.txt", "text/plain")
    second = await _upload(client, session_id, data, "resume.txt", "text/plain")

    assert first.json()["cached"] is False
    assert second.json()["cached"] is True
    assert first.json()["document_id"] == second.json()["document_id"]


async def test_different_bytes_are_not_cached_together(client: AsyncClient) -> None:
    session_id = await new_session(client)
    first = await _upload(client, session_id, make_txt_bytes(), "a.txt", "text/plain")
    second = await _upload(
        client, session_id, make_txt_bytes("different content\n"), "b.txt", "text/plain"
    )
    assert first.json()["document_id"] != second.json()["document_id"]


async def test_get_document_returns_full_structured_resume(client: AsyncClient) -> None:
    session_id = await new_session(client)
    upload = await _upload(client, session_id, make_txt_bytes(), "resume.txt", "text/plain")
    document_id = upload.json()["document_id"]

    response = await client.get(
        f"/v1/documents/{document_id}", headers={"X-Session-Id": session_id}
    )
    assert response.status_code == 200
    body = response.json()
    assert body["resume"]["contact"]["full_name"]["value"] == "Jordan Ellery Vance"
    assert SYNTHETIC_RESUME_TEXT.split("\n")[0] in body["text"]


async def test_get_unknown_document_is_404(client: AsyncClient) -> None:
    session_id = await new_session(client)
    response = await client.get(
        "/v1/documents/does-not-exist", headers={"X-Session-Id": session_id}
    )
    assert response.status_code == 404
    assert response.json()["error"]["code"] == "NOT_FOUND"


async def test_delete_document_removes_it(client: AsyncClient) -> None:
    session_id = await new_session(client)
    upload = await _upload(client, session_id, make_txt_bytes(), "resume.txt", "text/plain")
    document_id = upload.json()["document_id"]

    delete_response = await client.delete(
        f"/v1/documents/{document_id}", headers={"X-Session-Id": session_id}
    )
    assert delete_response.status_code == 204

    get_response = await client.get(
        f"/v1/documents/{document_id}", headers={"X-Session-Id": session_id}
    )
    assert get_response.status_code == 404


async def test_delete_unknown_document_is_still_204(client: AsyncClient) -> None:
    session_id = await new_session(client)
    response = await client.delete(
        "/v1/documents/does-not-exist", headers={"X-Session-Id": session_id}
    )
    assert response.status_code == 204


async def test_job_description_upload_skips_resume_structuring(client: AsyncClient) -> None:
    session_id = await new_session(client)
    files = {"file": ("jd.txt", b"We need a backend engineer.", "text/plain")}
    response = await client.post(
        "/v1/documents",
        files=files,
        data={"kind": "job_description"},
        headers={"X-Session-Id": session_id},
    )
    assert response.status_code == 201
    assert response.json()["resume_summary"] is None


async def test_upload_increments_the_session_document_counter(client: AsyncClient) -> None:
    session_id = await new_session(client)
    before = await client.get("/v1/session", headers={"X-Session-Id": session_id})
    assert before.json()["counters"]["documents"] == 0

    await _upload(client, session_id, make_txt_bytes(), "resume.txt", "text/plain")

    after = await client.get("/v1/session", headers={"X-Session-Id": session_id})
    assert after.json()["counters"]["documents"] == 1


async def test_document_upload_rate_limited(rate_limited_client: AsyncClient) -> None:
    session_response = await rate_limited_client.post("/v1/session", json={"mode": "candidate"})
    session_id = session_response.json()["session_id"]

    statuses = []
    for _ in range(8):
        response = await _upload(
            rate_limited_client, session_id, make_txt_bytes(), "resume.txt", "text/plain"
        )
        statuses.append(response.status_code)
    assert 429 in statuses
