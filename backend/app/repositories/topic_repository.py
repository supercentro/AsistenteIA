"""Data access for the topics of documents (change `frequent-questions-and-topics`).

Every method of the API side takes the teacher and the subject and joins `subjects.teacher_id`
(`docs/base-standards.md` section 9.4). Nothing here commits.
"""

import uuid
from collections import defaultdict
from collections.abc import Sequence
from dataclasses import dataclass
from datetime import datetime

from sqlalchemy import delete, func, insert, select, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.models.document import Document, DocumentChunk, DocumentStatus
from app.models.subject import Subject
from app.models.topic import DocumentTopic, DocumentTopicSet, TopicSource
from app.services.topic_rules import CurrentSet, Plan, Topic

_FOREIGN_KEY_VIOLATION = "23503"


class SetAlreadyCreated(Exception):
    """Another transaction created the set first."""


class DocumentGone(Exception):
    """The document was deleted before the set could be stored."""


@dataclass(frozen=True)
class StoredTopic:
    id: uuid.UUID
    title: str
    start_page: int
    end_page: int


@dataclass(frozen=True)
class MaterialFact:
    """A ready document of a subject with what the ranking needs about its topics."""

    document_id: uuid.UUID
    filename: str
    has_pages: bool
    source: TopicSource | None
    ranges_changed_at: datetime | None
    topics: tuple[StoredTopic, ...]


class TopicRepository:
    def __init__(self, session: Session) -> None:
        self._session = session

    def document(
        self, *, teacher_id: uuid.UUID, subject_id: uuid.UUID, document_id: uuid.UUID
    ) -> Document | None:
        statement = (
            select(Document)
            .join(Subject, Subject.id == Document.subject_id)
            .where(
                Document.id == document_id,
                Document.subject_id == subject_id,
                Subject.teacher_id == teacher_id,
            )
        )
        return self._session.execute(statement).scalar_one_or_none()

    def last_page(
        self, *, teacher_id: uuid.UUID, subject_id: uuid.UUID, document_id: uuid.UUID
    ) -> int | None:
        """The highest page with text of the document, `None` when it has no page numbers."""
        statement = (
            select(func.max(DocumentChunk.page_number))
            .join(Subject, Subject.id == DocumentChunk.subject_id)
            .where(
                DocumentChunk.document_id == document_id,
                DocumentChunk.subject_id == subject_id,
                Subject.teacher_id == teacher_id,
            )
        )
        return self._session.execute(statement).scalar_one()

    def stored(
        self,
        *,
        teacher_id: uuid.UUID,
        subject_id: uuid.UUID,
        document_id: uuid.UUID,
        lock: bool = False,
    ) -> tuple[DocumentTopicSet, CurrentSet] | None:
        """The set of the document and its topics; `lock` holds the set until the commit."""
        statement = (
            select(DocumentTopicSet)
            .join(Subject, Subject.id == DocumentTopicSet.subject_id)
            .where(
                DocumentTopicSet.document_id == document_id,
                DocumentTopicSet.subject_id == subject_id,
                Subject.teacher_id == teacher_id,
            )
        )
        if lock:
            statement = statement.with_for_update(of=DocumentTopicSet)
        found = self._session.execute(
            statement.execution_options(populate_existing=True)
        ).scalar_one_or_none()
        if found is None:
            return None
        # Read after the lock: a write that waited for another sees what that one stored.
        rows = self._session.execute(
            select(DocumentTopic.title, DocumentTopic.start_page, DocumentTopic.end_page)
            .where(DocumentTopic.document_id == document_id)
            .order_by(DocumentTopic.position)
        )
        topics = tuple(Topic(title=row[0], start_page=row[1], end_page=row[2]) for row in rows)
        return found, CurrentSet(TopicSource(found.source), found.revision, topics)

    def material(self, *, teacher_id: uuid.UUID, subject_id: uuid.UUID) -> list[MaterialFact]:
        """The ready documents of the subject, by name, each with its topics."""
        owned = (Subject.id == subject_id, Subject.teacher_id == teacher_id)
        documents = self._session.execute(
            select(
                Document.id,
                Document.filename,
                DocumentTopicSet.source,
                DocumentTopicSet.ranges_changed_at,
            )
            .join(Subject, Subject.id == Document.subject_id)
            .outerjoin(DocumentTopicSet, DocumentTopicSet.document_id == Document.id)
            .where(*owned, Document.status == DocumentStatus.READY)
            .order_by(Document.filename, Document.id)
        ).all()
        paged = set(
            self._session.execute(
                select(DocumentChunk.document_id)
                .join(Subject, Subject.id == DocumentChunk.subject_id)
                .where(*owned, DocumentChunk.page_number.is_not(None))
                .distinct()
            ).scalars()
        )
        topics: dict[uuid.UUID, list[StoredTopic]] = defaultdict(list)
        rows = self._session.execute(
            select(
                DocumentTopic.document_id,
                DocumentTopic.id,
                DocumentTopic.title,
                DocumentTopic.start_page,
                DocumentTopic.end_page,
            )
            .join(DocumentTopicSet, DocumentTopicSet.document_id == DocumentTopic.document_id)
            .join(Subject, Subject.id == DocumentTopicSet.subject_id)
            .where(*owned)
            .order_by(DocumentTopic.document_id, DocumentTopic.position)
        )
        for document_id, topic_id, title, start_page, end_page in rows:
            topics[document_id].append(StoredTopic(topic_id, title, start_page, end_page))
        return [
            MaterialFact(
                document_id=document_id,
                filename=filename,
                has_pages=document_id in paged,
                source=TopicSource(source) if source else None,
                ranges_changed_at=changed,
                topics=tuple(topics.get(document_id, ())),
            )
            for document_id, filename, source, changed in documents
        ]

    def create_topic_set(
        self, *, document_id: uuid.UUID, subject_id: uuid.UUID, plan: Plan
    ) -> None:
        try:
            self._session.execute(
                insert(DocumentTopicSet).values(
                    document_id=document_id,
                    subject_id=subject_id,
                    source=plan.source.value,
                    revision=plan.revision,
                )
            )
        except IntegrityError as error:
            if getattr(error.orig, "sqlstate", None) == _FOREIGN_KEY_VIOLATION:
                raise DocumentGone from None
            raise SetAlreadyCreated from None
        self._insert_topics(document_id, plan.topics)

    def replace_topic_set(self, *, document_id: uuid.UUID, plan: Plan) -> None:
        """Replace the topics of a locked set; the marker, once set, never moves back."""
        marker = (
            func.greatest(DocumentTopicSet.ranges_changed_at, func.clock_timestamp())
            if plan.moves_marker
            else DocumentTopicSet.ranges_changed_at
        )
        self._session.execute(
            update(DocumentTopicSet)
            .where(DocumentTopicSet.document_id == document_id)
            .values(source=plan.source.value, revision=plan.revision, ranges_changed_at=marker)
            .execution_options(synchronize_session=False)
        )
        self._session.execute(
            delete(DocumentTopic)
            .where(DocumentTopic.document_id == document_id)
            .execution_options(synchronize_session=False)
        )
        self._insert_topics(document_id, plan.topics)

    def _insert_topics(self, document_id: uuid.UUID, topics: Sequence[Topic]) -> None:
        if not topics:
            return
        rows = [
            {
                "document_id": document_id,
                "position": position,
                "title": topic.title,
                "start_page": topic.start_page,
                "end_page": topic.end_page,
            }
            for position, topic in enumerate(topics)
        ]
        self._session.execute(insert(DocumentTopic), rows)
