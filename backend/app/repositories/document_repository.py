"""Data access for documents and their chunks' writes (change 6, task 7.1).

Every public method is scoped by the owning teacher and the subject: there is no unscoped read.
Admission (`add_with_job`) follows design A5: the subject row is locked first (this also yields
the `404`), the documents of the subject are counted, then a global transaction-level advisory
lock is taken (always in that order, so no deadlock) and the unfinished jobs are counted and
summed. The caller owns the transaction: nothing here commits.

Chunk writes live here (`add_chunks`); they are called from the fenced final transaction of
`IngestionJobRepository`, which has already proved the worker still holds the job.
"""

import uuid
from collections.abc import Sequence
from dataclasses import dataclass
from typing import TYPE_CHECKING

from sqlalchemy import delete, func, insert, select, text
from sqlalchemy.orm import Session

from app.core.errors import DocumentQuotaExceededError, IngestionQueueFullError, NotFoundError
from app.models.document import Document, DocumentChunk, DocumentStatus
from app.models.ingestion import IngestionJob
from app.models.subject import Subject

if TYPE_CHECKING:
    from app.core.config import Settings
    from app.rag.chunker import Chunk

# Key of the global admission lock (`pg_advisory_xact_lock`); the bytes spell "ASISTENT".
ADMISSION_LOCK_KEY = 0x4153495354454E54
QUEUE_RETRY_AFTER_SECONDS = 30
_BYTES_PER_MB = 1024 * 1024


@dataclass(frozen=True)
class AdmissionLimits:
    """The hard limits checked under the admission locks."""

    max_documents: int
    queue_max: int
    pending_bytes_max: int

    @classmethod
    def from_settings(cls, settings: "Settings") -> "AdmissionLimits":
        return cls(
            max_documents=settings.max_documents_per_subject,
            queue_max=settings.ingestion_queue_max,
            pending_bytes_max=settings.ingestion_pending_bytes_max_mb * _BYTES_PER_MB,
        )


class DocumentRepository:
    """Documents of a subject, always reached through the teacher who owns the subject."""

    def __init__(self, session: Session) -> None:
        self._session = session

    def add_with_job(
        self,
        *,
        teacher_id: uuid.UUID,
        subject_id: uuid.UUID,
        filename: str,
        content_type: str,
        payload: bytes,
        limits: AdmissionLimits,
    ) -> Document:
        """Store a `pending` document and its job (with the bytes) under the admission locks.

        Raises `NotFoundError` (unknown subject or not owned: the same answer),
        `DocumentQuotaExceededError` and `IngestionQueueFullError`. The caller commits.
        """
        owned = self._session.execute(
            select(Subject.id)
            .where(Subject.id == subject_id, Subject.teacher_id == teacher_id)
            .with_for_update()
        ).scalar_one_or_none()
        if owned is None:
            raise NotFoundError("Subject not found")
        held = self._session.execute(
            select(func.count()).select_from(Document).where(Document.subject_id == subject_id)
        ).scalar_one()
        if held >= limits.max_documents:
            raise DocumentQuotaExceededError
        self._session.execute(
            text("SELECT pg_advisory_xact_lock(:key)"), {"key": ADMISSION_LOCK_KEY}
        )
        queued, queued_bytes = self._session.execute(
            select(
                func.count(),
                func.coalesce(func.sum(func.octet_length(IngestionJob.payload)), 0),
            ).where(IngestionJob.payload.is_not(None))
        ).one()
        if (
            queued >= limits.queue_max
            or int(queued_bytes) + len(payload) > limits.pending_bytes_max
        ):
            raise IngestionQueueFullError(QUEUE_RETRY_AFTER_SECONDS)
        document = Document(
            subject_id=subject_id,
            filename=filename,
            content_type=content_type,
            size_bytes=len(payload),
            status=DocumentStatus.PENDING,
        )
        self._session.add(document)
        self._session.flush()
        self._session.add(IngestionJob(document_id=document.id, payload=payload))
        self._session.flush()
        return document

    def list_for_teacher(
        self, subject_id: uuid.UUID, teacher_id: uuid.UUID
    ) -> list[Document] | None:
        """Documents of an owned subject, newest first; `None` if the subject is not owned."""
        if not self._owns(subject_id, teacher_id):
            return None
        statement = (
            select(Document)
            .where(Document.subject_id == subject_id)
            .order_by(Document.created_at.desc(), Document.id)
        )
        return list(self._session.execute(statement).scalars())

    def get_for_teacher(
        self, subject_id: uuid.UUID, document_id: uuid.UUID, teacher_id: uuid.UUID
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

    def delete_for_teacher(
        self, subject_id: uuid.UUID, document_id: uuid.UUID, teacher_id: uuid.UUID
    ) -> bool:
        """Delete a document of an owned subject (chunks and job cascade); False if not found."""
        owned_subjects = select(Subject.id).where(
            Subject.id == subject_id, Subject.teacher_id == teacher_id
        )
        statement = (
            delete(Document)
            .where(
                Document.id == document_id,
                Document.subject_id == subject_id,
                Document.subject_id.in_(owned_subjects),
            )
            .returning(Document.id)
        )
        return self._session.execute(statement).first() is not None

    def add_chunks(
        self,
        document_id: uuid.UUID,
        subject_id: uuid.UUID,
        chunks: Sequence["Chunk"],
        embeddings: Sequence[Sequence[float]],
    ) -> None:
        """Insert validated chunks of a document (called from the fenced final transaction)."""
        rows = [
            {
                "document_id": document_id,
                "subject_id": subject_id,
                "chunk_index": chunk.index,
                "page_number": chunk.page_number,
                "content": chunk.text,
                "embedding": list(embedding),
            }
            for chunk, embedding in zip(chunks, embeddings, strict=True)
        ]
        self._session.execute(insert(DocumentChunk), rows)

    def _owns(self, subject_id: uuid.UUID, teacher_id: uuid.UUID) -> bool:
        statement = select(Subject.id).where(
            Subject.id == subject_id, Subject.teacher_id == teacher_id
        )
        return self._session.execute(statement).first() is not None
