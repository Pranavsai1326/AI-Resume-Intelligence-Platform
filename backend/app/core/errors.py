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
