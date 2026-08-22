"""Structured logging with mandatory PII redaction.

Logs may carry operational facts only: request id, truncated session id, operation, status,
duration, error category, model name, token counts. They must never carry resume content, job
descriptions, personal identifiers, filenames or prompt bodies.

Redaction is enforced here, in a processor every log record passes through, rather than being
left to the discipline of individual call sites. See PRIVACY_ARCHITECTURE.md section 8.
"""

from __future__ import annotations

import logging
import re
import sys
from contextvars import ContextVar
from typing import Any

import structlog

request_id_var: ContextVar[str | None] = ContextVar("request_id", default=None)
session_id_var: ContextVar[str | None] = ContextVar("session_id", default=None)

#: Keys whose values are replaced wholesale, regardless of content.
SENSITIVE_KEYS = frozenset(
    {
        "resume", "resume_text", "resume_json", "text", "content", "raw_text",
        "job_description", "jd_text", "candidate", "candidates", "cover_letter",
        "prompt", "completion", "messages", "summary", "bullet", "bullets",
        "name", "full_name", "email", "phone", "address", "location",
        "filename", "file_name", "original_filename", "path", "file_path",
        "api_key", "authorization", "token", "secret", "password", "credentials",
        "body", "payload",
    }
)

REDACTED = "[redacted]"

#: Keys whose values this application generates itself (timestamps, levels, correlation ids).
#: They are exempt from value scrubbing because the digit patterns below otherwise mangle
#: timestamps into uselessness. Incoming request ids are sanitised at the middleware boundary
#: before they ever reach a log record, so nothing user-controlled is exempted here.
STRUCTURAL_KEYS = frozenset({"timestamp", "level", "logger", "request_id", "session"})

#: Values that look like direct identifiers are redacted even under a harmless-looking key.
_EMAIL_RE = re.compile(r"[\w.+-]+@[\w-]+\.[\w.-]+")
_PHONE_RE = re.compile(r"(?:\+?\d[\d\s().-]{7,}\d)")

#: Anything longer than this is assumed to be user content rather than an operational value.
MAX_VALUE_LENGTH = 120

#: Log values are identifiers, enums and numbers - never prose. A value with more than a handful
#: of words is user content by definition (a name, an address, a bullet, a JD line), and no regex
#: can reliably recognise a person's name, so the rule is structural rather than pattern-based.
#: This is why our own event names are dotted tokens ("session.created"), not sentences.
MAX_VALUE_TOKENS = 4


def _redact_value(value: Any, depth: int = 0) -> Any:
    if depth > 4:
        return REDACTED
    if isinstance(value, str):
        scrubbed = _PHONE_RE.sub(REDACTED, _EMAIL_RE.sub(REDACTED, value))
        if len(scrubbed) > MAX_VALUE_LENGTH or len(scrubbed.split()) > MAX_VALUE_TOKENS:
            return f"{REDACTED} (len={len(scrubbed)})"
        return scrubbed
    if isinstance(value, dict):
        return {k: _redact_entry(k, v, depth + 1) for k, v in value.items()}
    if isinstance(value, (list, tuple, set)):
        return [_redact_value(item, depth + 1) for item in value][:20]
    return value


def _redact_entry(key: str, value: Any, depth: int = 0) -> Any:
    lowered = key.lower()
    if lowered in SENSITIVE_KEYS:
        return REDACTED
    if depth == 0 and lowered in STRUCTURAL_KEYS:
        return value
    return _redact_value(value, depth)


def redact_processor(
    _logger: object, _method: str, event_dict: structlog.types.EventDict
) -> structlog.types.EventDict:
    """Redact sensitive keys and identifier-shaped values in every emitted record."""
    return {key: _redact_entry(key, value) for key, value in event_dict.items()}


def context_processor(
    _logger: object, _method: str, event_dict: structlog.types.EventDict
) -> structlog.types.EventDict:
    """Attach correlation ids. Session ids are truncated - never logged in full."""
    request_id = request_id_var.get()
    if request_id:
        event_dict.setdefault("request_id", request_id)
    session_id = session_id_var.get()
    if session_id:
        event_dict.setdefault("session", session_id[:8])
    return event_dict


class _StdoutProxy:
    """Write-through proxy that resolves ``sys.stdout`` at write time.

    Binding the stream at configuration time captures whatever ``sys.stdout`` happened to be
    then, which breaks any later reconfiguration and leaves handlers writing to a stream that
    may already be closed. Resolving per write costs nothing and always follows the process's
    current stdout.
    """

    def write(self, message: str) -> int:
        return sys.stdout.write(message)

    def flush(self) -> None:
        sys.stdout.flush()


def configure_logging(*, level: str = "INFO", fmt: str = "console") -> None:
    """Configure structlog and route the stdlib logging tree through the same processors."""
    shared_processors: list[structlog.types.Processor] = [
        structlog.contextvars.merge_contextvars,
        structlog.processors.add_log_level,
        structlog.processors.TimeStamper(fmt="iso", utc=True),
        context_processor,
        redact_processor,
    ]

    renderer: structlog.types.Processor = (
        structlog.processors.JSONRenderer()
        if fmt == "json"
        else structlog.dev.ConsoleRenderer(colors=False)
    )

    structlog.configure(
        processors=[*shared_processors, renderer],
        wrapper_class=structlog.make_filtering_bound_logger(
            logging.getLevelNamesMapping()[level]
        ),
        logger_factory=structlog.PrintLoggerFactory(file=_StdoutProxy()),  # type: ignore[arg-type]
        # Caching would freeze the first configuration for the life of the process.
        cache_logger_on_first_use=False,
    )

    # Uvicorn and library loggers emit through stdlib; give them the same redaction path.
    handler = logging.StreamHandler(_StdoutProxy())
    handler.setFormatter(
        structlog.stdlib.ProcessorFormatter(
            foreign_pre_chain=shared_processors,
            processors=[structlog.stdlib.ProcessorFormatter.remove_processors_meta, renderer],
        )
    )
    root = logging.getLogger()
    root.handlers = [handler]
    root.setLevel(level)
    for noisy in ("uvicorn.access", "uvicorn.error"):
        logging.getLogger(noisy).propagate = True
        logging.getLogger(noisy).handlers = []


def get_logger(name: str | None = None) -> structlog.stdlib.BoundLogger:
    return structlog.get_logger(name)  # type: ignore[no-any-return]
