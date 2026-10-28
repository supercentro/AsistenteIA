import uuid

from psycopg import errors as pg_errors
from sqlalchemy import delete, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.core.errors import ConflictError
from app.models.subject import Enrollment, Subject


class SubjectRepository:
    """All data access for subjects. Every read and delete is scoped by the acting user."""

    def __init__(self, session: Session) -> None:
        self._session = session

    def add(self, subject: Subject) -> Subject:
        """Insert a subject; a duplicate name for the teacher raises `ConflictError`."""
        try:
            with self._session.begin_nested():
                self._session.add(subject)
                self._session.flush()
        except IntegrityError as exc:
            if isinstance(exc.orig, pg_errors.UniqueViolation):
                raise ConflictError("You already have a subject with this name") from None
            raise
        return subject

    def list_for_teacher(self, teacher_id: uuid.UUID) -> list[Subject]:
        statement = (
            select(Subject)
            .where(Subject.teacher_id == teacher_id)
            .order_by(Subject.name, Subject.id)
        )
        return list(self._session.execute(statement).scalars())

    def list_for_student(self, student_id: uuid.UUID) -> list[Subject]:
        statement = (
            select(Subject)
            .join(Enrollment, Enrollment.subject_id == Subject.id)
            .where(Enrollment.student_id == student_id)
            .order_by(Subject.name, Subject.id)
        )
        return list(self._session.execute(statement).scalars())

    def get_for_teacher(self, subject_id: uuid.UUID, teacher_id: uuid.UUID) -> Subject | None:
        statement = select(Subject).where(
            Subject.id == subject_id, Subject.teacher_id == teacher_id
        )
        return self._session.execute(statement).scalar_one_or_none()

    def get_for_student(self, subject_id: uuid.UUID, student_id: uuid.UUID) -> Subject | None:
        statement = (
            select(Subject)
            .join(Enrollment, Enrollment.subject_id == Subject.id)
            .where(Subject.id == subject_id, Enrollment.student_id == student_id)
        )
        return self._session.execute(statement).scalar_one_or_none()

    def delete_for_teacher(self, subject_id: uuid.UUID, teacher_id: uuid.UUID) -> bool:
        """Delete an owned subject (enrollments cascade in the database); False if not owned."""
        statement = (
            delete(Subject)
            .where(Subject.id == subject_id, Subject.teacher_id == teacher_id)
            .returning(Subject.id)
        )
        return self._session.execute(statement).first() is not None
