"""Document use cases for the owning teacher (change 6, task 9.1).

The service never commits: the endpoints own the transaction (the upload commits explicitly before
the `202`, see design D2). Authorization is part of every repository call: the document of another
teacher's subject, an unknown subject and an unknown document are the same `404`.
"""

import logging
import uuid

from app.core.errors import NotFoundError
from app.models.document import Document as DocumentRecord
from app.repositories.document_repository import AdmissionLimits, DocumentRepository
from app.services.upload_inspection import InspectedUpload

logger = logging.getLogger(__name__)

SUBJECT_NOT_FOUND_MESSAGE = "Subject not found"
DOCUMENT_NOT_FOUND_MESSAGE = "Document not found"


class DocumentService:
    def __init__(self, documents: DocumentRepository, limits: AdmissionLimits) -> None:
        self._documents = documents
        self._limits = limits

    def upload(
        self,
        teacher_id: uuid.UUID,
        subject_id: uuid.UUID,
        inspected: InspectedUpload,
        content: bytes,
    ) -> DocumentRecord:
        """Store the document, its job and the bytes; the caller commits before answering."""
        document = self._documents.add_with_job(
            teacher_id=teacher_id,
            subject_id=subject_id,
            filename=inspected.filename,
            content_type=inspected.content_type,
            payload=content,
            limits=self._limits,
        )
        logger.info(
            "document upload stored id=%s subject=%s size=%d",
            document.id,
            subject_id,
            document.size_bytes,
        )
        return document

    def list_documents(self, teacher_id: uuid.UUID, subject_id: uuid.UUID) -> list[DocumentRecord]:
        documents = self._documents.list_for_teacher(subject_id, teacher_id)
        if documents is None:
            raise NotFoundError(SUBJECT_NOT_FOUND_MESSAGE)
        return documents

    def delete(self, teacher_id: uuid.UUID, subject_id: uuid.UUID, document_id: uuid.UUID) -> None:
        if not self._documents.delete_for_teacher(subject_id, document_id, teacher_id):
            raise NotFoundError(DOCUMENT_NOT_FOUND_MESSAGE)
        logger.info("document deleted id=%s subject=%s", document_id, subject_id)
