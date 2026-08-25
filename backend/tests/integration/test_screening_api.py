"""Integration tests for the recruiter screening endpoints.

Bulk processing genuinely runs as background asyncio tasks (app.queue.inprocess), so these tests
poll GET .../status the same way a real client would, rather than assuming synchronous
completion - a fake or mocked queue would not exercise the actual async path these endpoints
promise.
"""

from __future__ import annotations

import asyncio
from collections.abc import AsyncIterator
from pathlib import Path

import pytest
from httpx import ASGITransport, AsyncClient

from app.config import Settings
from app.main import create_app
from tests.conftest import new_session
from tests.fixtures import make_txt_bytes

JD_TEXT = "Requirements\n- Proficiency in Python\n- Rust required\n"


async def _create_job(client: AsyncClient, session_id: str, text: str = JD_TEXT) -> str:
    response = await client.post(
        "/v1/jobs", json={"text": text}, headers={"X-Session-Id": session_id}
    )
    return str(response.json()["job_id"])


async def _create_screening(client: AsyncClient, session_id: str, job_id: str) -> str:
    response = await client.post(
        "/v1/screening", json={"job_id": job_id}, headers={"X-Session-Id": session_id}
    )
    assert response.status_code == 201, response.text
    return str(response.json()["screening_id"])


async def _upload_candidates(
    client: AsyncClient, session_id: str, screening_id: str, count: int = 2
) -> list[str]:
    files = [
        ("files", (f"resume-{i}.txt", make_txt_bytes(), "text/plain")) for i in range(count)
    ]
    response = await client.post(
        f"/v1/screening/{screening_id}/candidates",
        files=files,
        headers={"X-Session-Id": session_id},
    )
    assert response.status_code == 202, response.text
    return list(response.json()["candidate_ids"])


async def _wait_for_completion(
    client: AsyncClient,
    session_id: str,
    screening_id: str,
    expected: int,
    timeout_seconds: float = 10.0,
) -> dict[str, object]:
    async with asyncio.timeout(timeout_seconds):
        while True:
            response = await client.get(
                f"/v1/screening/{screening_id}/status", headers={"X-Session-Id": session_id}
            )
            body = response.json()
            if body["completed"] + body["failed"] >= expected:
                return dict(body)
            await asyncio.sleep(0.05)


async def test_create_screening_requires_an_existing_job(client: AsyncClient) -> None:
    session_id = await new_session(client, mode="recruiter")
    response = await client.post(
        "/v1/screening", json={"job_id": "does-not-exist"}, headers={"X-Session-Id": session_id}
    )
    assert response.status_code == 404


async def test_full_screening_flow_end_to_end(client: AsyncClient) -> None:
    session_id = await new_session(client, mode="recruiter")
    job_id = await _create_job(client, session_id)
    screening_id = await _create_screening(client, session_id, job_id)

    candidate_ids = await _upload_candidates(client, session_id, screening_id, count=2)
    assert len(candidate_ids) == 2

    status_body = await _wait_for_completion(client, session_id, screening_id, expected=2)
    assert status_body["completed"] == 2
    assert status_body["failed"] == 0

    ranking = await client.get(
        f"/v1/screening/{screening_id}/ranking", headers={"X-Session-Id": session_id}
    )
    assert ranking.status_code == 200
    ranked = ranking.json()
    assert ranked["total"] == 2
    scores = [c["match"]["overall"] for c in ranked["candidates"]]
    assert scores == sorted(scores, reverse=True)

    # Blind review by construction: no candidate result exposes an unredacted resume.
    for candidate in ranked["candidates"]:
        assert candidate["resume"]["contact"]["full_name"] is None
        assert candidate["redaction"]["applied"] is True
        assert "name" in candidate["redaction"]["fields"]

    one = await client.get(
        f"/v1/screening/{screening_id}/candidates/{candidate_ids[0]}",
        headers={"X-Session-Id": session_id},
    )
    assert one.status_code == 200
    assert one.json()["candidate_id"] == candidate_ids[0]

    compare = await client.post(
        f"/v1/screening/{screening_id}/compare",
        json={"candidate_ids": candidate_ids},
        headers={"X-Session-Id": session_id},
    )
    assert compare.status_code == 200
    assert len(compare.json()["rows"]) == 2

    shortlist = await client.post(
        f"/v1/screening/{screening_id}/shortlist",
        json={"candidate_id": candidate_ids[0], "shortlisted": True},
        headers={"X-Session-Id": session_id},
    )
    assert shortlist.status_code == 200
    assert shortlist.json()["shortlisted"] is True

    # Shortlist status persists on re-fetch.
    refetched = await client.get(
        f"/v1/screening/{screening_id}/candidates/{candidate_ids[0]}",
        headers={"X-Session-Id": session_id},
    )
    assert refetched.json()["shortlisted"] is True


async def test_ranking_min_score_filter(client: AsyncClient) -> None:
    session_id = await new_session(client, mode="recruiter")
    job_id = await _create_job(client, session_id)
    screening_id = await _create_screening(client, session_id, job_id)
    await _upload_candidates(client, session_id, screening_id, count=1)
    await _wait_for_completion(client, session_id, screening_id, expected=1)

    response = await client.get(
        f"/v1/screening/{screening_id}/ranking",
        params={"min_score": 1000.0},  # unreachable - nothing scores above 100
        headers={"X-Session-Id": session_id},
    )
    assert response.json()["total"] == 0


async def test_upload_candidates_rejects_an_empty_file_list(client: AsyncClient) -> None:
    session_id = await new_session(client, mode="recruiter")
    job_id = await _create_job(client, session_id)
    screening_id = await _create_screening(client, session_id, job_id)

    response = await client.post(
        f"/v1/screening/{screening_id}/candidates",
        files=[],
        headers={"X-Session-Id": session_id},
    )
    assert response.status_code == 422


@pytest.fixture
async def bulk_limited_client(tmp_path: Path) -> AsyncIterator[AsyncClient]:
    """A session-scoped bulk cap of 1, small enough to actually exercise the over-limit guard."""
    settings = Settings(
        app_env="development",
        debug=True,
        temp_dir=str(tmp_path / "tmp-bulk"),
        session_store_backend="memory",
        rate_limit_enabled=False,
        embedding_backend="none",
        log_format="json",
        max_bulk_resumes=1,
    )
    app = create_app(settings)
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as http:
        async with app.router.lifespan_context(app):
            yield http


async def test_upload_candidates_rejects_over_the_bulk_limit(
    bulk_limited_client: AsyncClient,
) -> None:
    session_id = await new_session(bulk_limited_client, mode="recruiter")
    job_id = await _create_job(bulk_limited_client, session_id)
    screening_id = await _create_screening(bulk_limited_client, session_id, job_id)

    response = await bulk_limited_client.post(
        f"/v1/screening/{screening_id}/candidates",
        files=[
            ("files", ("a.txt", make_txt_bytes(), "text/plain")),
            ("files", ("b.txt", make_txt_bytes(), "text/plain")),
        ],
        headers={"X-Session-Id": session_id},
    )
    assert response.status_code == 422
    assert "1" in response.json()["error"]["message"]


async def test_candidates_unknown_screening_is_404(client: AsyncClient) -> None:
    session_id = await new_session(client, mode="recruiter")
    response = await client.get(
        "/v1/screening/does-not-exist/status", headers={"X-Session-Id": session_id}
    )
    assert response.status_code == 404


async def test_screening_endpoints_require_a_session(client: AsyncClient) -> None:
    response = await client.post("/v1/screening", json={"job_id": "j1"})
    assert response.status_code == 400
