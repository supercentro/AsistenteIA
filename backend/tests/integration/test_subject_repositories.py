import uuid

import pytest
from sqlalchemy import text
from sqlalchemy.exc import DBAPIError
from sqlalchemy.orm import Session

from app.core.errors import ConflictError, NotFoundError
from app.models.subject import Enrollment, Subject
from app.models.user import User, UserRole
from app.repositories.enrollment_repository import EnrollmentRepository
from app.repositories.subject_repository import SubjectRepository
from app.repositories.user_repository import UserRepository


def make_user(session: Session, email: str, role: UserRole) -> User:
    return UserRepository(session).add(
        User(name=email.split("@")[0], email=email, password_hash="$argon2id$fake", role=role)
    )


def make_subject(session: Session, teacher: User, name: str = "Algebra") -> Subject:
    return SubjectRepository(session).add(
        Subject(name=name, description=None, teacher_id=teacher.id)
    )


def count(session: Session, table: str) -> int:
    return int(session.execute(text(f"SELECT count(*) FROM {table}")).scalar_one())  # noqa: S608


@pytest.fixture
def teacher(db_session: Session) -> User:
    return make_user(db_session, "teacher@example.com", UserRole.TEACHER)


@pytest.fixture
def other_teacher(db_session: Session) -> User:
    return make_user(db_session, "other.teacher@example.com", UserRole.TEACHER)


@pytest.fixture
def student(db_session: Session) -> User:
    return make_user(db_session, "student@example.com", UserRole.STUDENT)


@pytest.fixture
def other_student(db_session: Session) -> User:
    return make_user(db_session, "other.student@example.com", UserRole.STUDENT)


# --- SubjectRepository ---------------------------------------------------------------------


def test_add_assigns_id_and_created_at(db_session: Session, teacher: User) -> None:
    subject = make_subject(db_session, teacher)

    assert isinstance(subject.id, uuid.UUID)
    assert subject.created_at is not None
    assert subject.teacher_id == teacher.id


def test_add_rejects_a_duplicate_name_for_the_same_teacher_and_keeps_the_session_usable(
    db_session: Session, teacher: User
) -> None:
    make_subject(db_session, teacher, "Algebra")

    with pytest.raises(ConflictError):
        make_subject(db_session, teacher, "Algebra")

    assert make_subject(db_session, teacher, "Calculus").name == "Calculus"


def test_names_are_case_sensitive_and_shared_between_teachers(
    db_session: Session, teacher: User, other_teacher: User
) -> None:
    make_subject(db_session, teacher, "Algebra")

    assert make_subject(db_session, teacher, "algebra").name == "algebra"
    assert make_subject(db_session, other_teacher, "Algebra").name == "Algebra"


def test_list_for_teacher_returns_only_own_subjects_ordered_by_name_then_id(
    db_session: Session, teacher: User, other_teacher: User
) -> None:
    make_subject(db_session, teacher, "Zoology")
    make_subject(db_session, teacher, "Algebra")
    make_subject(db_session, other_teacher, "Biology")

    names = [s.name for s in SubjectRepository(db_session).list_for_teacher(teacher.id)]

    assert names == ["Algebra", "Zoology"]
    assert SubjectRepository(db_session).list_for_teacher(uuid.uuid4()) == []


def test_list_for_student_returns_only_enrolled_subjects(
    db_session: Session, teacher: User, student: User, other_student: User
) -> None:
    algebra = make_subject(db_session, teacher, "Algebra")
    make_subject(db_session, teacher, "Biology")
    other = make_subject(db_session, teacher, "Chemistry")
    enrollments = EnrollmentRepository(db_session)
    enrollments.add(algebra.id, student.id)
    enrollments.add(other.id, other_student.id)

    names = [s.name for s in SubjectRepository(db_session).list_for_student(student.id)]

    assert names == ["Algebra"]


def test_get_for_teacher_requires_ownership(
    db_session: Session, teacher: User, other_teacher: User
) -> None:
    subject = make_subject(db_session, teacher)
    repo = SubjectRepository(db_session)

    assert repo.get_for_teacher(subject.id, teacher.id) is subject
    assert repo.get_for_teacher(subject.id, other_teacher.id) is None
    assert repo.get_for_teacher(uuid.uuid4(), teacher.id) is None


def test_get_for_student_requires_enrollment(
    db_session: Session, teacher: User, student: User, other_student: User
) -> None:
    subject = make_subject(db_session, teacher)
    EnrollmentRepository(db_session).add(subject.id, student.id)
    repo = SubjectRepository(db_session)

    assert repo.get_for_student(subject.id, student.id) is subject
    assert repo.get_for_student(subject.id, other_student.id) is None
    assert repo.get_for_student(uuid.uuid4(), student.id) is None


