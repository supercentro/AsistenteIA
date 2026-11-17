"""Integration tests for MessageRepository (task 4.3)."""

import uuid

import pytest
from sqlalchemy import text
from sqlalchemy.orm import Session

from app.models.user import UserRole
from app.repositories.conversation_repository import ConversationRepository
from app.repositories.message_repository import MessageRepository
from tests.integration.helpers import MakeUser, TestUser, insert_enrollment, insert_subject
from tests.sql_support import insert_chunk, insert_document


@pytest.fixture
def teacher(make_user: MakeUser) -> TestUser:
    return make_user("teacher-msg@example.com", UserRole.TEACHER)


@pytest.fixture
def student(make_user: MakeUser) -> TestUser:
    return make_user("student-msg@example.com", UserRole.STUDENT)


@pytest.fixture
def other_student(make_user: MakeUser) -> TestUser:
    return make_user("other-msg@example.com", UserRole.STUDENT)


@pytest.fixture
def subject_id(clean_db: str, teacher: TestUser) -> str:
    return insert_subject(clean_db, teacher.id)


@pytest.fixture
def enrolled(clean_db: str, subject_id: str, student: TestUser) -> None:
    insert_enrollment(clean_db, subject_id, student.id)


@pytest.fixture
def conversation_id(
    db_session: Session, student: TestUser, subject_id: str, enrolled: None
) -> uuid.UUID:
    repo = ConversationRepository(db_session)
    conv = repo.create(student_id=uuid.UUID(student.id), subject_id=uuid.UUID(subject_id))
    db_session.flush()
    return conv.id


# -------------------------------------------------------- create_with_sources


@pytest.mark.usefixtures("enrolled")
def test_create_user_message_with_no_sources(
    db_session: Session, conversation_id: uuid.UUID
) -> None:
    repo = MessageRepository(db_session)
    msg = repo.create_with_sources(
        conversation_id=conversation_id,
        role="user",
        content="Hello",
        sources=[],
    )
    assert msg.id is not None
    assert msg.role.value == "user"
    assert msg.content == "Hello"
    assert msg.sources == []


@pytest.mark.usefixtures("enrolled")
def test_create_assistant_message_with_sources(
    db_session: Session, conversation_id: uuid.UUID, clean_db: str, subject_id: str
) -> None:
    doc_id = insert_document(clean_db, uuid.UUID(subject_id), "notes.pdf", "ready")
    insert_chunk(
        clean_db,
        doc_id,
        uuid.UUID(subject_id),
        chunk_index=0,
        content="Some chunk text",
    )
    chunk_id_row = db_session.execute(
        text("SELECT id FROM document_chunks WHERE document_id = :d"),
        {"d": doc_id},
    ).first()
    assert chunk_id_row is not None
    chunk_id = chunk_id_row[0]

    repo = MessageRepository(db_session)
    msg = repo.create_with_sources(
        conversation_id=conversation_id,
        role="assistant",
        content="Answer based on notes",
        sources=[
            {
                "chunk_id": chunk_id,
                "document_filename": "notes.pdf",
                "page_number": 1,
                "rank": 1,
                "score": 0.95,
            }
        ],
    )
    assert msg.id is not None
    assert len(msg.sources) == 1
    assert msg.sources[0].document_filename == "notes.pdf"
    assert msg.sources[0].rank == 1
    assert msg.sources[0].score == pytest.approx(0.95)


# ------------------------------------------------------ list_by_conversation


@pytest.mark.usefixtures("enrolled")
def test_list_messages_returns_both_roles(
    db_session: Session, conversation_id: uuid.UUID, student: TestUser
) -> None:
    repo = MessageRepository(db_session)
    repo.create_with_sources(conversation_id=conversation_id, role="user", content="Q1", sources=[])
    repo.create_with_sources(
        conversation_id=conversation_id, role="assistant", content="A1", sources=[]
    )
    db_session.flush()
    messages = repo.list_by_conversation(conversation_id, uuid.UUID(student.id))
    assert len(messages) == 2
    roles = {m.role.value for m in messages}
    assert roles == {"user", "assistant"}


