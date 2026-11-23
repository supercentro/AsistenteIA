"""Aggregate reads of the activity of a subject, for its owning teacher.

Every query takes the teacher and the subject and joins `subjects.teacher_id`, and counts only the
conversations of students enrolled in the subject (`docs/base-standards.md` section 9.4). The
repository returns facts, never rows to show: the service reduces them to numbers. Nothing is
written. The text of an answer is read only so that the service can derive whether it cited its
sources, and it never leaves the service.
"""

import uuid
from collections import defaultdict
from dataclasses import dataclass
from datetime import datetime
from typing import Any, TypeVar

from sqlalchemy import Select, func, select
from sqlalchemy.orm import Session

from app.models.conversation import Conversation, Message, MessageRole, MessageSource
from app.models.document import Document, DocumentChunk, DocumentStatus
from app.models.subject import Enrollment, Subject

SelectT = TypeVar("SelectT", bound=Select[*tuple[Any, ...]])


@dataclass(frozen=True)
class QuestionFact:
    student_id: uuid.UUID
    asked_at: datetime


@dataclass(frozen=True)
class SourceFact:
    rank: int
    document_id: uuid.UUID | None  # null once the document was deleted
    filename: str


@dataclass(frozen=True)
class AnswerFact:
    student_id: uuid.UUID
    answered_at: datetime
    content: str
    sources: tuple[SourceFact, ...]


class ActivityRepository:
    def __init__(self, session: Session) -> None:
        self._session = session

    def enrolled_count(self, *, teacher_id: uuid.UUID, subject_id: uuid.UUID) -> int:
        statement = (
            select(func.count(Enrollment.id))
            .join(Subject, Subject.id == Enrollment.subject_id)
            .where(Subject.id == subject_id, Subject.teacher_id == teacher_id)
        )
        return int(self._session.execute(statement).scalar_one())

    def questions(
        self, *, teacher_id: uuid.UUID, subject_id: uuid.UUID, start: datetime, end: datetime
    ) -> list[QuestionFact]:
        """Questions asked in `[start, end)` by students currently enrolled in the subject."""
        statement = self._scoped(
            select(Conversation.student_id, Message.created_at).select_from(Message),
            teacher_id,
            subject_id,
            start,
            end,
            MessageRole.USER,
        )
        return [
            QuestionFact(student_id=row[0], asked_at=row[1])
            for row in self._session.execute(statement)
        ]

    def answers(
        self, *, teacher_id: uuid.UUID, subject_id: uuid.UUID, start: datetime, end: datetime
    ) -> list[AnswerFact]:
        """Answers in `[start, end)` with the sources stored for each, same scope as questions."""
        heads = self._scoped(
            select(
                Message.id, Conversation.student_id, Message.created_at, Message.content
            ).select_from(Message),
            teacher_id,
            subject_id,
            start,
            end,
            MessageRole.ASSISTANT,
        )
        source_rows = self._scoped(
            select(
                MessageSource.message_id,
                MessageSource.rank,
                DocumentChunk.document_id,
                MessageSource.document_filename,
            )
            .select_from(Message)
            .join(MessageSource, MessageSource.message_id == Message.id)
            .outerjoin(DocumentChunk, DocumentChunk.id == MessageSource.chunk_id),
            teacher_id,
            subject_id,
            start,
            end,
            MessageRole.ASSISTANT,
        )
        sources: dict[uuid.UUID, list[SourceFact]] = defaultdict(list)
        for message_id, rank, document_id, filename in self._session.execute(source_rows):
            sources[message_id].append(
                SourceFact(rank=rank, document_id=document_id, filename=filename)
            )
        return [
            AnswerFact(
                student_id=student_id,
                answered_at=answered_at,
                content=content,
                sources=tuple(sources.get(message_id, ())),
            )
            for message_id, student_id, answered_at, content in self._session.execute(heads)
        ]

    def current_documents(
        self, *, teacher_id: uuid.UUID, subject_id: uuid.UUID
    ) -> list[tuple[uuid.UUID, str]]:
        """Ready documents of the subject: the ones that can be cited."""
        statement = (
            select(Document.id, Document.filename)
            .join(Subject, Subject.id == Document.subject_id)
            .where(
                Subject.id == subject_id,
                Subject.teacher_id == teacher_id,
                Document.status == DocumentStatus.READY,
            )
            .order_by(Document.filename)
        )
        return [(row[0], row[1]) for row in self._session.execute(statement)]

    @staticmethod
    def _scoped(
        statement: SelectT,
        teacher_id: uuid.UUID,
        subject_id: uuid.UUID,
        start: datetime,
        end: datetime,
        role: MessageRole,
    ) -> SelectT:
        """Messages of one role in the window, of the teacher's subject, enrolled students only."""
        return (
            statement.join(Conversation, Conversation.id == Message.conversation_id)
            .join(Subject, Subject.id == Conversation.subject_id)
            .join(
                Enrollment,
                (Enrollment.subject_id == Conversation.subject_id)
                & (Enrollment.student_id == Conversation.student_id),
            )
            .where(
                Subject.id == subject_id,
                Subject.teacher_id == teacher_id,
                Message.role == role,
                Message.created_at >= start,
                Message.created_at < end,
            )
        )
