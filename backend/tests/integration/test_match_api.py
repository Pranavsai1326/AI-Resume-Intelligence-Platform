"""Resume<->job matching API: compute, cache, isolate.

Uses the default ``client`` fixture, whose settings run with ``embedding_backend="none"`` (see
conftest.py) - fast and hermetic. This means every match here genuinely exercises the degrade
path (project_relevance and semantic_relevance unavailable), which is the honest default for a
deployment where the embedding model has not been configured or cannot load - not a test
shortcut standing in for different behaviour.
"""

from __future__ import annotations

from httpx import AsyncClient

from tests.conftest import new_session
from tests.fixtures import make_txt_bytes

JD_TEXT = "Requirements\n- 3+ years of experience\n- Proficiency in Python\n"


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


async def test_match_returns_all_components_and_skill_gaps(client: AsyncClient) -> None:
    session_id = await new_session(client)
    document_id, job_id = await _setup_document_and_job(client, session_id)

    response = await client.post(
        "/v1/match",
        json={"document_id": document_id, "job_id": job_id},
        headers={"X-Session-Id": session_id},
    )
    assert response.status_code == 201
    body = response.json()
    assert set(body["components"]) == {
        "required_skills", "preferred_skills", "experience", "education",
        "project_relevance", "semantic_relevance",
    }
    assert 0 <= body["overall"] <= 100
    assert "entries" in body["skill_gaps"]


async def test_match_reports_semantic_components_as_degraded_without_embeddings(
    client: AsyncClient,
) -> None:
    session_id = await new_session(client)
    document_id, job_id = await _setup_document_and_job(client, session_id)

    response = await client.post(
        "/v1/match",
        json={"document_id": document_id, "job_id": job_id},
        headers={"X-Session-Id": session_id},
    )
    body = response.json()
    assert set(body["degraded"]) == {"project_relevance", "semantic_relevance"}
    assert body["skill_gaps"]["semantic_available"] is False


async def test_every_component_carries_evidence_and_explanation(client: AsyncClient) -> None:
    session_id = await new_session(client)
    document_id, job_id = await _setup_document_and_job(client, session_id)

    response = await client.post(
        "/v1/match",
        json={"document_id": document_id, "job_id": job_id},
        headers={"X-Session-Id": session_id},
    )
    for component in response.json()["components"].values():
        assert component["explanation"]
        assert len(component["evidence"]) > 0


async def test_match_requires_a_session(client: AsyncClient) -> None:
    response = await client.post("/v1/match", json={"document_id": "x", "job_id": "y"})
    assert response.status_code == 400


async def test_match_unknown_document_is_404(client: AsyncClient) -> None:
    session_id = await new_session(client)
    _document_id, job_id = await _setup_document_and_job(client, session_id)
    response = await client.post(
        "/v1/match",
        json={"document_id": "does-not-exist", "job_id": job_id},
        headers={"X-Session-Id": session_id},
    )
    assert response.status_code == 404


async def test_match_unknown_job_is_404(client: AsyncClient) -> None:
    session_id = await new_session(client)
    document_id, _job_id = await _setup_document_and_job(client, session_id)
    response = await client.post(
        "/v1/match",
        json={"document_id": document_id, "job_id": "does-not-exist"},
        headers={"X-Session-Id": session_id},
    )
    assert response.status_code == 404


async def test_matching_a_job_description_document_is_rejected(client: AsyncClient) -> None:
    session_id = await new_session(client)
    files = {"file": ("jd.txt", b"We need engineers.", "text/plain")}
    upload = await client.post(
        "/v1/documents",
        files=files,
        data={"kind": "job_description"},
        headers={"X-Session-Id": session_id},
    )
    document_id = upload.json()["document_id"]

    job = await client.post(
        "/v1/jobs", json={"text": JD_TEXT}, headers={"X-Session-Id": session_id}
    )
    job_id = job.json()["job_id"]

    response = await client.post(
        "/v1/match",
        json={"document_id": document_id, "job_id": job_id},
        headers={"X-Session-Id": session_id},
    )
    assert response.status_code == 422


async def test_repeated_match_is_a_cache_hit(client: AsyncClient) -> None:
    session_id = await new_session(client)
    document_id, job_id = await _setup_document_and_job(client, session_id)

    first = await client.post(
        "/v1/match",
        json={"document_id": document_id, "job_id": job_id},
        headers={"X-Session-Id": session_id},
    )
    second = await client.post(
        "/v1/match",
        json={"document_id": document_id, "job_id": job_id},
        headers={"X-Session-Id": session_id},
    )
    assert first.json() == second.json()


async def test_match_increments_the_analyses_counter(client: AsyncClient) -> None:
    session_id = await new_session(client)
    document_id, job_id = await _setup_document_and_job(client, session_id)

    before = await client.get("/v1/session", headers={"X-Session-Id": session_id})
    assert before.json()["counters"]["analyses"] == 0

    await client.post(
        "/v1/match",
        json={"document_id": document_id, "job_id": job_id},
        headers={"X-Session-Id": session_id},
    )

    after = await client.get("/v1/session", headers={"X-Session-Id": session_id})
    assert after.json()["counters"]["analyses"] == 1


async def test_session_b_cannot_match_using_session_a_resources(client: AsyncClient) -> None:
    session_a = await new_session(client)
    session_b = await new_session(client)
    document_id, job_id = await _setup_document_and_job(client, session_a)

    response = await client.post(
        "/v1/match",
        json={"document_id": document_id, "job_id": job_id},
        headers={"X-Session-Id": session_b},
    )
    assert response.status_code == 404
