import uuid
from collections.abc import Sequence
from dataclasses import dataclass

from sqlalchemy import exists, select
from sqlalchemy.orm import Session

from app.core.vector_validation import validate_embedding, validate_subject_id, validate_top_k
from app.models.document import Document, DocumentChunk, DocumentStatus
from app.models.subject import Enrollment, Subject
from app.models.user import User, UserRole


@dataclass(frozen=True)
class SearchActor:
    """The authenticated user as the repository needs it: id and role, nothing else."""

    user_id: uuid.UUID
    role: UserRole


@dataclass(frozen=True)
class ScoredChunk:
    """One search hit with the fields later snapshotted by the chat sources (design D11)."""

    chunk_id: uuid.UUID
    document_id: uuid.UUID
    document_filename: str
    chunk_index: int
    page_number: int | None
    content: str
    similarity: float


class ChunkRepository:
    """Read access to document chunks. The only method is scoped by subject and by acting user."""

    def __init__(self, session: Session) -> None:
        self._session = session

    def find_similar(
        self,
        actor: SearchActor,
        subject_id: uuid.UUID,
        query_embedding: Sequence[float],
        top_k: int,
    ) -> list[ScoredChunk]:
        """Return up to `top_k` chunks of ready documents of the subject, nearest first.

        Authorization is part of the SQL statement: a student must be enrolled in the subject and
        a teacher must own it, and the stored role of that user must match; otherwise (and for an
        unknown subject or role) the result is empty and no error is raised. Invalid input
        (including a `subject_id` that is not a `uuid.UUID`) raises `InvalidSearchInputError`
        before any statement runs. Similarity is `1 - cosine distance`; ties break by chunk id.
        """
        validate_subject_id(subject_id)
        vector = validate_embedding(query_embedding)
        limit = validate_top_k(top_k)

        # The declared role only picks the branch. Each branch also joins `users` and requires the
        # stored role, so a false claim (or a role changed in the database) finds nothing (F7).
        if actor.role == UserRole.STUDENT:
            authorized = exists().where(
                Enrollment.subject_id == subject_id,
                Enrollment.student_id == actor.user_id,
                User.id == Enrollment.student_id,
                User.role == UserRole.STUDENT,
            )
        elif actor.role == UserRole.TEACHER:
            authorized = exists().where(
                Subject.id == subject_id,
                Subject.teacher_id == actor.user_id,
                User.id == Subject.teacher_id,
                User.role == UserRole.TEACHER,
            )
        else:
            return []

        distance = DocumentChunk.embedding.cosine_distance(vector)
        statement = (
            select(
                DocumentChunk.id,
                DocumentChunk.document_id,
                Document.filename,
                DocumentChunk.chunk_index,
                DocumentChunk.page_number,
                DocumentChunk.content,
                (1 - distance).label("similarity"),
            )
            .join(Document, Document.id == DocumentChunk.document_id)
            .where(
                DocumentChunk.subject_id == subject_id,
                Document.status == DocumentStatus.READY,
                authorized,
            )
            .order_by(distance, DocumentChunk.id)
            .limit(limit)
        )
        return [
            ScoredChunk(
                chunk_id=row.id,
                document_id=row.document_id,
                document_filename=row.filename,
                chunk_index=row.chunk_index,
                page_number=row.page_number,
                content=row.content,
                similarity=float(row.similarity),
            )
            for row in self._session.execute(statement)
        ]
