"""Exception handlers producing the common `Error` body without leaking internals."""

import logging
from typing import cast

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from sqlalchemy.exc import InterfaceError, OperationalError
from starlette.exceptions import HTTPException as StarletteHTTPException

from app.core.errors import AppError
from app.schemas.error import ErrorResponse

logger = logging.getLogger(__name__)

_HTTP_CODES = {
    401: "UNAUTHORIZED",
    403: "FORBIDDEN",
    404: "NOT_FOUND",
    405: "METHOD_NOT_ALLOWED",
    409: "CONFLICT",
    422: "VALIDATION_ERROR",
}


def _error_response(
    status_code: int,
    code: str,
    message: str,
    details: dict[str, object] | None = None,
    headers: dict[str, str] | None = None,
) -> JSONResponse:
    body = ErrorResponse(code=code, message=message, details=details)
    return JSONResponse(
        status_code=status_code, content=body.model_dump(exclude_none=True), headers=headers
    )


async def _app_error_handler(_: Request, error: Exception) -> JSONResponse:
    exc = cast(AppError, error)
    return _error_response(exc.status_code, exc.code, exc.message, exc.details, exc.headers)


async def _http_exception_handler(_: Request, error: Exception) -> JSONResponse:
    exc = cast(StarletteHTTPException, error)
    code = _HTTP_CODES.get(exc.status_code, "HTTP_ERROR")
    message = "Resource not found" if exc.status_code == 404 else "Request could not be processed"
    return _error_response(exc.status_code, code, message)


async def _validation_error_handler(_: Request, error: Exception) -> JSONResponse:
    exc = cast(RequestValidationError, error)
    # Only field locations and messages: submitted values are never echoed back.
    errors = [
        {"field": ".".join(str(part) for part in err["loc"]), "message": str(err["msg"])}
        for err in exc.errors()
    ]
    return _error_response(422, "VALIDATION_ERROR", "Request validation failed", {"errors": errors})


async def _database_unavailable_handler(request: Request, exc: Exception) -> JSONResponse:
    # Type, method and path only: the exception text can contain hosts, SQL or row data.
    logger.error(
        "database unavailable type=%s method=%s path=%s",
        type(exc).__name__,
        request.method,
        request.url.path,
    )
    return _error_response(503, "SERVICE_UNAVAILABLE", "Service unavailable")


def register_exception_handlers(app: FastAPI) -> None:
    app.add_exception_handler(AppError, _app_error_handler)
    app.add_exception_handler(StarletteHTTPException, _http_exception_handler)
    app.add_exception_handler(RequestValidationError, _validation_error_handler)
    app.add_exception_handler(OperationalError, _database_unavailable_handler)
    app.add_exception_handler(InterfaceError, _database_unavailable_handler)
