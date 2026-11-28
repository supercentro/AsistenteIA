"""Topics of the PDF material of a subject, for its owning teacher.

Change `frequent-questions-and-topics`. Switched off unless `TEACHER_ACTIVITY_ENABLED` and
`TEACHER_TOPICS_ENABLED` are both on. A student and an anonymous caller are refused before the
settings are looked at. A malformed identifier is the same `404` as an unknown one.
"""

from typing import Annotated, Any

from fastapi import APIRouter, Depends

from app.api.deps import (
    DbSession,
    get_document_topic_service,
    get_topic_ranking_service,
    require_teacher_topics,
)
from app.api.document_deps import DocumentId, SubjectId
from app.api.transaction import commit_or_rollback
from app.models.user import User
from app.schemas.error import ErrorResponse
from app.schemas.topic import (
    DocumentTopicsResponse,
    DocumentTopicsUpdate,
    TopicRankingResponse,
)
from app.services.topic_ranking_service import TopicRankingService
from app.services.topic_service import DocumentTopicService

router = APIRouter(prefix="/subjects/{subject_id}", tags=["Topics"])

Teacher = Annotated[User, Depends(require_teacher_topics)]
Service = Annotated[DocumentTopicService, Depends(get_document_topic_service)]


def _error(description: str) -> dict[str, Any]:
    return {"model": ErrorResponse, "description": description}


def _path_parameter(name: str) -> dict[str, Any]:
    return {
        "name": name,
        "in": "path",
        "required": True,
        "schema": {"type": "string", "format": "uuid"},
    }


Ranking = Annotated[TopicRankingService, Depends(get_topic_ranking_service)]

_DOCUMENT_PARAMETERS = {
    "parameters": [_path_parameter("subject_id"), _path_parameter("document_id")]
}
_ERRORS: dict[int | str, dict[str, Any]] = {
    401: _error("Missing or invalid token"),
    403: _error("Authenticated but not a teacher"),
    404: _error("The subject or the document does not exist or is not yours, or topics are off"),
    500: _error("Unexpected error"),
    503: _error("Database unavailable"),
}
_WRITE_ERRORS: dict[int | str, dict[str, Any]] = {
    **_ERRORS,
    409: _error("details.reason: stale, not_ready or no_pages"),
    422: _error("Invalid body, or details.reason: overlap or page_range"),
}


@router.get(
    "/activity/topics",
    response_model=TopicRankingResponse,
    responses=_ERRORS,
    summary="Most cited topics of a subject (owner teacher)",
    openapi_extra={"parameters": [_path_parameter("subject_id")]},
)
def get_topic_ranking(
    teacher: Teacher, subject_id: SubjectId, service: Ranking
) -> TopicRankingResponse:
    return service.get(teacher.id, subject_id)


@router.get(
    "/documents/{document_id}/topics",
    response_model=DocumentTopicsResponse,
    responses=_ERRORS,
    summary="Topics of one document (owner teacher)",
    openapi_extra=_DOCUMENT_PARAMETERS,
)
def get_document_topics(
    teacher: Teacher, subject_id: SubjectId, document_id: DocumentId, service: Service
) -> DocumentTopicsResponse:
    return service.get(teacher.id, subject_id, document_id)


@router.put(
    "/documents/{document_id}/topics",
    response_model=DocumentTopicsResponse,
    responses=_WRITE_ERRORS,
    summary="Replace the topics of one document (owner teacher)",
    openapi_extra=_DOCUMENT_PARAMETERS,
)
def replace_document_topics(
    teacher: Teacher,
    subject_id: SubjectId,
    document_id: DocumentId,
    body: DocumentTopicsUpdate,
    service: Service,
    db: DbSession,
) -> DocumentTopicsResponse:
    response = service.save_topics(teacher.id, subject_id, document_id, body)
    commit_or_rollback(db)  # stored before the answer is built (TD-039)
    return response
