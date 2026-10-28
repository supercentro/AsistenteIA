import uuid
from typing import NamedTuple

from psycopg import errors as pg_errors
from sqlalchemy import delete, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.core.errors import ConflictError, NotFoundError
from app.models.subject import Enrollment, Subject
from app.models.user import User


class EnrollmentRow(NamedTuple):
    """An enrollment with the student email (the only student data a teacher sees)."""

    enrollment: Enrollment
    student_email: str


class EnrollmentRepository:
    """All data access for enrollments. Reads and deletes are scoped by subject owner."""

    def __init__(self, session: Session) -> None:
        self._session = session

    def add(self, subject_id: uuid.UUID, student_id: uuid.UUID) -> Enrollment:
        """Insert an enrollment; duplicates raise `ConflictError`, vanished rows `NotFoundError`."""
        enrollment = Enrollment(subject_id=subject_id, student_id=student_id)
        try:
            with self._session.begin_nested():
                self._session.add(enrollment)
                self._session.flush()
        except IntegrityError as exc:
            if isinstance(exc.orig, pg_errors.UniqueViolation):
                raise ConflictError("Student is already enrolled in this subject") from None
            if isinstance(exc.orig, pg_errors.ForeignKeyViolation):
                # The student or the subject was deleted between the lookup and the insert.
                raise NotFoundError("Resource not found") from None
            raise
        return enrollment

    def list_for_teacher_subject(
        self, subject_id: uuid.UUID, teacher_id: uuid.UUID
    ) -> list[EnrollmentRow]:
        statement = (
            select(Enrollment, User.email)
            .join(Subject, Subject.id == Enrollment.subject_id)
            .join(User, User.id == Enrollment.student_id)
            .where(Enrollment.subject_id == subject_id, Subject.teacher_id == teacher_id)
            .order_by(Enrollment.created_at, Enrollment.id)
        )
        return [EnrollmentRow(row[0], row[1]) for row in self._session.execute(statement)]

    def delete_for_teacher_subject(
        self, subject_id: uuid.UUID, teacher_id: uuid.UUID, student_id: uuid.UUID
    ) -> bool:
        owned_subject = select(Subject.id).where(
            Subject.id == subject_id, Subject.teacher_id == teacher_id
        )
        statement = (
            delete(Enrollment)
            .where(
                Enrollment.subject_id == subject_id,
                Enrollment.student_id == student_id,
                Enrollment.subject_id.in_(owned_subject),
            )
            .returning(Enrollment.id)
        )
        return self._session.execute(statement).first() is not None
