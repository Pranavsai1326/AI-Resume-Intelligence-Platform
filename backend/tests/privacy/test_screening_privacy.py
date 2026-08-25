"""Zero-persistence and blind-review guarantees for recruiter screening (Phase 7).

Extends the document/matching privacy suites: a candidate's resume content must never appear in
logs, screening data must be destroyed with its session, one session must never reach another's
candidate pool, and - specific to screening - the *stored* candidate result must never carry the
candidate's real name or contact details, since blind review (PRD section 8, SECURITY.md
section 10) depends on redaction happening before storage, not on a later display-time filter
that a future endpoint could forget to apply.
"""

from __future__ import annotations

import asyncio

import pytest
from httpx import AsyncClient

from tests.conftest import new_session
from tests.privacy.test_document_privacy import CANARY_RESUME_TEXT
from tests.privacy.test_zero_persistence import CANARY_TOKENS

CANARY_JD_TEXT = "Requirements\n- Proficiency in Palewind-flavoured Python\n"


async def _create_job(client: AsyncClient, session_id: str) -> str:
    response = await client.post(
        "/v1/jobs", json={"text": CANARY_JD_TEXT}, headers={"X-Session-Id": session_id}
    )
    return str(response.json()["job_id"])


async def _create_screening(client: AsyncClient, session_id: str, job_id: str) -> str:
    response = await client.post(
        "/v1/screening", json={"job_id": job_id}, headers={"X-Session-Id": session_id}
    )
    return str(response.json()["screening_id"])


async def _upload_one_canary_candidate(
    client: AsyncClient, session_id: str, screening_id: str
) -> str:
    files = [("files", ("resume.txt", CANARY_RESUME_TEXT, "text/plain"))]
    response = await client.post(
        f"/v1/screening/{screening_id}/candidates",
        files=files,
        headers={"X-Session-Id": session_id},
    )
    return str(response.json()["candidate_ids"][0])


async def _wait_for_completion(
    client: AsyncClient, session_id: str, screening_id: str, timeout_seconds: float = 10.0
) -> None:
    async with asyncio.timeout(timeout_seconds):
        while True:
            response = await client.get(
                f"/v1/screening/{screening_id}/status", headers={"X-Session-Id": session_id}
            )
            body = response.json()
            if body["completed"] + body["failed"] >= 1:
                return
            await asyncio.sleep(0.05)


async def test_candidate_name_never_appears_in_the_stored_result(client: AsyncClient) -> None:
    """The name in the canary resume must never survive into the API response - not filtered at
    display time, but genuinely absent because redaction runs before storage."""
    session_id = await new_session(client, mode="recruiter")
    job_id = await _create_job(client, session_id)
    screening_id = await _create_screening(client, session_id, job_id)
    candidate_id = await _upload_one_canary_candidate(client, session_id, screening_id)
    await _wait_for_completion(client, session_id, screening_id)

    response = await client.get(
        f"/v1/screening/{screening_id}/candidates/{candidate_id}",
        headers={"X-Session-Id": session_id},
    )
    body = response.json()
    assert body["resume"]["contact"]["full_name"] is None
    assert body["resume"]["contact"]["email"] is None
    raw_text = response.text
    assert "Zorvath" not in raw_text
    assert "Quillfeather" not in raw_text
    assert "zorvath.quillfeather" not in raw_text


async def test_screening_pipeline_logs_no_candidate_content(
    client: AsyncClient, capsys: pytest.CaptureFixture[str]
) -> None:
    session_id = await new_session(client, mode="recruiter")
    job_id = await _create_job(client, session_id)
    screening_id = await _create_screening(client, session_id, job_id)
    await _upload_one_canary_candidate(client, session_id, screening_id)
    await _wait_for_completion(client, session_id, screening_id)

    output = capsys.readouterr().out
    for token in CANARY_TOKENS:
        assert token not in output
    assert "Zorvath" not in output
    assert "Cindervale" not in output
    assert "Palewind" not in output


async def test_session_b_cannot_reach_session_as_screening(client: AsyncClient) -> None:
    session_a = await new_session(client, mode="recruiter")
    session_b = await new_session(client, mode="recruiter")

    job_id = await _create_job(client, session_a)
    screening_id = await _create_screening(client, session_a, job_id)
    candidate_id = await _upload_one_canary_candidate(client, session_a, screening_id)
    await _wait_for_completion(client, session_a, screening_id)

    for path in (
        f"/v1/screening/{screening_id}/status",
        f"/v1/screening/{screening_id}/ranking",
        f"/v1/screening/{screening_id}/candidates/{candidate_id}",
    ):
        response = await client.get(path, headers={"X-Session-Id": session_b})
        assert response.status_code == 404, path

    compare = await client.post(
        f"/v1/screening/{screening_id}/compare",
        json={"candidate_ids": [candidate_id]},
        headers={"X-Session-Id": session_b},
    )
    assert compare.status_code == 404

    shortlist = await client.post(
        f"/v1/screening/{screening_id}/shortlist",
        json={"candidate_id": candidate_id, "shortlisted": True},
        headers={"X-Session-Id": session_b},
    )
    assert shortlist.status_code == 404


async def test_screening_data_is_destroyed_with_the_session(client: AsyncClient) -> None:
    session_id = await new_session(client, mode="recruiter")
    job_id = await _create_job(client, session_id)
    screening_id = await _create_screening(client, session_id, job_id)
    await _upload_one_canary_candidate(client, session_id, screening_id)
    await _wait_for_completion(client, session_id, screening_id)

    await client.delete("/v1/session", headers={"X-Session-Id": session_id})

    response = await client.get(
        f"/v1/screening/{screening_id}/status", headers={"X-Session-Id": session_id}
    )
    assert response.status_code == 410  # the session itself is gone
