"""End-to-end proof that logs carry no user content.

The unit tests exercise the redaction processor; this drives the real application and asserts on
what actually lands on stdout.
"""

from __future__ import annotations

import logging

import pytest
from httpx import ASGITransport, AsyncClient

from app.config import Settings
from app.logging import configure_logging, get_logger
from app.main import create_app
from tests.conftest import new_session
from tests.privacy.test_zero_persistence import (
    CANARY_EMAIL,
    CANARY_NAME,
    CANARY_RESUME,
    CANARY_TOKENS,
)


async def test_request_logs_contain_no_user_content(
    tmp_path: object, capsys: pytest.CaptureFixture[str]
) -> None:
    settings = Settings(
        app_env="development",
        temp_dir=str(tmp_path),
        session_store_backend="memory",
        rate_limit_enabled=False,
        log_format="json",
    )
    app = create_app(settings)

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as http:
        async with app.router.lifespan_context(app):
            session_id = await new_session(http)
            manager = app.state.session_manager
            meta = await manager.require(session_id)
            await manager.put_object(meta, "document", "d1", CANARY_RESUME)
            await http.get("/v1/session", headers={"X-Session-Id": session_id})
            await http.delete("/v1/session", headers={"X-Session-Id": session_id})

    output = capsys.readouterr().out
    assert output, "expected structured logs to be emitted"
    for token in CANARY_TOKENS:
        assert token not in output, f"user content leaked into logs: {token}"
    assert CANARY_EMAIL not in output


async def test_full_session_id_is_never_logged(
    tmp_path: object, capsys: pytest.CaptureFixture[str]
) -> None:
    """Session ids are correlation aids, truncated so they cannot be replayed from a log."""
    settings = Settings(
        app_env="development",
        temp_dir=str(tmp_path),
        session_store_backend="memory",
        rate_limit_enabled=False,
        log_format="json",
    )
    app = create_app(settings)
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as http:
        async with app.router.lifespan_context(app):
            session_id = await new_session(http)
            await http.get("/v1/session", headers={"X-Session-Id": session_id})

    output = capsys.readouterr().out
    assert session_id not in output
    assert session_id[:8] in output, "a truncated id should still be present for correlation"


def test_direct_logging_of_user_content_is_neutralised(
    capsys: pytest.CaptureFixture[str],
) -> None:
    """Even a careless call site cannot leak: redaction is in the pipeline, not the convention."""
    configure_logging(level="INFO", fmt="json")
    logger = get_logger("test")
    logger.info(
        "document.parsed",
        resume_text=CANARY_RESUME,
        name=CANARY_NAME,
        email=CANARY_EMAIL,
        note=f"candidate {CANARY_NAME} applied from Cindervale",
    )
    output = capsys.readouterr().out
    for token in CANARY_TOKENS:
        assert token not in output
    assert "document.parsed" in output


def test_third_party_library_logs_are_redacted_too(
    capsys: pytest.CaptureFixture[str],
) -> None:
    """Foreign loggers route through the same processors, so they cannot bypass redaction."""
    configure_logging(level="INFO", fmt="json")
    logging.getLogger("some.library").info("processing resume for %s", CANARY_NAME)
    output = capsys.readouterr().out
    assert CANARY_NAME not in output
    assert "Zorvath" not in output


def test_error_logs_record_type_not_message(capsys: pytest.CaptureFixture[str]) -> None:
    """Exception messages can embed user content, so only the category is recorded."""
    configure_logging(level="INFO", fmt="json")
    logger = get_logger("test")
    try:
        raise ValueError(f"failed parsing resume of {CANARY_NAME}")
    except ValueError as exc:
        logger.error("parse.failed", error_type=type(exc).__name__)

    output = capsys.readouterr().out
    assert "ValueError" in output
    assert CANARY_NAME not in output
