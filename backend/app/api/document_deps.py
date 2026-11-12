"""Dependencies of the document endpoints (change 6, group 9).

The upload authenticates, checks the role and the ownership of the subject, applies the rate limit
and the early queue check in a **short session of its own** that is closed before the body is
read: a slow client never holds a pooled database connection (design A8). The path identifiers
are read from `request.path_params` instead of being declared as typed parameters, so a malformed
id is the same `404` as an unknown one and the framework adds no `422` to these routes.
"""

import uuid
from dataclasses import dataclass
from typing import Annotated

from fastapi import Depends, Request
from fastapi.security import HTTPAuthorizationCredentials
from sqlalchemy.orm import Session, sessionmaker

from app.api.deps import AppSettings, DbSession, _client_key, authenticate, bearer_scheme
from app.core.errors import ForbiddenError, IngestionQueueFullError, NotFoundError
from app.core.rate_limit import RateLimiter
from app.models.user import UserRole
from app.repositories.document_repository import (
    QUEUE_RETRY_AFTER_SECONDS,
    AdmissionLimits,
    DocumentRepository,
)
from app.repositories.user_repository import UserRepository
from app.services.document_service import (
    DOCUMENT_NOT_FOUND_MESSAGE,
    SUBJECT_NOT_FOUND_MESSAGE,
    DocumentService,
)

FORBIDDEN_MESSAGE = "You do not have permission to perform this action"


def _path_uuid(request: Request, name: str, message: str) -> uuid.UUID:
    raw = request.path_params.get(name, "")
    try:
        return uuid.UUID(str(raw))
    except ValueError:
        raise NotFoundError(message) from None


def subject_id_from_path(request: Request) -> uuid.UUID:
    return _path_uuid(request, "subject_id", SUBJECT_NOT_FOUND_MESSAGE)


def document_id_from_path(request: Request) -> uuid.UUID:
    return _path_uuid(request, "document_id", DOCUMENT_NOT_FOUND_MESSAGE)


SubjectId = Annotated[uuid.UUID, Depends(subject_id_from_path)]
DocumentId = Annotated[uuid.UUID, Depends(document_id_from_path)]


def get_document_service(db: DbSession, settings: AppSettings) -> DocumentService:
    return DocumentService(DocumentRepository(db), AdmissionLimits.from_settings(settings))


@dataclass(frozen=True)
class UploadActor:
    """Who may upload to which subject; plain values, so nothing is tied to a closed session."""

    teacher_id: uuid.UUID
    subject_id: uuid.UUID


def authorize_upload(
    request: Request,
    credentials: Annotated[HTTPAuthorizationCredentials | None, Depends(bearer_scheme)],
    settings: AppSettings,
) -> UploadActor:
    """401, 403, 404, 429 and the early 503, decided before the body is read.

    The order is fixed: authentication, role, the subject identifier, ownership (the same `404`
    for unknown and foreign subjects), then the per-address upload rate and a lock-free look at
    the queue. Refused requests before the rate limit do not use up the rate.
    """
    factory: sessionmaker[Session] = request.app.state.session_factory
    with factory() as session:
        user = authenticate(credentials, settings, UserRepository(session))
        if user.role is not UserRole.TEACHER:
            raise ForbiddenError(FORBIDDEN_MESSAGE)
        subject_id = subject_id_from_path(request)
        documents = DocumentRepository(session)
        if not documents.owns_subject(subject_id, user.id):
            raise NotFoundError(SUBJECT_NOT_FOUND_MESSAGE)
        limiter: RateLimiter = request.app.state.upload_rate_limiter
        limiter.check(_client_key(request))
        if documents.unfinished_jobs() >= settings.ingestion_queue_max:
            raise IngestionQueueFullError(QUEUE_RETRY_AFTER_SECONDS)
        return UploadActor(user.id, subject_id)
