"""Integration tests for POST /v1/tailor and POST /v1/tailor/apply."""

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


async def test_generate_tailor_proposals(client: AsyncClient) -> None:
    session_id = await new_session(client)
    document_id, job_id = await _setup_document_and_job(client, session_id)

    response = await client.post(
        "/v1/tailor",
        json={"document_id": document_id, "job_id": job_id},
        headers={"X-Session-Id": session_id},
    )
    assert response.status_code == 200
    proposals = response.json()
    assert isinstance(proposals, list)
    # No LLM configured -> only deterministic proposals (never requires_ai).
    assert all(p["requires_ai"] is False for p in proposals)
    for proposal in proposals:
        assert proposal["rationale"]
        assert proposal["proposal_id"]


async def test_apply_accepted_proposals_creates_a_new_ai_tailored_version(
    client: AsyncClient,
) -> None:
    session_id = await new_session(client)
    document_id, job_id = await _setup_document_and_job(client, session_id)

    generated = await client.post(
        "/v1/tailor",
        json={"document_id": document_id, "job_id": job_id},
        headers={"X-Session-Id": session_id},
    )
    proposals = generated.json()
    assert proposals, "expected at least one deterministic proposal for this job/resume pair"

    response = await client.post(
        "/v1/tailor/apply",
        json={"document_id": document_id, "label": "Tailored for role", "proposals": proposals},
        headers={"X-Session-Id": session_id},
    )
    assert response.status_code == 201
    body = response.json()
    assert body["source"] == "ai_tailored"
    assert body["label"] == "Tailored for role"
    assert body["based_on_version_id"] is not None


async def test_apply_with_no_proposals_still_creates_a_version(client: AsyncClient) -> None:
    session_id = await new_session(client)
    document_id, _job_id = await _setup_document_and_job(client, session_id)

    response = await client.post(
        "/v1/tailor/apply",
        json={"document_id": document_id, "label": "Untouched", "proposals": []},
        headers={"X-Session-Id": session_id},
    )
    assert response.status_code == 201
    assert response.json()["source"] == "ai_tailored"


async def test_tailor_unknown_job_is_404(client: AsyncClient) -> None:
    session_id = await new_session(client)
    document_id, _job_id = await _setup_document_and_job(client, session_id)
    response = await client.post(
        "/v1/tailor",
        json={"document_id": document_id, "job_id": "does-not-exist"},
        headers={"X-Session-Id": session_id},
    )
    assert response.status_code == 404


async def test_tailor_requires_a_session(client: AsyncClient) -> None:
    response = await client.post("/v1/tailor", json={"document_id": "d1", "job_id": "j1"})
    assert response.status_code == 400
