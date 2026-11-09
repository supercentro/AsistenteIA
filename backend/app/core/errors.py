"""Domain errors, mapped to HTTP responses by the handlers in `core/handlers.py`."""


class AppError(Exception):
    """Base class of expected, user-facing application errors."""

    status_code = 500
    code = "INTERNAL_ERROR"

    def __init__(
        self,
        message: str,
        details: dict[str, object] | None = None,
        headers: dict[str, str] | None = None,
    ) -> None:
        super().__init__(message)
        self.message = message
        self.details = details
        self.headers = headers


class UnauthorizedError(AppError):
    status_code = 401
    code = "UNAUTHORIZED"


class InvalidCredentialsError(AppError):
    status_code = 401
    code = "INVALID_CREDENTIALS"


class ForbiddenError(AppError):
    status_code = 403
    code = "FORBIDDEN"


class NotFoundError(AppError):
    status_code = 404
    code = "NOT_FOUND"


class ConflictError(AppError):
    status_code = 409
    code = "CONFLICT"


class InvalidConsentVersionError(AppError):
    status_code = 422
    code = "INVALID_CONSENT_VERSION"


class RateLimitedError(AppError):
    status_code = 429
    code = "RATE_LIMITED"

    def __init__(self, message: str, retry_after_seconds: int) -> None:
        super().__init__(message, headers={"Retry-After": str(max(1, retry_after_seconds))})


class ServiceUnavailableError(AppError):
    status_code = 503
    code = "SERVICE_UNAVAILABLE"


class DocumentQuotaExceededError(AppError):
    """The subject already holds the maximum number of documents (change 6)."""

    status_code = 409
    code = "DOCUMENT_QUOTA_EXCEEDED"

    def __init__(self) -> None:
        super().__init__("The subject has reached the maximum number of documents")


class IngestionQueueFullError(AppError):
    """The ingestion queue is full by count or by pending bytes (change 6)."""

    status_code = 503
    code = "INGESTION_QUEUE_FULL"

    def __init__(self, retry_after_seconds: int = 30) -> None:
        super().__init__(
            "The service cannot accept more documents right now",
            headers={"Retry-After": str(max(1, retry_after_seconds))},
        )
