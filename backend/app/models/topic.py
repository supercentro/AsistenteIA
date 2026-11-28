"""Topics of the PDF material of a subject. See docs/data-model.md (`document_topic_sets`).

Change `frequent-questions-and-topics`. Topics are material metadata: they name pages of a file and
hold nothing about students. The set is a table of its own because `ranges_changed_at` must outlive
an emptied list of topics.
"""

import enum
import uuid
from datetime import datetime

from sqlalchemy import (
    CheckConstraint,
    DateTime,
    FetchedValue,
    ForeignKey,
    ForeignKeyConstraint,
    Index,
    Integer,
    String,
    UniqueConstraint,
    text,
)
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base

TITLE_MAX_LENGTH = 200


class TopicSource(enum.StrEnum):
    BOOKMARKS = "bookmarks"
    TEACHER = "teacher"


class DocumentTopicSet(Base):
    """The topics of one document as a whole: where they come from and when their pages moved."""

    __tablename__ = "document_topic_sets"
    __table_args__ = (
        # Composite key: a set cannot carry a subject different from its document's subject.
        ForeignKeyConstraint(
            ["document_id", "subject_id"],
            ["documents.id", "documents.subject_id"],
            ondelete="CASCADE",
        ),
        CheckConstraint("source IN ('bookmarks', 'teacher')", name="source_known"),
        CheckConstraint("revision >= 1", name="revision_positive"),
        Index(None, "subject_id"),
    )

    document_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True)
    subject_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    source: Mapped[str] = mapped_column(String(16), nullable=False)
    revision: Mapped[int] = mapped_column(Integer, nullable=False)
    # Set by every change of page ranges after the first set, never moved back and never set on
    # insert (`FetchedValue()`): the figures of the document count only the weeks after it.
    ranges_changed_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True, server_default=FetchedValue()
    )


class DocumentTopic(Base):
    """One topic: a title and an inclusive range of pages. See docs/data-model.md."""

    __tablename__ = "document_topics"
    __table_args__ = (
        UniqueConstraint("document_id", "position"),
        CheckConstraint("position >= 0", name="position_non_negative"),
        CheckConstraint(r"title ~ '\S'", name="title_not_blank"),
        CheckConstraint("start_page >= 1 AND end_page >= start_page", name="page_range"),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, server_default=text("gen_random_uuid()")
    )
    document_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("document_topic_sets.document_id", ondelete="CASCADE"),
        nullable=False,
    )
    position: Mapped[int] = mapped_column(Integer, nullable=False)
    title: Mapped[str] = mapped_column(String(TITLE_MAX_LENGTH), nullable=False)
    start_page: Mapped[int] = mapped_column(Integer, nullable=False)
    end_page: Mapped[int] = mapped_column(Integer, nullable=False)
