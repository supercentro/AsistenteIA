import uuid
from datetime import datetime

from pydantic import BaseModel, ConfigDict

from app.models.document import DocumentStatus
from app.models.ingestion import DocumentErrorCode


class Document(BaseModel):
    """The `Document` schema of docs/api-spec.yml: metadata and processing state, never content.

    `error_code` and `error_message` are set only on a `failed` document. The bytes of the file,
    the chunk text and the embeddings are never part of this schema.
    """

    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    subject_id: uuid.UUID
    filename: str
    content_type: str
    size_bytes: int
    status: DocumentStatus
    error_code: DocumentErrorCode | None = None
    error_message: str | None = None
    chunks_count: int
    created_at: datetime