@pytest.mark.usefixtures("enrolled")
def test_list_messages_includes_sources_for_assistant(
    db_session: Session,
    conversation_id: uuid.UUID,
    student: TestUser,
    clean_db: str,
    subject_id: str,
) -> None:
    doc_id = insert_document(clean_db, uuid.UUID(subject_id), "doc.pdf", "ready")
    insert_chunk(clean_db, doc_id, uuid.UUID(subject_id), chunk_index=0, content="text")
    chunk_id = db_session.execute(
        text("SELECT id FROM document_chunks WHERE document_id = :d"), {"d": doc_id}
    ).scalar_one()

    repo = MessageRepository(db_session)
    repo.create_with_sources(conversation_id=conversation_id, role="user", content="Q", sources=[])
    repo.create_with_sources(
        conversation_id=conversation_id,
        role="assistant",
        content="A",
        sources=[
            {
                "chunk_id": chunk_id,
                "document_filename": "doc.pdf",
                "page_number": 2,
                "rank": 1,
                "score": 0.9,
            }
        ],
    )
    db_session.flush()
    messages = repo.list_by_conversation(conversation_id, uuid.UUID(student.id))
    by_role = {m.role.value: m for m in messages}
    assert by_role["user"].sources == []
    assert len(by_role["assistant"].sources) == 1
    assert by_role["assistant"].sources[0].document_filename == "doc.pdf"


@pytest.mark.usefixtures("enrolled")
def test_list_messages_other_student_returns_empty(
    db_session: Session,
    conversation_id: uuid.UUID,
    other_student: TestUser,
) -> None:
    repo = MessageRepository(db_session)
    repo.create_with_sources(conversation_id=conversation_id, role="user", content="Q", sources=[])
    db_session.flush()
    messages = repo.list_by_conversation(conversation_id, uuid.UUID(other_student.id))
    assert messages == []


# ------------------------------------------------- chunk_id SET NULL on delete


@pytest.mark.usefixtures("enrolled")
def test_chunk_id_set_null_when_document_deleted(
    db_session: Session,
    conversation_id: uuid.UUID,
    student: TestUser,
    clean_db: str,
    subject_id: str,
) -> None:
    doc_id = insert_document(clean_db, uuid.UUID(subject_id), "deleteme.pdf", "ready")
    insert_chunk(
        clean_db,
        doc_id,
        uuid.UUID(subject_id),
        chunk_index=0,
        content="to be deleted",
    )
    chunk_id = db_session.execute(
        text("SELECT id FROM document_chunks WHERE document_id = :d"), {"d": doc_id}
    ).scalar_one()

    repo = MessageRepository(db_session)
    repo.create_with_sources(
        conversation_id=conversation_id,
        role="assistant",
        content="A",
        sources=[
            {
                "chunk_id": chunk_id,
                "document_filename": "deleteme.pdf",
                "page_number": 1,
                "rank": 1,
                "score": 0.85,
            }
        ],
    )
    db_session.flush()

    db_session.execute(text("DELETE FROM document_chunks WHERE id = :cid"), {"cid": chunk_id})
    db_session.flush()

    messages = repo.list_by_conversation(conversation_id, uuid.UUID(student.id))
    src = messages[0].sources[0]
    assert src.chunk_id is None
    assert src.document_filename == "deleteme.pdf"
    assert src.page_number == 1


@pytest.mark.usefixtures("enrolled")
def test_messages_of_one_turn_are_returned_user_first(
    db_session: Session, conversation_id: uuid.UUID, student: TestUser
) -> None:
    repo = MessageRepository(db_session)
    repo.create_with_sources(
        conversation_id=conversation_id, role="assistant", content="A", sources=[]
    )
    repo.create_with_sources(conversation_id=conversation_id, role="user", content="Q", sources=[])
    db_session.flush()
    messages = repo.list_by_conversation(conversation_id, uuid.UUID(student.id))
    assert [m.role.value for m in messages] == ["user", "assistant"]
