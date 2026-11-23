"""SQL fixtures for the teacher activity tests (change `activity-events-and-metrics`).

Fictitious data only. Everything is inserted straight into the database so that the tests control
the timestamps and the citation markers of every answer, which the API cannot do.
"""

import uuid
from datetime import UTC, datetime
from typing import Literal

from tests.sql_support import (
    insert_document,
    insert_enrollment,
    insert_subject,
    insert_user,
    run,
    unit_vector,
)

Kind = Literal["cited", "retrieved", "none"]
CITED_ANSWER = "Respuesta ficticia basada en el material [1]."
RETRIEVED_ANSWER = "Respuesta ficticia sin marcas de cita."
NO_MATERIAL_ANSWER = "No encontré material relevante para responder."
QUESTION = "Pregunta ficticia sobre el tema de la unidad"


def at(day: str, hour: int = 10) -> datetime:
    """A UTC timestamp on the given ISO day."""
    year, month, number = (int(part) for part in day.split("-"))
    return datetime(year, month, number, hour, 0, tzinfo=UTC)


def insert_document_with_chunk(
    url: str, subject_id: uuid.UUID, filename: str
) -> tuple[uuid.UUID, uuid.UUID]:
    """A ready document with one chunk; returns the document id and the chunk id."""
    document_id = insert_document(url, subject_id, filename, "ready")
    chunk_id = uuid.uuid4()
    run(
        url,
        "INSERT INTO document_chunks (id, document_id, subject_id, chunk_index, page_number, "
        "content, embedding) VALUES (:id, :document, :subject, 0, 1, 'chunk text', "
        "CAST(:embedding AS vector))",
        id=chunk_id,
        document=document_id,
        subject=subject_id,
        embedding=unit_vector(0),
    )
    return document_id, chunk_id


class Classroom:
    """A teacher, a subject, enrolled students and two documents, all fictitious."""

    def __init__(
        self,
        url: str,
        students: int = 6,
        prefix: str = "act",
        teacher: uuid.UUID | None = None,
    ) -> None:
        self.url = url
        self.teacher = teacher or insert_user(url, f"teacher-{prefix}@example.com", "teacher")
        self.subject = insert_subject(url, self.teacher, f"Fictitious subject {prefix}")
        self.students = [
            insert_user(url, f"student-{prefix}-{number}@example.com") for number in range(students)
        ]
        for student in self.students:
            insert_enrollment(url, self.subject, student)
        self.document_a, self.chunk_a = insert_document_with_chunk(url, self.subject, "a.pdf")
        self.document_b, self.chunk_b = insert_document_with_chunk(url, self.subject, "b.pdf")
        self._conversations: dict[uuid.UUID, uuid.UUID] = {}

    def conversation(self, student: uuid.UUID) -> uuid.UUID:
        if student not in self._conversations:
            conversation_id = uuid.uuid4()
            run(
                self.url,
                "INSERT INTO conversations (id, student_id, subject_id) "
                "VALUES (:id, :student, :subject)",
                id=conversation_id,
                student=student,
                subject=self.subject,
            )
            self._conversations[student] = conversation_id
        return self._conversations[student]

    def turn(
        self,
        student: uuid.UUID,
        when: datetime,
        kind: Kind = "cited",
        document: Literal["a", "b"] = "a",
    ) -> uuid.UUID:
        """One question and its answer; returns the id of the answer."""
        conversation = self.conversation(student)
        self._message(conversation, "user", QUESTION, when)
        chunk, name = (self.chunk_a, "a.pdf") if document == "a" else (self.chunk_b, "b.pdf")
        content = {"cited": CITED_ANSWER, "retrieved": RETRIEVED_ANSWER}.get(
            kind, NO_MATERIAL_ANSWER
        )
        answer = self._message(conversation, "assistant", content, when)
        if kind != "none":
            run(
                self.url,
                "INSERT INTO message_sources (message_id, chunk_id, document_filename, "
                "page_number, rank, score) VALUES (:message, :chunk, :name, 1, 1, 0.9)",
                message=answer,
                chunk=chunk,
                name=name,
            )
        return answer

    def _message(
        self, conversation: uuid.UUID, role: str, content: str, when: datetime
    ) -> uuid.UUID:
        message_id = uuid.uuid4()
        run(
            self.url,
            "INSERT INTO messages (id, conversation_id, role, content, created_at) "
            "VALUES (:id, :conversation, CAST(:role AS message_role), :content, :at)",
            id=message_id,
            conversation=conversation,
            role=role,
            content=content,
            at=when,
        )
        return message_id
