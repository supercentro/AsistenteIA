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


class PayloadTooLargeError(AppError):
    """More bytes were received than `MAX_UPLOAD_MB` allows (change 6)."""

    status_code = 413
    code = "PAYLOAD_TOO_LARGE"

    def __init__(self) -> None:
        super().__init__("The file is larger than the allowed maximum")


class UnsupportedMediaTypeError(AppError):
    """The extension is not allowed or the content does not match it (change 6)."""

    status_code = 415
    code = "UNSUPPORTED_MEDIA_TYPE"

    def __init__(self) -> None:
        super().__init__("Only PDF, plain text and Markdown files are accepted")


class RequestTimeoutError(AppError):
    """A client that stayed connected did not send the body in time (change 6)."""

    status_code = 408
    code = "REQUEST_TIMEOUT"

    def __init__(self) -> None:
        super().__init__("The upload was not received in time")


class UploadValidationError(AppError):
    """The multipart request or the file name is invalid; `details.reason` is a fixed value."""

    status_code = 422
    code = "VALIDATION_ERROR"

    def __init__(self, reason: str, message: str) -> None:
        super().__init__(message, details={"reason": str(reason)})


class InvalidActivityWindowError(AppError):
    """The window of the teacher activity is reversed or longer than the allowed maximum."""

    status_code = 422
    code = "VALIDATION_ERROR"

    def __init__(self, reason: str, message: str) -> None:
        super().__init__(message, details={"reason": str(reason)})


class ConsentRequiredError(ForbiddenError):
    """The student has not accepted the current privacy policy version."""

    code = "CONSENT_REQUIRED"

    def __init__(self) -> None:
        super().__init__("Current privacy-policy consent is required")


class LLMUnavailableError(AppError):
    """The LLM provider is unreachable or throttled."""

    status_code = 502
    code = "LLM_UNAVAILABLE"

    def __init__(self) -> None:
        super().__init__("The language model is temporarily unavailable")


class LLMBlockedError(AppError):
    """The LLM refused to generate because of safety filters."""

    status_code = 502
    code = "LLM_BLOCKED"

    def __init__(self) -> None:
        super().__init__("The response was blocked by safety filters")


class SearchUnavailableError(AppError):
    """The vector search backend failed."""

    status_code = 503
    code = "SEARCH_UNAVAILABLE"

    def __init__(self) -> None:
        super().__init__("The search service is temporarily unavailable")
