"""Integration tests for POST /v1/cover-letter, /v1/interview/questions, /v1/learning-priorities."""

from __future__ import annotations

from httpx import AsyncClient

from tests.conftest import new_session
from tests.fixtures import make_txt_bytes

JD_TEXT = "Requirements\n- 3+ years of experience\n- Proficiency in Python\n- Rust required\n"


async def _setup_document_and_job(client: AsyncClient, session_id: str) -> tuple[str, str]:
    files = {"file": ("resume.txt", make_txt_bytes(), "text/plain")}
    upload = await client.post(
        "/v1/documents", files=files, headers={"X-Session-Id": session_id}
    )
    document_id = upload.json()["document_id"]

    job = await client.post(
        "/v1/jobs", json={"text": JD_TEXT}, headers={"X-Session-Id": session_id}
    )
    job_id = job.json()["job_id"]
    return document_id, job_id


async def test_cover_letter_with_no_llm_configured_is_honestly_unavailable(
    client: AsyncClient,
) -> None:
    session_id = await new_session(client)
    document_id, job_id = await _setup_document_and_job(client, session_id)

    response = await client.post(
        "/v1/cover-letter",
        json={"document_id": document_id, "job_id": job_id},
        headers={"X-Session-Id": session_id},
    )
    assert response.status_code == 200
    body = response.json()
    assert body["available"] is False
    assert body["unavailable_reason"] == "AI writing is not configured on this deployment."
    assert body["body_paragraphs"] == []


async def test_interview_questions_with_no_llm_configured_is_honestly_unavailable(
    client: AsyncClient,
) -> None:
    session_id = await new_session(client)
    document_id, job_id = await _setup_document_and_job(client, session_id)

    response = await client.post(
        "/v1/interview/questions",
        json={"document_id": document_id, "job_id": job_id},
        headers={"X-Session-Id": session_id},
    )
    assert response.status_code == 200
    body = response.json()
    assert body["available"] is False
    assert body["questions"] == []


async def test_learning_priorities_needs_no_llm_at_all(client: AsyncClient) -> None:
    session_id = await new_session(client)
    document_id, job_id = await _setup_document_and_job(client, session_id)

    response = await client.post(
        "/v1/learning-priorities",
        json={"document_id": document_id, "job_id": job_id},
        headers={"X-Session-Id": session_id},
    )
    assert response.status_code == 200
    body = response.json()
    assert isinstance(body["priorities"], list)
    # Rust is required by the JD and absent from the synthetic resume fixture.
    assert any(p["skill"].lower() == "rust" for p in body["priorities"])


async def test_career_endpoints_unknown_job_is_404(client: AsyncClient) -> None:
    session_id = await new_session(client)
    document_id, _job_id = await _setup_document_and_job(client, session_id)

    for path in ("/v1/cover-letter", "/v1/interview/questions", "/v1/learning-priorities"):
        response = await client.post(
            path,
            json={"document_id": document_id, "job_id": "does-not-exist"},
            headers={"X-Session-Id": session_id},
        )
        assert response.status_code == 404, path


async def test_career_endpoints_require_a_session(client: AsyncClient) -> None:
    for path in ("/v1/cover-letter", "/v1/interview/questions", "/v1/learning-priorities"):
        response = await client.post(path, json={"document_id": "d1", "job_id": "j1"})
        assert response.status_code == 400, path
