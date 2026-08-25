"""Job description API: create from pasted text or an uploaded document, retrieve, isolate."""

from __future__ import annotations

from httpx import AsyncClient

from tests.conftest import new_session

JD_TEXT = "Requirements\n- 3+ years of experience\n- Proficiency in Python\n"


async def test_create_job_from_pasted_text(client: AsyncClient) -> None:
    session_id = await new_session(client)
    response = await client.post(
        "/v1/jobs", json={"text": JD_TEXT}, headers={"X-Session-Id": session_id}
    )
    assert response.status_code == 201
    body = response.json()
    assert body["job_id"]
    assert len(body["job"]["requirements"]) == 2


async def test_create_job_from_uploaded_document(client: AsyncClient) -> None:
    session_id = await new_session(client)
    files = {"file": ("jd.txt", JD_TEXT.encode(), "text/plain")}
    upload = await client.post(
        "/v1/documents",
        files=files,
        data={"kind": "job_description"},
        headers={"X-Session-Id": session_id},
    )
    document_id = upload.json()["document_id"]

    response = await client.post(
        "/v1/jobs", json={"document_id": document_id}, headers={"X-Session-Id": session_id}
    )
    assert response.status_code == 201
    assert len(response.json()["job"]["requirements"]) == 2


async def test_requires_exactly_one_source(client: AsyncClient) -> None:
    session_id = await new_session(client)
    both = await client.post(
        "/v1/jobs",
        json={"text": JD_TEXT, "document_id": "x"},
        headers={"X-Session-Id": session_id},
    )
    assert both.status_code == 422

    neither = await client.post("/v1/jobs", json={}, headers={"X-Session-Id": session_id})
    assert neither.status_code == 422


async def test_empty_text_is_rejected(client: AsyncClient) -> None:
    session_id = await new_session(client)
    response = await client.post(
        "/v1/jobs", json={"text": "   "}, headers={"X-Session-Id": session_id}
    )
    assert response.status_code == 422
    assert response.json()["error"]["code"] == "VALIDATION_FAILED"


async def test_unknown_document_id_is_404(client: AsyncClient) -> None:
    session_id = await new_session(client)
    response = await client.post(
        "/v1/jobs", json={"document_id": "does-not-exist"}, headers={"X-Session-Id": session_id}
    )
    assert response.status_code == 404


async def test_get_job_by_id(client: AsyncClient) -> None:
    session_id = await new_session(client)
    create = await client.post(
        "/v1/jobs", json={"text": JD_TEXT}, headers={"X-Session-Id": session_id}
    )
    job_id = create.json()["job_id"]

    response = await client.get(f"/v1/jobs/{job_id}", headers={"X-Session-Id": session_id})
    assert response.status_code == 200
    assert response.json()["job_id"] == job_id


async def test_get_unknown_job_is_404(client: AsyncClient) -> None:
    session_id = await new_session(client)
    response = await client.get(
        "/v1/jobs/does-not-exist", headers={"X-Session-Id": session_id}
    )
    assert response.status_code == 404


async def test_job_requires_a_session(client: AsyncClient) -> None:
    response = await client.post("/v1/jobs", json={"text": JD_TEXT})
    assert response.status_code == 400


async def test_session_b_cannot_fetch_session_a_job(client: AsyncClient) -> None:
    session_a = await new_session(client)
    session_b = await new_session(client)
    create = await client.post(
        "/v1/jobs", json={"text": JD_TEXT}, headers={"X-Session-Id": session_a}
    )
    job_id = create.json()["job_id"]

    response = await client.get(f"/v1/jobs/{job_id}", headers={"X-Session-Id": session_b})
    assert response.status_code == 404
