"""Upload, list and delete the course material of a subject (change 6, task 9.1).

Only the owning teacher may use these routes. The upload follows design A8:

1. `authorize_upload` decides 401, 403, 404, 429 and the early 503 in a short session that is
   closed before the body is read;
2. an upload slot is taken (`503` when `UPLOAD_MAX_IN_FLIGHT` uploads are being received);
3. the form is read here, not declared with `File`, with the guard of `app.core.upload_guard`
   enforcing the size and the deadlines on the bytes actually received; every parser failure is a
   controlled answer with a fixed reason;
4. the file name and type are checked, then the document, its job and the bytes are stored in one
   transaction that is **committed here, before the `202` is built** (design D2): `get_db` would
   commit after the handler returns, which can fail after a `202` was sent.
"""

import logging
from typing import Annotated, Any

from fastapi import APIRouter, Depends, Request, Response, status
from fastapi.concurrency import run_in_threadpool
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session, sessionmaker
from starlette.datastructures import UploadFile
from starlette.exceptions import HTTPException as StarletteHTTPException
from starlette.requests import ClientDisconnect

from app.api.deps import DbSession, require_teacher
from app.api.document_deps import (
    DocumentId,
    SubjectId,
    UploadActor,
    authorize_upload,
    get_document_service,
)
from app.core.config import Settings
from app.core.errors import (
    AppError,
    IngestionQueueFullError,
    PayloadTooLargeError,
    RequestTimeoutError,
    ServiceUnavailableError,
)
from app.core.upload_guard import UploadSlots, UploadTimedOut, UploadTooLarge
from app.models.user import User
from app.repositories.document_repository import (
    QUEUE_RETRY_AFTER_SECONDS,
    AdmissionLimits,
    DocumentRepository,
)
from app.schemas.document import Document
from app.schemas.error import ErrorResponse
from app.services.document_service import DocumentService
from app.services.upload_inspection import UploadRejection, inspect_upload, rejection

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/subjects/{subject_id}/documents", tags=["Documents"])

_BYTES_PER_MB = 1024 * 1024
# One file and nothing else is expected: a few extra parts are answered as unexpected fields, an
# abusive number of them as a malformed request (the parser stops at these limits).
_MAX_PARTS = 5
_MAX_FIELD_BYTES = 64 * 1024
_FILE_FIELD = "file"

Teacher = Annotated[User, Depends(require_teacher)]
Service = Annotated[DocumentService, Depends(get_document_service)]


class ClientGoneError(AppError):
    """The client closed the connection while sending the body: nothing is stored.

    The response of this error is never delivered; raising it ends the request quietly instead of
    letting the transport log a disconnect as an unhandled exception.
    """

    status_code = 400
    code = "CLIENT_DISCONNECTED"


def _error(description: str) -> dict[str, Any]:
    return {"model": ErrorResponse, "description": description}


_SUBJECT_PARAMETER = {
    "name": "subject_id",
    "in": "path",
    "required": True,
    "schema": {"type": "string", "format": "uuid"},
}
_DOCUMENT_PARAMETER = {
    "name": "document_id",
    "in": "path",
    "required": True,
    "schema": {"type": "string", "format": "uuid"},
}
_UPLOAD_BODY = {
    "required": True,
    "content": {
        "multipart/form-data": {
            "schema": {
                "type": "object",
                "required": [_FILE_FIELD],
                "additionalProperties": False,
                "properties": {_FILE_FIELD: {"type": "string", "format": "binary"}},
            }
        }
    },
}
_ACCESS_ERRORS: dict[int | str, dict[str, Any]] = {
    401: _error("Missing or invalid token"),
    403: _error("Authenticated but not a teacher"),
    404: _error("The subject or the document does not exist or is not yours"),
}


def _is_multipart(request: Request) -> bool:
    media_type = request.headers.get("content-type", "").split(";", 1)[0].strip().lower()
    return media_type == "multipart/form-data"


