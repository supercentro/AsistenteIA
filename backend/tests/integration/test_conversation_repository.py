"""Integration tests for ConversationRepository (task 4.1)."""

import uuid

import pytest
from sqlalchemy.orm import Session

from app.models.user import UserRole
from app.repositories.conversation_repository import ConversationRepository
from tests.integration.helpers import MakeUser, TestUser, insert_enrollment, insert_subject


@pytest.fixture
def teacher(make_user: MakeUser) -> TestUser:
    return make_user("teacher-conv@example.com", UserRole.TEACHER)


@pytest.fixture
def student_a(make_user: MakeUser) -> TestUser:
    return make_user("student-a-conv@example.com", UserRole.STUDENT)


@pytest.fixture
def student_b(make_user: MakeUser) -> TestUser:
    return make_user("student-b-conv@example.com", UserRole.STUDENT)


@pytest.fixture
def subject_id(clean_db: str, teacher: TestUser) -> str:
    return insert_subject(clean_db, teacher.id)


@pytest.fixture
def enrolled(clean_db: str, subject_id: str, student_a: TestUser) -> None:
    insert_enrollment(clean_db, subject_id, student_a.id)


# ------------------------------------------------------------------ create


@pytest.mark.usefixtures("enrolled")
def test_create_returns_conversation_with_ids(
    db_session: Session, student_a: TestUser, subject_id: str
) -> None:
    repo = ConversationRepository(db_session)
    conv = repo.create(student_id=uuid.UUID(student_a.id), subject_id=uuid.UUID(subject_id))
    assert conv.id is not None
    assert conv.student_id == uuid.UUID(student_a.id)
    assert conv.subject_id == uuid.UUID(subject_id)
    assert conv.created_at is not None


# -------------------------------------------------------- get_by_id_and_student


@pytest.mark.usefixtures("enrolled")
def test_get_own_conversation(db_session: Session, student_a: TestUser, subject_id: str) -> None:
    repo = ConversationRepository(db_session)
    conv = repo.create(student_id=uuid.UUID(student_a.id), subject_id=uuid.UUID(subject_id))
    found = repo.get_by_id_and_student(conv.id, uuid.UUID(student_a.id))
    assert found is not None
    assert found.id == conv.id


@pytest.mark.usefixtures("enrolled")
def test_get_other_student_conversation_returns_none(
    db_session: Session, student_a: TestUser, student_b: TestUser, subject_id: str
) -> None:
    repo = ConversationRepository(db_session)
    conv = repo.create(student_id=uuid.UUID(student_a.id), subject_id=uuid.UUID(subject_id))
    assert repo.get_by_id_and_student(conv.id, uuid.UUID(student_b.id)) is None


def test_get_nonexistent_conversation_returns_none(
    db_session: Session, student_a: TestUser
) -> None:
    repo = ConversationRepository(db_session)
    assert repo.get_by_id_and_student(uuid.uuid4(), uuid.UUID(student_a.id)) is None


# ------------------------------------------------------------ list_by_student


@pytest.mark.usefixtures("enrolled")
def test_list_returns_own_conversations(
    db_session: Session, student_a: TestUser, subject_id: str
) -> None:
    repo = ConversationRepository(db_session)
    c1 = repo.create(student_id=uuid.UUID(student_a.id), subject_id=uuid.UUID(subject_id))
    c2 = repo.create(student_id=uuid.UUID(student_a.id), subject_id=uuid.UUID(subject_id))
    result = repo.list_by_student(uuid.UUID(student_a.id))
    ids = {c.id for c in result}
    assert c1.id in ids
    assert c2.id in ids
    assert len(result) == 2


@pytest.mark.usefixtures("enrolled")
def test_list_excludes_other_student(
    db_session: Session,
    student_a: TestUser,
    student_b: TestUser,
    subject_id: str,
) -> None:
    repo = ConversationRepository(db_session)
    repo.create(student_id=uuid.UUID(student_a.id), subject_id=uuid.UUID(subject_id))
    assert repo.list_by_student(uuid.UUID(student_b.id)) == []


