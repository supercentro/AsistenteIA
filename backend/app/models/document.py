import enum
import uuid
from datetime import datetime

from pgvector.sqlalchemy import VECTOR
from sqlalchemy import (
    BigInteger,
    CheckConstraint,
    DateTime,
    Enum,
    FetchedValue,
    ForeignKey,
    ForeignKeyConstraint,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
    func,
    text,
)
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import Base

# paraphrase-multilingual-MiniLM-L12-v2 produces 384-dimension vectors; the column type pins it.
EMBEDDING_DIMENSIONS = 384


class DocumentStatus(enum.StrEnum):
    PENDING = "pending"
    PROCESSING = "processing"
    READY = "ready"
    FAILED = "failed"


class Document(Base):
    """Original uploaded file (metadata only). See docs/data-model.md (`documents`)."""

    __tablename__ = "documents"
    __table_args__ = (
        # Target of the composite foreign key of `document_chunks`: keeps chunk.subject_id equal
        # to the subject of its document.
        UniqueConstraint("id", "subject_id"),
        CheckConstraint("size_bytes >= 0", name="size_bytes_non_negative"),
        CheckConstraint("chunks_count >= 0", name="chunks_count_non_negative"),
        # A failure code belongs to a failed document only. The reverse ("a failed document has a
        # code") is the service rule, so fixtures that insert failed rows without one still work.
        CheckConstraint(
            "error_code IS NULL OR status = 'failed'", name="error_code_only_when_failed"
        ),
        Index(None, "subject_id"),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, server_default=text("gen_random_uuid()")
    )
    subject_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("subjects.id", ondelete="CASCADE"), nullable=False
    )
    filename: Mapped[str] = mapped_column(String(255), nullable=False)
    content_type: Mapped[str] = mapped_column(String(100), nullable=False)
    size_bytes: Mapped[int] = mapped_column(BigInteger, nullable=False)
    status: Mapped[DocumentStatus] = mapped_column(
        Enum(
            DocumentStatus,
            name="document_status",
            values_callable=lambda enum_cls: [member.value for member in enum_cls],
        ),
        nullable=False,
        server_default=DocumentStatus.PENDING.value,
    )
    # Never set on insert (only the worker records a failure, with SQL). `FetchedValue()` keeps both
    # out of the INSERT, so the API role needs no INSERT on them (DD-14 of change
    # `database-least-privilege`); the default RETURNING reads them, and the API can SELECT them.
    error_message: Mapped[str | None] = mapped_column(
        Text, nullable=True, server_default=FetchedValue()
    )
    # One value of `DocumentErrorCode` (app.models.ingestion); the catalogue lives in code.
    error_code: Mapped[str | None] = mapped_column(
        String(40), nullable=True, server_default=FetchedValue()
    )
    chunks_count: Mapped[int] = mapped_column(Integer, nullable=False, server_default=text("0"))
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )

    # The database cascades deletes (ON DELETE CASCADE); the ORM must not load or delete chunks.
    chunks: Mapped[list["DocumentChunk"]] = relationship(
        back_populates="document", passive_deletes=True, order_by="DocumentChunk.chunk_index"
    )


class DocumentChunk(Base):
    """Text fragment with its embedding. See docs/data-model.md (`document_chunks`)."""

    __tablename__ = "document_chunks"
    __table_args__ = (
        UniqueConstraint("document_id", "chunk_index"),
        # Composite key: a chunk cannot carry a subject different from its document's subject.
        ForeignKeyConstraint(
            ["document_id", "subject_id"],
            ["documents.id", "documents.subject_id"],
            ondelete="CASCADE",
        ),
        CheckConstraint("chunk_index >= 0", name="chunk_index_non_negative"),
        CheckConstraint("page_number IS NULL OR page_number >= 1", name="page_number_positive"),
        CheckConstraint(r"content ~ '\S'", name="content_not_blank"),
        # pgvector 0.8.7 returns NaN or wrong cosine distances outside roughly 1e-21..1e19; the
        # accepted range keeps a wide margin (see the magnitude experiment report of the change).
        CheckConstraint("vector_norm(embedding) BETWEEN 1e-6 AND 1e6", name="embedding_norm_range"),
        Index(None, "subject_id"),
        # Default parameters (m=16, ef_construction=64); the MVP search does not depend on it.
        Index(
            "ix_document_chunks_embedding",
            "embedding",
            postgresql_using="hnsw",
            postgresql_with={"m": 16, "ef_construction": 64},
            postgresql_ops={"embedding": "vector_cosine_ops"},
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, server_default=text("gen_random_uuid()")
    )
    document_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    # Denormalized on purpose: every similarity query filters by subject without a join.
    subject_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    chunk_index: Mapped[int] = mapped_column(Integer, nullable=False)
    page_number: Mapped[int | None] = mapped_column(Integer, nullable=True)
    content: Mapped[str] = mapped_column(Text, nullable=False)
    embedding: Mapped[list[float]] = mapped_column(VECTOR(EMBEDDING_DIMENSIONS), nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )

    document: Mapped[Document] = relationship(back_populates="chunks")