async def _read_file(request: Request, max_bytes: int) -> tuple[str | None, bytes]:
    """The single `file` part of the request: its client name and its bytes."""
    try:
        form = await request.form(
            max_files=_MAX_PARTS, max_fields=_MAX_PARTS, max_part_size=_MAX_FIELD_BYTES
        )
    except UploadTooLarge:
        raise PayloadTooLargeError from None
    except UploadTimedOut:
        raise RequestTimeoutError from None
    except ClientDisconnect:
        logger.info("upload abandoned by the client")
        raise ClientGoneError("The client closed the connection") from None
    except StarletteHTTPException:  # the parser's default 400, never exposed
        raise rejection(UploadRejection.MALFORMED_MULTIPART) from None
    try:
        items = form.multi_items()
        files = [
            value for key, value in items if key == _FILE_FIELD and isinstance(value, UploadFile)
        ]
        if not files:
            raise rejection(UploadRejection.FILE_PART_MISSING)
        if len(items) != 1:
            raise rejection(UploadRejection.UNEXPECTED_FIELDS)
        upload = files[0]
        content = await upload.read()
        if len(content) > max_bytes:
            raise PayloadTooLargeError
        return upload.filename, content
    finally:
        await form.close()


def _store(
    factory: sessionmaker[Session],
    settings: Settings,
    actor: UploadActor,
    raw_filename: str | None,
    content: bytes,
) -> Document:
    """Validate, store and **commit**; the returned schema is built after the commit."""
    inspected = inspect_upload(raw_filename, content)
    try:
        with factory() as session:
            service = DocumentService(
                DocumentRepository(session), AdmissionLimits.from_settings(settings)
            )
            try:
                record = service.upload(actor.teacher_id, actor.subject_id, inspected, content)
                session.commit()
            except BaseException:
                session.rollback()
                raise
    except SQLAlchemyError as error:
        logger.error("upload could not be stored type=%s", type(error).__name__)
        raise ServiceUnavailableError("The upload could not be stored right now") from None
    return Document.model_validate(record)


@router.post(
    "",
    response_model=Document,
    status_code=status.HTTP_202_ACCEPTED,
    summary="Upload course material (owner teacher)",
    responses={
        **_ACCESS_ERRORS,
        408: _error("A connected client did not send the body in time"),
        409: _error("The subject already holds the maximum number of documents"),
        413: _error("File too large"),
        415: _error("Unsupported file type or content that does not match the type"),
        422: _error("Invalid multipart request; details.reason names the case"),
        429: _error("Upload rate limit exceeded"),
        503: _error("The ingestion queue is full, or the upload could not be stored"),
    },
    openapi_extra={"requestBody": _UPLOAD_BODY, "parameters": [_SUBJECT_PARAMETER]},
)
async def upload_document(
    request: Request, actor: Annotated[UploadActor, Depends(authorize_upload)]
) -> Document:
    settings: Settings = request.app.state.settings
    if not _is_multipart(request):
        raise rejection(UploadRejection.MALFORMED_MULTIPART)
    slots: UploadSlots = request.app.state.upload_slots
    if not slots.try_acquire():
        raise IngestionQueueFullError(QUEUE_RETRY_AFTER_SECONDS)
    try:
        raw_filename, content = await _read_file(request, settings.max_upload_mb * _BYTES_PER_MB)
        return await run_in_threadpool(
            _store, request.app.state.session_factory, settings, actor, raw_filename, content
        )
    finally:
        slots.release()


@router.get(
    "",
    response_model=list[Document],
    summary="List documents of a subject with processing status (owner teacher)",
    responses=_ACCESS_ERRORS,
    openapi_extra={"parameters": [_SUBJECT_PARAMETER]},
)
def list_documents(teacher: Teacher, subject_id: SubjectId, service: Service) -> list[Document]:
    records = service.list_documents(teacher.id, subject_id)
    return [Document.model_validate(record) for record in records]


@router.delete(
    "/{document_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Delete a document and its chunks (owner teacher)",
    responses=_ACCESS_ERRORS,
    openapi_extra={"parameters": [_SUBJECT_PARAMETER, _DOCUMENT_PARAMETER]},
)
def delete_document(
    teacher: Teacher,
    subject_id: SubjectId,
    document_id: DocumentId,
    service: Service,
    db: DbSession,
) -> Response:
    service.delete(teacher.id, subject_id, document_id)
    db.commit()  # the deletion is durable before the 204 is built
    return Response(status_code=status.HTTP_204_NO_CONTENT)
