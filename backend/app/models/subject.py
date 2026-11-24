import uuid
from datetime import datetime

from sqlalchemy import (
    DateTime,
    FetchedValue,
    ForeignKey,
    Index,
    String,
    Text,
    UniqueConstraint,
    func,
    text,
)
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base


class Subject(Base):
    """Course owned by one teacher. See docs/data-model.md (`subjects`)."""

    __tablename__ = "subjects"
    __table_args__ = (UniqueConstraint("teacher_id", "name"),)

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, server_default=text("gen_random_uuid()")
    )
    name: Mapped[str] = mapped_column(String(150), nullable=False)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    # RESTRICT: a teacher who still owns subjects cannot be deleted.
    teacher_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="RESTRICT"), nullable=False
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    # The moment of the last unenrolment (database clock, never decreasing), null while there was
    # none. No reference to a student: the activity aggregate never shows a week that starts before
    # it (change `activity-privacy-hardening`). Never set on insert, only by the removal of an
    # enrolment: `FetchedValue()` keeps it out of the INSERT, so the application role needs no
    # INSERT on it.
    last_unenrolment_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True, server_default=FetchedValue()
    )


class Enrollment(Base):
    """Link between a student and a subject. See docs/data-model.md (`enrollments`)."""

    __tablename__ = "enrollments"
    __table_args__ = (UniqueConstraint("subject_id", "student_id"), Index(None, "student_id"))

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, server_default=text("gen_random_uuid()")
    )
    subject_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("subjects.id", ondelete="CASCADE"), nullable=False
    )
    student_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False
    )
    # clock_timestamp() (not now()) so enrollments created in one transaction keep their order.
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.clock_timestamp()
    )
