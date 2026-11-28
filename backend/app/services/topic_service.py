"""Read and replace the topics of one document of the teacher.

Change `frequent-questions-and-topics`.

The service never commits: the endpoint owns the transaction. Another teacher's document, a
document of another subject and an unknown document are the same `404`. Titles are never logged.
"""

import logging
import uuid

from app.core.errors import NotFoundError, TopicConflictError, TopicDefinitionError
from app.models.document import Document, DocumentStatus
from app.repositories.topic_repository import DocumentGone, SetAlreadyCreated, TopicRepository
from app.schemas.topic import (
    DocumentTopicsResponse,
    DocumentTopicsUpdate,
    TopicView,
    UnavailableReason,
)
from app.services.activity_service import first_week_after
from app.services.document_service import DOCUMENT_NOT_FOUND_MESSAGE
from app.services.topic_rules import InvalidDefinition, StaleRevision, Topic, plan_change

logger = logging.getLogger(__name__)


class DocumentTopicService:
    def __init__(self, topics: TopicRepository) -> None:
        self._topics = topics

    def get(
        self, teacher_id: uuid.UUID, subject_id: uuid.UUID, document_id: uuid.UUID
    ) -> DocumentTopicsResponse:
        document = self._document(teacher_id, subject_id, document_id)
        return self._view(teacher_id, document)

    def save_topics(
        self,
        teacher_id: uuid.UUID,
        subject_id: uuid.UUID,
        document_id: uuid.UUID,
        request: DocumentTopicsUpdate,
    ) -> DocumentTopicsResponse:
        scope = {"teacher_id": teacher_id, "subject_id": subject_id, "document_id": document_id}
        document = self._document(teacher_id, subject_id, document_id)
        if document.status != DocumentStatus.READY:
            raise TopicConflictError("not_ready")
        last_page = self._topics.last_page(**scope)
        if last_page is None:
            # The document may have been deleted since it was found: then it is not found.
            self._document(teacher_id, subject_id, document_id)
            raise TopicConflictError("no_pages")
        stored = self._topics.stored(
            teacher_id=teacher_id, subject_id=subject_id, document_id=document_id, lock=True
        )
        requested = [Topic(e.title, e.start_page, e.end_page) for e in request.topics]
        try:
            plan = plan_change(
                stored[1] if stored else None, request.revision, requested, last_page
            )
        except StaleRevision:
            if stored is None:  # the set may be gone with its document: say so
                self._document(teacher_id, subject_id, document_id)
            raise TopicConflictError("stale") from None
        except InvalidDefinition as error:
            raise TopicDefinitionError(error.reason) from None
        if plan is not None:
            try:
                if plan.creates:
                    self._topics.create_topic_set(
                        document_id=document_id, subject_id=subject_id, plan=plan
                    )
                else:
                    self._topics.replace_topic_set(document_id=document_id, plan=plan)
            except SetAlreadyCreated:
                raise TopicConflictError("stale") from None
            except DocumentGone:
                raise NotFoundError(DOCUMENT_NOT_FOUND_MESSAGE) from None
            logger.info(
                "document topics replaced document=%s revision=%d count=%d ranges_changed=%s",
                document_id,
                plan.revision,
                len(plan.topics),
                plan.moves_marker,
            )
        return self._view(teacher_id, document)

    def _document(
        self, teacher_id: uuid.UUID, subject_id: uuid.UUID, document_id: uuid.UUID
    ) -> Document:
        document = self._topics.document(
            teacher_id=teacher_id, subject_id=subject_id, document_id=document_id
        )
        if document is None:
            raise NotFoundError(DOCUMENT_NOT_FOUND_MESSAGE)
        return document

    def _view(self, teacher_id: uuid.UUID, document: Document) -> DocumentTopicsResponse:
        scope = {
            "teacher_id": teacher_id,
            "subject_id": document.subject_id,
            "document_id": document.id,
        }
        ready = document.status == DocumentStatus.READY
        last_page = self._topics.last_page(**scope) if ready else None
        reason: UnavailableReason | None = None
        if not ready:
            reason = "not_ready"
        elif last_page is None:
            reason = "no_pages"
        stored = self._topics.stored(
            teacher_id=teacher_id, subject_id=document.subject_id, document_id=document.id
        )
        record, current = stored if stored else (None, None)
        marker = record.ranges_changed_at if record else None
        return DocumentTopicsResponse(
            document_id=document.id,
            filename=document.filename,
            editable=reason is None,
            reason=reason,
            last_page=last_page,
            revision=current.revision if current else 0,
            source=current.source if current else None,
            counting_from=first_week_after(marker) if marker else None,
            topics=[
                TopicView(title=t.title, start_page=t.start_page, end_page=t.end_page)
                for t in (current.topics if current else ())
            ],
        )
