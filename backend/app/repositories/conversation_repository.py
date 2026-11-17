"""Data access for conversations. Every query is scoped by student_id."""

import uuid

from sqlalchemy import delete, func, select
from sqlalchemy.orm import Session

from app.models.conversation import Conversation
from app.models.subject import Enrollment


class ConversationRepository:
    def __init__(self, session: Session) -> None:
        self._session = session

    def create(self, *, student_id: uuid.UUID, subject_id: uuid.UUID) -> Conversation:
        conv = Conversation(student_id=student_id, subject_id=subject_id)
        self._session.add(conv)
        self._session.flush()
        return conv

    def get_by_id_and_student(
        self,
        conversation_id: uuid.UUID,
        student_id: uuid.UUID,
        *,
        subject_id: uuid.UUID | None = None,
    ) -> Conversation | None:
        statement = select(Conversation).where(
            Conversation.id == conversation_id,
            Conversation.student_id == student_id,
        )
        if subject_id is not None:
            statement = statement.where(Conversation.subject_id == subject_id)
        return self._session.execute(statement).scalars().first()

    def get_visible_to_student(
        self, conversation_id: uuid.UUID, student_id: uuid.UUID
    ) -> Conversation | None:
        """The student's own conversation, only while still enrolled in its subject."""
        statement = (
            select(Conversation)
            .join(
                Enrollment,
                (Enrollment.student_id == Conversation.student_id)
                & (Enrollment.subject_id == Conversation.subject_id),
            )
            .where(Conversation.id == conversation_id, Conversation.student_id == student_id)
        )
        return self._session.execute(statement).scalars().first()

    def list_by_student(
        self,
        student_id: uuid.UUID,
        *,
        subject_id: uuid.UUID | None = None,
    ) -> list[Conversation]:
        statement = (
            select(Conversation)
            .join(
                Enrollment,
                (Enrollment.student_id == Conversation.student_id)
                & (Enrollment.subject_id == Conversation.subject_id),
            )
            .where(Conversation.student_id == student_id)
        )
        if subject_id is not None:
            statement = statement.where(Conversation.subject_id == subject_id)
        statement = statement.order_by(Conversation.created_at.desc())
        return list(self._session.execute(statement).scalars())

    def delete_by_id_and_student(self, conversation_id: uuid.UUID, student_id: uuid.UUID) -> bool:
        statement = (
            delete(Conversation)
            .where(
                Conversation.id == conversation_id,
                Conversation.student_id == student_id,
            )
            .returning(Conversation.id)
        )
        return self._session.execute(statement).first() is not None

    def delete_all_by_student(self, student_id: uuid.UUID) -> int:
        count_stmt = select(func.count()).where(Conversation.student_id == student_id)
        count: int = self._session.execute(count_stmt).scalar_one()
        if count:
            self._session.execute(delete(Conversation).where(Conversation.student_id == student_id))
        return count
