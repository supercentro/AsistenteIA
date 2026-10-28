import uuid
from unittest.mock import create_autospec

import pytest

from app.core.errors import NotFoundError
from app.models.subject import Subject
from app.models.user import User, UserRole
from app.repositories.subject_repository import SubjectRepository
from app.schemas.subject import SubjectCreate
from app.services.subject_service import SUBJECT_NOT_FOUND_MESSAGE, SubjectService


def make_user(role: UserRole) -> User:
    return User(
        id=uuid.uuid4(), name="N", email=f"{role.value}@example.com", password_hash="x", role=role
    )


@pytest.fixture
def repo() -> SubjectRepository:
    mock: SubjectRepository = create_autospec(SubjectRepository, instance=True)
    return mock


def test_create_assigns_the_teacher_as_owner(repo: SubjectRepository) -> None:
    teacher = make_user(UserRole.TEACHER)
    repo.add.side_effect = lambda subject: subject  # type: ignore[attr-defined]

    created = SubjectService(repo).create(teacher, SubjectCreate(name="Algebra", description="d"))

    assert created.teacher_id == teacher.id
    assert (created.name, created.description) == ("Algebra", "d")


def test_list_uses_the_teacher_or_the_student_scope_by_role(repo: SubjectRepository) -> None:
    teacher = make_user(UserRole.TEACHER)
    student = make_user(UserRole.STUDENT)
    service = SubjectService(repo)

    service.list_visible(teacher)
    service.list_visible(student)

    repo.list_for_teacher.assert_called_once_with(teacher.id)  # type: ignore[attr-defined]
    repo.list_for_student.assert_called_once_with(student.id)  # type: ignore[attr-defined]


def test_get_uses_the_scope_of_the_role_and_returns_the_subject(repo: SubjectRepository) -> None:
    teacher = make_user(UserRole.TEACHER)
    student = make_user(UserRole.STUDENT)
    subject = Subject(id=uuid.uuid4(), name="A", teacher_id=teacher.id)
    repo.get_for_teacher.return_value = subject  # type: ignore[attr-defined]
    repo.get_for_student.return_value = subject  # type: ignore[attr-defined]
    service = SubjectService(repo)

    assert service.get_visible(teacher, subject.id) is subject
    assert service.get_visible(student, subject.id) is subject
    repo.get_for_teacher.assert_called_once_with(subject.id, teacher.id)  # type: ignore[attr-defined]
    repo.get_for_student.assert_called_once_with(subject.id, student.id)  # type: ignore[attr-defined]


@pytest.mark.parametrize("role", [UserRole.TEACHER, UserRole.STUDENT])
def test_get_of_an_inaccessible_subject_raises_one_identical_not_found(
    repo: SubjectRepository, role: UserRole
) -> None:
    repo.get_for_teacher.return_value = None  # type: ignore[attr-defined]
    repo.get_for_student.return_value = None  # type: ignore[attr-defined]

    with pytest.raises(NotFoundError) as exc:
        SubjectService(repo).get_visible(make_user(role), uuid.uuid4())

    assert exc.value.message == SUBJECT_NOT_FOUND_MESSAGE
    assert exc.value.details is None


def test_delete_succeeds_for_the_owner_and_raises_not_found_otherwise(
    repo: SubjectRepository,
) -> None:
    teacher = make_user(UserRole.TEACHER)
    subject_id = uuid.uuid4()
    service = SubjectService(repo)

    repo.delete_for_teacher.return_value = True  # type: ignore[attr-defined]
    service.delete(teacher, subject_id)
    repo.delete_for_teacher.assert_called_once_with(subject_id, teacher.id)  # type: ignore[attr-defined]

    repo.delete_for_teacher.return_value = False  # type: ignore[attr-defined]
    with pytest.raises(NotFoundError) as exc:
        service.delete(teacher, subject_id)
    assert exc.value.message == SUBJECT_NOT_FOUND_MESSAGE
