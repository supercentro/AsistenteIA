"""Data access for messages and their sources."""

from __future__ import annotations

import uuid
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session, joinedload

from app.models.conversation import Conversation, Message, MessageRole, MessageSource
from app.models.document import DocumentChunk
from app.models.subject import Enrollment


class MessageRepository:
    def __init__(self, session: Session) -> None:
        self._session = session

    def create_with_sources(
        self,
        *,
        conversation_id: uuid.UUID,
        role: str,
        content: str,
        sources: list[dict[str, Any]],
    ) -> Message:
        msg = Message(
            conversation_id=conversation_id,
            role=MessageRole(role),
            content=content,
        )
        self._session.add(msg)
        self._session.flush()

        for src in sources:
            ms = MessageSource(
                message_id=msg.id,
                chunk_id=src.get("chunk_id"),
                document_filename=src["document_filename"],
                page_number=src.get("page_number"),
                rank=src["rank"],
                score=src["score"],
            )
            self._session.add(ms)
        if sources:
            self._session.flush()

        return msg

    def list_by_conversation(
        self, conversation_id: uuid.UUID, student_id: uuid.UUID
    ) -> list[Message]:
        statement = (
            select(Message)
            .join(Message.conversation)
            .where(
                Message.conversation_id == conversation_id,
                Message.conversation.has(student_id=student_id),
            )
            .options(joinedload(Message.sources))
            .order_by(Message.created_at, Message.role)
        )
        return list(self._session.execute(statement).unique().scalars())

    def recent_for_prompt(
        self, conversation_id: uuid.UUID, student_id: uuid.UUID, limit: int
    ) -> list[Message]:
        """The newest ``limit`` messages of the student's own conversation, oldest first.

        Bounded in the database so that the cost does not grow with the conversation. Sources
        are not loaded: the prompt needs only the role and the text. No query runs for 0.
        """
        if limit <= 0:
            return []
        statement = (
            select(Message)
            .join(Message.conversation)
            .where(
                Message.conversation_id == conversation_id,
                Message.conversation.has(student_id=student_id),
            )
            .order_by(Message.created_at.desc(), Message.role.desc())
            .limit(limit)
        )
        newest_first = list(self._session.execute(statement).scalars())
        return newest_first[::-1]

    def citation_details(
        self, conversation_id: uuid.UUID, student_id: uuid.UUID
    ) -> dict[uuid.UUID, tuple[uuid.UUID, str]]:
        """Document id and text of the chunks still cited by this student's conversation.

        Scoped by student, by the conversation's own subject and by the student's current
        enrolment in it; a chunk deleted with its document is simply absent.
        """
        statement = (
            select(DocumentChunk.id, DocumentChunk.document_id, DocumentChunk.content)
            .join(MessageSource, MessageSource.chunk_id == DocumentChunk.id)
            .join(Message, Message.id == MessageSource.message_id)
            .join(Conversation, Conversation.id == Message.conversation_id)
            .join(
                Enrollment,
                (Enrollment.student_id == Conversation.student_id)
                & (Enrollment.subject_id == Conversation.subject_id),
            )
            .where(
                Message.conversation_id == conversation_id,
                Conversation.student_id == student_id,
                DocumentChunk.subject_id == Conversation.subject_id,
            )
        )
        return {
            chunk_id: (document_id, content)
            for chunk_id, document_id, content in self._session.execute(statement)
        }