def test_delete_for_teacher_only_deletes_owned_subjects(
    db_session: Session, teacher: User, other_teacher: User
) -> None:
    subject = make_subject(db_session, teacher)
    repo = SubjectRepository(db_session)

    assert repo.delete_for_teacher(subject.id, other_teacher.id) is False
    assert count(db_session, "subjects") == 1
    assert repo.delete_for_teacher(subject.id, teacher.id) is True
    assert count(db_session, "subjects") == 0
    assert repo.delete_for_teacher(subject.id, teacher.id) is False


# --- EnrollmentRepository ------------------------------------------------------------------


def test_enrollment_add_assigns_id_and_rejects_duplicates(
    db_session: Session, teacher: User, student: User
) -> None:
    subject = make_subject(db_session, teacher)
    repo = EnrollmentRepository(db_session)

    enrollment = repo.add(subject.id, student.id)

    assert isinstance(enrollment, Enrollment)
    assert isinstance(enrollment.id, uuid.UUID)
    assert enrollment.created_at is not None
    with pytest.raises(ConflictError):
        repo.add(subject.id, student.id)
    assert count(db_session, "enrollments") == 1


def test_same_student_can_join_subjects_of_different_teachers(
    db_session: Session, teacher: User, other_teacher: User, student: User
) -> None:
    first = make_subject(db_session, teacher)
    second = make_subject(db_session, other_teacher)
    repo = EnrollmentRepository(db_session)

    repo.add(first.id, student.id)
    repo.add(second.id, student.id)

    assert count(db_session, "enrollments") == 2


def test_enrollment_add_maps_a_vanished_student_to_not_found(
    db_session: Session, teacher: User
) -> None:
    subject = make_subject(db_session, teacher)

    with pytest.raises(NotFoundError):
        EnrollmentRepository(db_session).add(subject.id, uuid.uuid4())

    assert count(db_session, "enrollments") == 0


def test_list_for_teacher_subject_is_scoped_to_the_owner_and_subject(
    db_session: Session,
    teacher: User,
    other_teacher: User,
    student: User,
    other_student: User,
) -> None:
    algebra = make_subject(db_session, teacher, "Algebra")
    biology = make_subject(db_session, teacher, "Biology")
    repo = EnrollmentRepository(db_session)
    repo.add(algebra.id, student.id)
    repo.add(algebra.id, other_student.id)
    repo.add(biology.id, student.id)

    rows = repo.list_for_teacher_subject(algebra.id, teacher.id)

    assert [row.student_email for row in rows] == [
        "student@example.com",
        "other.student@example.com",
    ]
    assert {row.enrollment.subject_id for row in rows} == {algebra.id}
    assert repo.list_for_teacher_subject(algebra.id, other_teacher.id) == []
    assert repo.list_for_teacher_subject(uuid.uuid4(), teacher.id) == []


def test_delete_for_teacher_subject_is_scoped_to_owner_subject_and_student(
    db_session: Session,
    teacher: User,
    other_teacher: User,
    student: User,
    other_student: User,
) -> None:
    algebra = make_subject(db_session, teacher, "Algebra")
    biology = make_subject(db_session, teacher, "Biology")
    repo = EnrollmentRepository(db_session)
    repo.add(algebra.id, student.id)
    repo.add(biology.id, other_student.id)

    assert repo.delete_for_teacher_subject(algebra.id, other_teacher.id, student.id) is False
    assert repo.delete_for_teacher_subject(algebra.id, teacher.id, other_student.id) is False
    assert count(db_session, "enrollments") == 2
    assert repo.delete_for_teacher_subject(algebra.id, teacher.id, student.id) is True
    assert count(db_session, "enrollments") == 1
    assert repo.delete_for_teacher_subject(algebra.id, teacher.id, student.id) is False


# --- Database-level integrity --------------------------------------------------------------


def test_deleting_a_subject_cascades_to_its_enrollments_and_keeps_the_students(
    db_session: Session, teacher: User, student: User
) -> None:
    subject = make_subject(db_session, teacher)
    EnrollmentRepository(db_session).add(subject.id, student.id)

    db_session.execute(text("DELETE FROM subjects WHERE id = :id"), {"id": subject.id})

    assert count(db_session, "enrollments") == 0
    assert count(db_session, "users") == 2


def test_deleting_a_student_cascades_to_enrollments_and_keeps_the_subject(
    db_session: Session, teacher: User, student: User
) -> None:
    subject = make_subject(db_session, teacher)
    EnrollmentRepository(db_session).add(subject.id, student.id)

    db_session.execute(text("DELETE FROM users WHERE id = :id"), {"id": student.id})

    assert count(db_session, "enrollments") == 0
    assert count(db_session, "subjects") == 1
    assert subject.id is not None


def test_a_teacher_with_subjects_cannot_be_deleted(db_session: Session, teacher: User) -> None:
    make_subject(db_session, teacher)

    with pytest.raises(DBAPIError), db_session.begin_nested():
        db_session.execute(text("DELETE FROM users WHERE id = :id"), {"id": teacher.id})

    assert count(db_session, "subjects") == 1
    assert count(db_session, "users") == 1
