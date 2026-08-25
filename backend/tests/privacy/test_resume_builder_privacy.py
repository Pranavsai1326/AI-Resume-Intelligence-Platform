"""Privacy properties of Phase 5's resume builder: versions, tailoring, export.

Proves the same guarantees PRIVACY_ARCHITECTURE.md makes for every other session object apply
here too - session-scoped, isolated between sessions, and gone on session destruction - rather
than assuming they hold just because the underlying storage layer is shared.
"""

from __future__ import annotations

import pytest
from httpx import AsyncClient

from tests.conftest import new_session
from tests.fixtures import make_txt_bytes

CANARY_LABEL = "Zorvath Quillfeather private edit"


async def _upload_document(client: AsyncClient, session_id: str) -> str:
    files = {"file": ("resume.txt", make_txt_bytes(), "text/plain")}
    upload = await client.post(
        "/v1/documents", files=files, headers={"X-Session-Id": session_id}
    )
    return str(upload.json()["document_id"])


async def test_versions_are_isolated_between_sessions(client: AsyncClient) -> None:
    session_a = await new_session(client)
    session_b = await new_session(client)
    document_id = await _upload_document(client, session_a)

    # Session A can see its own version.
    listed_a = await client.get(
        "/v1/resume/versions",
        params={"document_id": document_id},
        headers={"X-Session-Id": session_a},
    )
    assert listed_a.status_code == 200
    version_id = listed_a.json()[0]["version_id"]

    # Session B, which never uploaded this document, cannot see it or the version.
    listed_b = await client.get(
        "/v1/resume/versions",
        params={"document_id": document_id},
        headers={"X-Session-Id": session_b},
    )
    assert listed_b.status_code == 404

    fetched_b = await client.get(
        f"/v1/resume/versions/{version_id}", headers={"X-Session-Id": session_b}
    )
    assert fetched_b.status_code == 404


async def test_versions_are_destroyed_when_session_ends(client: AsyncClient) -> None:
    session_id = await new_session(client)
    document_id = await _upload_document(client, session_id)

    listed = await client.get(
        "/v1/resume/versions",
        params={"document_id": document_id},
        headers={"X-Session-Id": session_id},
    )
    version_id = listed.json()[0]["version_id"]

    await client.delete("/v1/session", headers={"X-Session-Id": session_id})

    response = await client.get(
        f"/v1/resume/versions/{version_id}", headers={"X-Session-Id": session_id}
    )
    assert response.status_code == 410  # session itself is gone


async def test_tailor_proposals_use_session_scoped_documents_and_jobs(client: AsyncClient) -> None:
    session_a = await new_session(client)
    session_b = await new_session(client)
    document_id = await _upload_document(client, session_a)
    job = await client.post(
        "/v1/jobs",
        json={"text": "Requirements\n- Proficiency in Python\n"},
        headers={"X-Session-Id": session_a},
    )
    job_id = job.json()["job_id"]

    response = await client.post(
        "/v1/tailor",
        json={"document_id": document_id, "job_id": job_id},
        headers={"X-Session-Id": session_b},
    )
    assert response.status_code == 404


async def test_exported_file_reflects_only_the_requesting_sessions_data(
    client: AsyncClient,
) -> None:
    session_a = await new_session(client)
    session_b = await new_session(client)
    document_id = await _upload_document(client, session_a)

    response = await client.post(
        "/v1/export",
        json={"document_id": document_id, "format": "docx"},
        headers={"X-Session-Id": session_b},
    )
    assert response.status_code == 404


async def test_version_label_content_does_not_leak_into_logs(
    client: AsyncClient, capsys: pytest.CaptureFixture[str]
) -> None:
    session_id = await new_session(client)
    document_id = await _upload_document(client, session_id)

    original = await client.get(
        "/v1/resume/versions",
        params={"document_id": document_id},
        headers={"X-Session-Id": session_id},
    )
    original_version_id = original.json()[0]["version_id"]

    await client.post(
        "/v1/resume/versions",
        json={
            "document_id": document_id,
            "label": CANARY_LABEL,
            "based_on_version_id": original_version_id,
        },
        headers={"X-Session-Id": session_id},
    )

    output = capsys.readouterr().out
    assert CANARY_LABEL not in output
    assert "Zorvath" not in output


async def test_rewrite_and_tailor_endpoints_log_no_resume_content(
    client: AsyncClient, capsys: pytest.CaptureFixture[str]
) -> None:
    session_id = await new_session(client)
    document_id = await _upload_document(client, session_id)
    canary_bullet = "Zorvath Quillfeather built the Palewind ingestion service."

    await client.post(
        "/v1/ai/rewrite",
        json={"document_id": document_id, "kind": "bullet", "text": canary_bullet},
        headers={"X-Session-Id": session_id},
    )
    job = await client.post(
        "/v1/jobs",
        json={"text": "Requirements\n- Proficiency in Python\n"},
        headers={"X-Session-Id": session_id},
    )
    job_id = job.json()["job_id"]
    await client.post(
        "/v1/tailor",
        json={"document_id": document_id, "job_id": job_id},
        headers={"X-Session-Id": session_id},
    )
    await client.post(
        "/v1/export",
        json={"document_id": document_id, "format": "docx"},
        headers={"X-Session-Id": session_id},
    )

    output = capsys.readouterr().out
    assert "Zorvath" not in output
    assert "Quillfeather" not in output
    assert "Palewind" not in output


async def test_career_endpoints_use_session_scoped_documents_and_jobs(client: AsyncClient) -> None:
    """Phase 6: cover letter, interview prep, and learning priorities all reuse the same
    document/job lookup as tailoring - one session must not be able to reach another's."""
    session_a = await new_session(client)
    session_b = await new_session(client)
    document_id = await _upload_document(client, session_a)
    job = await client.post(
        "/v1/jobs",
        json={"text": "Requirements\n- Proficiency in Python\n"},
        headers={"X-Session-Id": session_a},
    )
    job_id = job.json()["job_id"]

    for path in ("/v1/cover-letter", "/v1/interview/questions", "/v1/learning-priorities"):
        response = await client.post(
            path,
            json={"document_id": document_id, "job_id": job_id},
            headers={"X-Session-Id": session_b},
        )
        assert response.status_code == 404, path


async def test_career_endpoints_log_no_resume_or_job_content(
    client: AsyncClient, capsys: pytest.CaptureFixture[str]
) -> None:
    session_id = await new_session(client)
    document_id = await _upload_document(client, session_id)
    job = await client.post(
        "/v1/jobs",
        json={"text": "Requirements\n- Proficiency in Zorvathium scripting\n"},
        headers={"X-Session-Id": session_id},
    )
    job_id = job.json()["job_id"]

    for path in ("/v1/cover-letter", "/v1/interview/questions", "/v1/learning-priorities"):
        await client.post(
            path,
            json={"document_id": document_id, "job_id": job_id},
            headers={"X-Session-Id": session_id},
        )

    output = capsys.readouterr().out
    assert "Zorvathium" not in output
    assert "Quillfeather" not in output
