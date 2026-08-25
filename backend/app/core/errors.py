"""Sanitised error model.

Every failure reaching a client is expressed through :class:`AppError` and rendered by the
handlers in ``app.core.middleware``. Users receive a stable code, a category, a readable
message and a request id. Stack traces, filesystem paths, library internals and provider
payloads never leave the server.
"""

from __future__ import annotations

from enum import StrEnum
from typing import Any


class ErrorCategory(StrEnum):
    VALIDATION = "validation"
    SESSION = "session"
    RATE_LIMIT = "rate_limit"
    UNAVAILABLE = "unavailable"
    TIMEOUT = "timeout"
    INTERNAL = "internal"


class AppError(Exception):
    """Base class for every error that is safe to show a user."""

    code: str = "INTERNAL_ERROR"
    category: ErrorCategory = ErrorCategory.INTERNAL
    status_code: int = 500
    retryable: bool = False
    message: str = "Something went wrong. Please try again."

    def __init__(
        self,
        message: str | None = None,
        *,
        headers: dict[str, str] | None = None,
        details: dict[str, Any] | None = None,
    ) -> None:
        self.message = message or self.message
        self.headers = headers or {}
        self.details = details or {}
        super().__init__(self.message)

    def to_payload(self, request_id: str | None) -> dict[str, Any]:
        payload: dict[str, Any] = {
            "error": {
                "code": self.code,
                "category": self.category.value,
                "message": self.message,
                "retryable": self.retryable,
                "request_id": request_id,
            }
        }
        if self.details:
            payload["error"]["details"] = self.details
        return payload


class SessionRequiredError(AppError):
    code = "SESSION_REQUIRED"
    category = ErrorCategory.SESSION
    status_code = 400
    message = "This request requires an active session. Start one and try again."


class SessionExpiredError(AppError):
    code = "SESSION_EXPIRED"
    category = ErrorCategory.SESSION
    status_code = 410
    message = (
        "Your temporary session has ended and its data has been removed. "
        "Start a new session to continue."
    )


class ValidationFailedError(AppError):
    code = "VALIDATION_FAILED"
    category = ErrorCategory.VALIDATION
    status_code = 422
    message = "The request could not be processed as sent."


class NotFoundError(AppError):
    code = "NOT_FOUND"
    category = ErrorCategory.VALIDATION
    status_code = 404
    message = "The requested item does not exist in this session."


class RateLimitedError(AppError):
    code = "RATE_LIMITED"
    category = ErrorCategory.RATE_LIMIT
    status_code = 429
    retryable = True
    message = "Too many requests. Please wait a moment and try again."

    def __init__(self, retry_after: int, message: str | None = None) -> None:
        super().__init__(message, headers={"Retry-After": str(retry_after)})
        self.retry_after = retry_after


class ServiceUnavailableError(AppError):
    code = "SERVICE_UNAVAILABLE"
    category = ErrorCategory.UNAVAILABLE
    status_code = 503
    retryable = True
    message = "This capability is temporarily unavailable."


class AIUnavailableError(ServiceUnavailableError):
    """Raised when an AI-backed feature is requested without a configured provider.

    Deliberately explicit: the product shows an honest unavailable state rather than
    fabricating output. See AI_ARCHITECTURE.md section 2.
    """

    code = "AI_UNAVAILABLE"
    retryable = False
    message = "AI features are not configured on this deployment."


class StorageUnavailableError(ServiceUnavailableError):
    code = "STORAGE_UNAVAILABLE"
    message = "The session store is unreachable. Please try again shortly."


# -- Document processing (Phase 2) --------------------------------------------------------------
# Uploaded files are hostile input until proven otherwise (SECURITY.md section 2). Each of these
# maps one validation or extraction failure to a message that names the problem without ever
# reflecting file content, a path, or a library's internal error text back to the client.


class EmptyFileError(ValidationFailedError):
    code = "EMPTY_FILE"
    message = "The uploaded file is empty."


class FileTooLargeError(ValidationFailedError):
    code = "FILE_TOO_LARGE"

    def __init__(self, max_bytes: int) -> None:
        super().__init__(
            f"The file exceeds the {max_bytes // (1024 * 1024)} MB limit.",
            details={"max_bytes": max_bytes},
        )


class UnsupportedFileTypeError(ValidationFailedError):
    code = "UNSUPPORTED_FILE_TYPE"
    message = "Only PDF, DOCX and TXT files are supported."


class TooManyPagesError(ValidationFailedError):
    code = "TOO_MANY_PAGES"

    def __init__(self, max_pages: int) -> None:
        super().__init__(
            f"The document exceeds the {max_pages}-page limit.",
            details={"max_pages": max_pages},
        )


class DocumentStructureError(ValidationFailedError):
    """Structural limits: decompression ratio, entry count, archive nesting.

    Named separately from a generic corrupt-file error because this one is a defence
    (zip-bomb / entity-expansion protection), not a parse failure - see SECURITY.md section 2.
    """

    code = "DOCUMENT_STRUCTURE_REJECTED"
    message = "The document's internal structure could not be safely processed."


class CorruptDocumentError(ValidationFailedError):
    code = "CORRUPT_DOCUMENT"
    message = "The file could not be read. It may be corrupted or not a valid document."


class PasswordProtectedDocumentError(ValidationFailedError):
    code = "PASSWORD_PROTECTED"
    message = "This document is password-protected and cannot be processed."


class NoExtractableTextError(ValidationFailedError):
    """The document has no text layer and OCR is unavailable or disabled.

    Distinguished from :class:`CorruptDocumentError`: the file is valid, it simply contains no
    text this pipeline can read without OCR (e.g. a scanned image saved as PDF).
    """

    code = "NO_EXTRACTABLE_TEXT"
    message = (
        "This file has no extractable text, and OCR is not available on this deployment."
    )


class DocumentProcessingTimeoutError(AppError):
    code = "DOCUMENT_PROCESSING_TIMEOUT"
    category = ErrorCategory.TIMEOUT
    status_code = 504
    retryable = True
    message = "Processing this document took too long and was cancelled."