@pytest.mark.usefixtures("enrolled")
def test_list_with_subject_filter(
    db_session: Session, student_a: TestUser, teacher: TestUser, clean_db: str, subject_id: str
) -> None:
    repo = ConversationRepository(db_session)
    sub2 = insert_subject(clean_db, teacher.id, name="Physics")
    insert_enrollment(clean_db, sub2, student_a.id)
    repo.create(student_id=uuid.UUID(student_a.id), subject_id=uuid.UUID(subject_id))
    repo.create(student_id=uuid.UUID(student_a.id), subject_id=uuid.UUID(sub2))
    db_session.commit()
    filtered = repo.list_by_student(uuid.UUID(student_a.id), subject_id=uuid.UUID(subject_id))
    assert len(filtered) == 1
    assert filtered[0].subject_id == uuid.UUID(subject_id)


def test_list_empty_when_no_conversations(db_session: Session, student_a: TestUser) -> None:
    repo = ConversationRepository(db_session)
    assert repo.list_by_student(uuid.UUID(student_a.id)) == []


# ------------------------------------------------------ delete_by_id_and_student


@pytest.mark.usefixtures("enrolled")
def test_delete_own_conversation(db_session: Session, student_a: TestUser, subject_id: str) -> None:
    repo = ConversationRepository(db_session)
    conv = repo.create(student_id=uuid.UUID(student_a.id), subject_id=uuid.UUID(subject_id))
    assert repo.delete_by_id_and_student(conv.id, uuid.UUID(student_a.id)) is True
    assert repo.get_by_id_and_student(conv.id, uuid.UUID(student_a.id)) is None


@pytest.mark.usefixtures("enrolled")
def test_delete_other_student_conversation_returns_false(
    db_session: Session, student_a: TestUser, student_b: TestUser, subject_id: str
) -> None:
    repo = ConversationRepository(db_session)
    conv = repo.create(student_id=uuid.UUID(student_a.id), subject_id=uuid.UUID(subject_id))
    assert repo.delete_by_id_and_student(conv.id, uuid.UUID(student_b.id)) is False
    assert repo.get_by_id_and_student(conv.id, uuid.UUID(student_a.id)) is not None


# ------------------------------------------------------ delete_all_by_student


@pytest.mark.usefixtures("enrolled")
def test_delete_all_own_conversations(
    db_session: Session, student_a: TestUser, subject_id: str
) -> None:
    repo = ConversationRepository(db_session)
    repo.create(student_id=uuid.UUID(student_a.id), subject_id=uuid.UUID(subject_id))
    repo.create(student_id=uuid.UUID(student_a.id), subject_id=uuid.UUID(subject_id))
    deleted = repo.delete_all_by_student(uuid.UUID(student_a.id))
    assert deleted == 2
    assert repo.list_by_student(uuid.UUID(student_a.id)) == []


@pytest.mark.usefixtures("enrolled")
def test_delete_all_does_not_touch_other_student(
    db_session: Session,
    student_a: TestUser,
    student_b: TestUser,
    clean_db: str,
    teacher: TestUser,
    subject_id: str,
) -> None:
    sub2 = insert_subject(clean_db, teacher.id, name="Physics 2")
    insert_enrollment(clean_db, sub2, student_b.id)
    repo = ConversationRepository(db_session)
    repo.create(student_id=uuid.UUID(student_a.id), subject_id=uuid.UUID(subject_id))
    repo.create(student_id=uuid.UUID(student_b.id), subject_id=uuid.UUID(sub2))
    db_session.flush()
    repo.delete_all_by_student(uuid.UUID(student_a.id))
    assert len(repo.list_by_student(uuid.UUID(student_b.id))) == 1
