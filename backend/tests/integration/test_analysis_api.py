"""Resume analysis API: upload a document, analyze it, retrieve and cache the result."""

from __future__ import annotations

from httpx import AsyncClient

from tests.conftest import new_session
from tests.fixtures import SYNTHETIC_RESUME_TEXT, make_txt_bytes


async def _upload(client: AsyncClient, session_id: str) -> str:
    files = {"file": ("resume.txt", make_txt_bytes(), "text/plain")}
    response = await client.post(
        "/v1/documents", files=files, headers={"X-Session-Id": session_id}
    )
    document_id: str = response.json()["document_id"]
    return document_id


async def test_analyze_returns_all_six_components(client: AsyncClient) -> None:
    session_id = await new_session(client)
    document_id = await _upload(client, session_id)

    response = await client.post(
        "/v1/analysis/resume",
        json={"document_id": document_id},
        headers={"X-Session-Id": session_id},
    )
    assert response.status_code == 201
    body = response.json()
    assert set(body["components"]) == {
        "ats_compatibility", "content_quality", "skills_coverage",
        "experience_quality", "formatting", "impact",
    }
    assert 0 <= body["overall"] <= 100
    assert body["degraded"] == []


async def test_every_score_carries_evidence_and_an_explanation(client: AsyncClient) -> None:
    """No component may return a bare number - API.md's explainability requirement, over HTTP."""
    session_id = await new_session(client)
    document_id = await _upload(client, session_id)

    response = await client.post(
        "/v1/analysis/resume",
        json={"document_id": document_id},
        headers={"X-Session-Id": session_id},
    )
    for component in response.json()["components"].values():
        assert component["explanation"]
        assert len(component["evidence"]) > 0
        for item in component["evidence"]:
            assert item["message"]
            assert item["severity"] in {"positive", "info", "warning"}


async def test_analysis_requires_a_session(client: AsyncClient) -> None:
    response = await client.post("/v1/analysis/resume", json={"document_id": "x"})
    assert response.status_code == 400


async def test_analyzing_unknown_document_is_404(client: AsyncClient) -> None:
    session_id = await new_session(client)
    response = await client.post(
        "/v1/analysis/resume",
        json={"document_id": "does-not-exist"},
        headers={"X-Session-Id": session_id},
    )
    assert response.status_code == 404


async def test_analyzing_a_job_description_document_is_rejected(client: AsyncClient) -> None:
    session_id = await new_session(client)
    files = {"file": ("jd.txt", b"We need a backend engineer.", "text/plain")}
    upload = await client.post(
        "/v1/documents",
        files=files,
        data={"kind": "job_description"},
        headers={"X-Session-Id": session_id},
    )
    document_id = upload.json()["document_id"]

    response = await client.post(
        "/v1/analysis/resume",
        json={"document_id": document_id},
        headers={"X-Session-Id": session_id},
    )
    assert response.status_code == 422
    assert response.json()["error"]["code"] == "VALIDATION_FAILED"


async def test_reanalysis_of_the_same_document_is_a_cache_hit(client: AsyncClient) -> None:
    session_id = await new_session(client)
    document_id = await _upload(client, session_id)

    first = await client.post(
        "/v1/analysis/resume",
        json={"document_id": document_id},
        headers={"X-Session-Id": session_id},
    )
    second = await client.post(
        "/v1/analysis/resume",
        json={"document_id": document_id},
        headers={"X-Session-Id": session_id},
    )
    assert first.json() == second.json()


async def test_get_analysis_by_id(client: AsyncClient) -> None:
    session_id = await new_session(client)
    document_id = await _upload(client, session_id)

    await client.post(
        "/v1/analysis/resume",
        json={"document_id": document_id},
        headers={"X-Session-Id": session_id},
    )
    response = await client.get(
        f"/v1/analysis/{document_id}", headers={"X-Session-Id": session_id}
    )
    assert response.status_code == 200
    assert "overall" in response.json()


async def test_get_unknown_analysis_is_404(client: AsyncClient) -> None:
    session_id = await new_session(client)
    response = await client.get(
        "/v1/analysis/does-not-exist", headers={"X-Session-Id": session_id}
    )
    assert response.status_code == 404


async def test_analysis_increments_the_session_counter(client: AsyncClient) -> None:
    session_id = await new_session(client)
    document_id = await _upload(client, session_id)

    before = await client.get("/v1/session", headers={"X-Session-Id": session_id})
    assert before.json()["counters"]["analyses"] == 0

    await client.post(
        "/v1/analysis/resume",
        json={"document_id": document_id},
        headers={"X-Session-Id": session_id},
    )

    after = await client.get("/v1/session", headers={"X-Session-Id": session_id})
    assert after.json()["counters"]["analyses"] == 1


async def test_session_b_cannot_analyze_session_a_document(client: AsyncClient) -> None:
    session_a = await new_session(client)
    session_b = await new_session(client)
    document_id = await _upload(client, session_a)

    response = await client.post(
        "/v1/analysis/resume",
        json={"document_id": document_id},
        headers={"X-Session-Id": session_b},
    )
    assert response.status_code == 404


async def test_analysis_reflects_the_uploaded_content(client: AsyncClient) -> None:
    session_id = await new_session(client)
    document_id = await _upload(client, session_id)

    response = await client.post(
        "/v1/analysis/resume",
        json={"document_id": document_id},
        headers={"X-Session-Id": session_id},
    )
    body = response.json()
    assert body["components"]["skills_coverage"]["score"] > 0
    assert SYNTHETIC_RESUME_TEXT.split("\n")[0]  # sanity: fixture still has the expected shape
