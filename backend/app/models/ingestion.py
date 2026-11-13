import enum
import uuid
from datetime import datetime

from sqlalchemy import (
    CheckConstraint,
    DateTime,
    FetchedValue,
    ForeignKey,
    Index,
    Integer,
    LargeBinary,
    String,
    func,
    text,
)
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base

# Width of `documents.error_code`; every member of `DocumentErrorCode` must fit.
DOCUMENT_ERROR_CODE_MAX_LENGTH = 40
# Width of `ingestion_jobs.locked_by`: a random claim token of up to 64 characters.
CLAIM_TOKEN_MAX_LENGTH = 64


class DocumentErrorCode(enum.StrEnum):
    """Closed catalogue of failure codes of a `failed` document (`document-ingestion` spec).

    Adding a code is a contract change: it needs a message below, an entry in the API contract and
    a decision of the user. The database stores the text and only checks that a code belongs to a
    failed document.
    """

    NO_EXTRACTABLE_TEXT = "NO_EXTRACTABLE_TEXT"
    ENCRYPTED_PDF = "ENCRYPTED_PDF"
    CORRUPT_FILE = "CORRUPT_FILE"
    TOO_MANY_PAGES = "TOO_MANY_PAGES"
    TEXT_TOO_LARGE = "TEXT_TOO_LARGE"
    TOO_MANY_CHUNKS = "TOO_MANY_CHUNKS"
    PROCESSING_TIMEOUT = "PROCESSING_TIMEOUT"
    RESOURCE_LIMIT_EXCEEDED = "RESOURCE_LIMIT_EXCEEDED"
    EMBEDDING_FAILED = "EMBEDDING_FAILED"
    PROCESSING_INTERRUPTED = "PROCESSING_INTERRUPTED"
    JOB_EXPIRED = "JOB_EXPIRED"
    PROCESSING_FAILED = "PROCESSING_FAILED"


# One fixed sentence per code. They are never built from parser, database or system text, never
# contain the file name or content, and are what `documents.error_message` stores.
DOCUMENT_ERROR_MESSAGES: dict[DocumentErrorCode, str] = {
    DocumentErrorCode.NO_EXTRACTABLE_TEXT: "The document has no text that can be extracted.",
    DocumentErrorCode.ENCRYPTED_PDF: "Encrypted PDF files are not supported.",
    DocumentErrorCode.CORRUPT_FILE: "The file is damaged or is not a valid document.",
    DocumentErrorCode.TOO_MANY_PAGES: "The PDF has more pages than the allowed maximum.",
    DocumentErrorCode.TEXT_TOO_LARGE: "The document contains more text than the allowed maximum.",
    DocumentErrorCode.TOO_MANY_CHUNKS: "The document would produce more fragments than allowed.",
    DocumentErrorCode.PROCESSING_TIMEOUT: "Processing the document took longer than allowed.",
    DocumentErrorCode.RESOURCE_LIMIT_EXCEEDED: "Processing the document exceeded a resource limit.",
    DocumentErrorCode.EMBEDDING_FAILED: "The text could not be converted into search vectors.",
    DocumentErrorCode.PROCESSING_INTERRUPTED: "Processing was interrupted too many times.",
    DocumentErrorCode.JOB_EXPIRED: "The document waited too long to be processed.",
    DocumentErrorCode.PROCESSING_FAILED: "The document could not be processed.",
}


class IngestionJob(Base):
    """Persistent queue entry of a document, with its temporary file bytes.

    One row per document (`UNIQUE (document_id)`), removed with it. `payload` holds the uploaded
    bytes until the document is `ready` or `failed`. `locked_by` is the random claim token that
    fences every write of a worker; `locked_until` is the lease. See docs/data-model.md.
    """

    __tablename__ = "ingestion_jobs"
    # The lease columns are never set on insert. `FetchedValue()` keeps them out of the INSERT (the
    # ORM would otherwise send NULL and the application role would need INSERT on the fencing
    # token), and `eager_defaults=False` keeps them out of RETURNING (which would need SELECT).
    # Only the worker writes them, with SQL. Decision DD-14 of change `database-least-privilege`.
    __mapper_args__ = {"eager_defaults": False}
    __table_args__ = (
        CheckConstraint("attempts >= 0", name="attempts_non_negative"),
        CheckConstraint("(locked_by IS NULL) = (locked_until IS NULL)", name="lease_consistent"),
        # The claim query looks for jobs that still hold bytes, oldest `available_at` first.
        Index(
            "ix_ingestion_jobs_claimable",
            "available_at",
            postgresql_where=text("payload IS NOT NULL"),
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, server_default=text("gen_random_uuid()")
    )
    document_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("documents.id", ondelete="CASCADE"),
        nullable=False,
        unique=True,
    )
    payload: Mapped[bytes | None] = mapped_column(LargeBinary, nullable=True)
    attempts: Mapped[int] = mapped_column(Integer, nullable=False, server_default=text("0"))
    locked_by: Mapped[str | None] = mapped_column(
        String(CLAIM_TOKEN_MAX_LENGTH), nullable=True, server_default=FetchedValue()
    )
    locked_until: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True, server_default=FetchedValue()
    )
    available_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now(), onupdate=func.now()
    )
