import uuid
from unittest.mock import create_autospec

import pytest

from app.core.errors import NotFoundError
from app.models.subject import Enrollment, Subject
from app.models.user import User, UserRole
from app.repositories.enrollment_repository import EnrollmentRepository, EnrollmentRow
from app.repositories.subject_repository import SubjectRepository
from app.repositories.user_repository import UserRepository
from app.services.enrollment_service import STUDENT_NOT_FOUND_MESSAGE, EnrollmentService
from app.services.subject_service import SUBJECT_NOT_FOUND_MESSAGE


def make_user(role: UserRole, email: str | None = None) -> User:
    return User(
        id=uuid.uuid4(),
        name="N",
        email=email or f"{role.value}@example.com",
        password_hash="x",
        role=role,
    )


class Fixture:
    def __init__(self) -> None:
        self.subjects: SubjectRepository = create_autospec(SubjectRepository, instance=True)
        self.enrollments: EnrollmentRepository = create_autospec(
            EnrollmentRepository, instance=True
        )
        self.users: UserRepository = create_autospec(UserRepository, instance=True)
        self.service = EnrollmentService(self.subjects, self.enrollments, self.users)
        self.teacher = make_user(UserRole.TEACHER)
        self.subject = Subject(id=uuid.uuid4(), name="A", teacher_id=self.teacher.id)


@pytest.fixture
def fx() -> Fixture:
    return Fixture()


def test_enroll_links_the_registered_student_after_checking_ownership(fx: Fixture) -> None:
    student = make_user(UserRole.STUDENT, "ana@example.com")
    fx.subjects.get_for_teacher.return_value = fx.subject  # type: ignore[attr-defined]
    fx.users.get_by_email.return_value = student  # type: ignore[attr-defined]
    enrollment = Enrollment(id=uuid.uuid4(), subject_id=fx.subject.id, student_id=student.id)
    fx.enrollments.add.return_value = enrollment  # type: ignore[attr-defined]

    row = fx.service.enroll(fx.teacher, fx.subject.id, "ana@example.com")

    assert row == EnrollmentRow(enrollment, "ana@example.com")
    fx.subjects.get_for_teacher.assert_called_once_with(fx.subject.id, fx.teacher.id)  # type: ignore[attr-defined]
    fx.enrollments.add.assert_called_once_with(fx.subject.id, student.id)  # type: ignore[attr-defined]


def test_ownership_is_checked_before_the_email_is_looked_up(fx: Fixture) -> None:
    fx.subjects.get_for_teacher.return_value = None  # type: ignore[attr-defined]

    with pytest.raises(NotFoundError) as exc:
        fx.service.enroll(fx.teacher, fx.subject.id, "ana@example.com")

    assert exc.value.message == SUBJECT_NOT_FOUND_MESSAGE
    fx.users.get_by_email.assert_not_called()  # type: ignore[attr-defined]
    fx.enrollments.add.assert_not_called()  # type: ignore[attr-defined]


def test_unknown_and_non_student_emails_raise_the_same_error_without_the_email(
    fx: Fixture,
) -> None:
    fx.subjects.get_for_teacher.return_value = fx.subject  # type: ignore[attr-defined]
    errors: list[NotFoundError] = []
    for found in (None, make_user(UserRole.TEACHER, "colleague@example.com")):
        fx.users.get_by_email.return_value = found  # type: ignore[attr-defined]
        with pytest.raises(NotFoundError) as exc:
            fx.service.enroll(fx.teacher, fx.subject.id, "colleague@example.com")
        errors.append(exc.value)

    first, second = errors
    assert (first.status_code, first.code, first.message, first.details) == (
        second.status_code,
        second.code,
        second.message,
        second.details,
    )
    assert "colleague" not in first.message
    assert first.details is None
    fx.enrollments.add.assert_not_called()  # type: ignore[attr-defined]


def test_vanished_student_race_gets_the_same_not_found_as_an_unknown_email(fx: Fixture) -> None:
    student = make_user(UserRole.STUDENT)
    fx.subjects.get_for_teacher.return_value = fx.subject  # type: ignore[attr-defined]
    fx.users.get_by_email.return_value = student  # type: ignore[attr-defined]
    fx.enrollments.add.side_effect = NotFoundError("Resource not found")  # type: ignore[attr-defined]

    with pytest.raises(NotFoundError) as exc:
        fx.service.enroll(fx.teacher, fx.subject.id, student.email)

    assert exc.value.message == STUDENT_NOT_FOUND_MESSAGE
    assert exc.value.details is None


def test_list_returns_an_empty_list_for_an_owned_subject_and_not_found_otherwise(
    fx: Fixture,
) -> None:
    fx.subjects.get_for_teacher.return_value = fx.subject  # type: ignore[attr-defined]
    fx.enrollments.list_for_teacher_subject.return_value = []  # type: ignore[attr-defined]
    assert fx.service.list_for_subject(fx.teacher, fx.subject.id) == []

    fx.subjects.get_for_teacher.return_value = None  # type: ignore[attr-defined]
    with pytest.raises(NotFoundError) as exc:
        fx.service.list_for_subject(fx.teacher, fx.subject.id)
    assert exc.value.message == SUBJECT_NOT_FOUND_MESSAGE


def test_remove_checks_ownership_first_then_reports_a_missing_enrollment(fx: Fixture) -> None:
    student_id = uuid.uuid4()
    fx.subjects.get_for_teacher.return_value = None  # type: ignore[attr-defined]
    with pytest.raises(NotFoundError) as not_owner:
        fx.service.remove(fx.teacher, fx.subject.id, student_id)
    assert not_owner.value.message == SUBJECT_NOT_FOUND_MESSAGE
    fx.enrollments.delete_for_teacher_subject.assert_not_called()  # type: ignore[attr-defined]

    fx.subjects.get_for_teacher.return_value = fx.subject  # type: ignore[attr-defined]
    fx.enrollments.delete_for_teacher_subject.return_value = False  # type: ignore[attr-defined]
    with pytest.raises(NotFoundError) as missing:
        fx.service.remove(fx.teacher, fx.subject.id, student_id)
    assert missing.value.message == "Enrollment not found"

    fx.enrollments.delete_for_teacher_subject.return_value = True  # type: ignore[attr-defined]
    fx.service.remove(fx.teacher, fx.subject.id, student_id)
    fx.enrollments.delete_for_teacher_subject.assert_called_with(  # type: ignore[attr-defined]
        fx.subject.id, fx.teacher.id, student_id
    )
