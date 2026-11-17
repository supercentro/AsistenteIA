"""Integration tests for POST /chat (task 7.1)."""

import uuid

import pytest
from fastapi.testclient import TestClient

from app.models.user import UserRole
from app.rag.embedder import FakeEmbedder
from tests.integration.helpers import (
    MakeUser,
    TestUser,
    bearer,
    insert_enrollment,
    insert_subject,
    login_token,
)
from tests.sql_support import insert_chunk, insert_document

CHAT = "/api/v1/chat"
CONSENT = "/api/v1/users/me/consent"
CONSENT_VERSION = "2026-10-v1"


def _seed_chunks(db_url: str, subject_id: str, content: str = "algebra equations formulas") -> None:
    """Seed a ready document with one chunk whose embedding matches FakeEmbedder."""
    embedder = FakeEmbedder()
    vector = embedder.embed([content])[0]
    literal = "[" + ",".join(repr(v) for v in vector) + "]"
    doc_id = insert_document(db_url, uuid.UUID(subject_id), "notes.pdf", "ready")
    insert_chunk(
        db_url,
        doc_id,
        uuid.UUID(subject_id),
        chunk_index=0,
        embedding=literal,
        content=content,
        page_number=1,
    )


def _grant_consent(client: TestClient, token: str) -> None:
    client.post(CONSENT, json={"consent_version": CONSENT_VERSION}, headers=bearer(token))


@pytest.fixture
def teacher(make_user: MakeUser) -> TestUser:
    return make_user("teacher-chat@example.com", UserRole.TEACHER)


@pytest.fixture
def student(make_user: MakeUser) -> TestUser:
    return make_user("student-chat@example.com", UserRole.STUDENT)


@pytest.fixture
def subject_id(clean_db: str, teacher: TestUser) -> str:
    return insert_subject(clean_db, teacher.id)


@pytest.fixture
def enrolled_student(
    client: TestClient, clean_db: str, student: TestUser, subject_id: str
) -> tuple[str, str]:
    """Return (token, subject_id) for an enrolled+consented student."""
    insert_enrollment(clean_db, subject_id, student.id)
    token = login_token(client, student.email)
    _grant_consent(client, token)
    return token, subject_id


# ---------------------------------------------------------------- happy path


def test_chat_returns_200_with_sources(
    client: TestClient,
    clean_db: str,
    enrolled_student: tuple[str, str],
) -> None:
    token, subject_id = enrolled_student
    _seed_chunks(clean_db, subject_id)
    response = client.post(
        CHAT,
        json={"subject_id": subject_id, "message": "algebra equations"},
        headers=bearer(token),
    )
    assert response.status_code == 200
    body = response.json()
    assert "conversation_id" in body
    assert "message_id" in body
    assert "answer" in body
    assert body["no_material"] is False
    assert len(body["sources"]) >= 1
    src = body["sources"][0]
    assert src["filename"] == "notes.pdf"
    assert src["document_id"] is not None
    assert "document_filename" not in src and "score" not in src
    assert src["rank"] == 1
    assert 0 < len(src["snippet"]) <= 300


# --------------------------------------------------- no-material (no chunks)


def test_chat_no_material_when_no_chunks(
    client: TestClient,
    enrolled_student: tuple[str, str],
) -> None:
    token, subject_id = enrolled_student
    response = client.post(
        CHAT,
        json={"subject_id": subject_id, "message": "quantum physics"},
        headers=bearer(token),
    )
    assert response.status_code == 200
    body = response.json()
    assert body["no_material"] is True
    assert body["sources"] == []


# ------------------------------------------------------ consent required 403


def test_chat_missing_consent_returns_403(
    client: TestClient,
    clean_db: str,
    student: TestUser,
    subject_id: str,
) -> None:
    insert_enrollment(clean_db, subject_id, student.id)
    token = login_token(client, student.email)
    response = client.post(
        CHAT,
        json={"subject_id": subject_id, "message": "hello"},
        headers=bearer(token),
    )
    assert response.status_code == 403
    assert response.json()["code"] == "CONSENT_REQUIRED"


# ------------------------------------------------------------ teacher 403


def test_chat_teacher_returns_403(client: TestClient, teacher: TestUser) -> None:
    token = login_token(client, teacher.email)
    response = client.post(
        CHAT,
        json={"subject_id": str(uuid.uuid4()), "message": "hello"},
        headers=bearer(token),
    )
    assert response.status_code == 403


# -------------------------------------------------------- unauthenticated 401


def test_chat_no_token_returns_401(client: TestClient) -> None:
    response = client.post(
        CHAT,
        json={"subject_id": str(uuid.uuid4()), "message": "hello"},
    )
    assert response.status_code == 401


# --------------------------------- not enrolled 403, unknown subject 404


def test_chat_not_enrolled_returns_403(
    client: TestClient, student: TestUser, subject_id: str
) -> None:
    token = login_token(client, student.email)
    _grant_consent(client, token)
    response = client.post(
        CHAT,
        json={"subject_id": subject_id, "message": "hello"},
        headers=bearer(token),
    )
    assert response.status_code == 403


# ------------------------------------ invalid conversation_id (other student)


def test_chat_other_student_conversation_returns_404(
    client: TestClient,
    clean_db: str,
    make_user: MakeUser,
    enrolled_student: tuple[str, str],
) -> None:
    token_a, subject_id = enrolled_student
    _seed_chunks(clean_db, subject_id)
    resp = client.post(
        CHAT,
        json={"subject_id": subject_id, "message": "algebra equations"},
        headers=bearer(token_a),
    )
    conv_id = resp.json()["conversation_id"]

    student_b = make_user("student-b-chat@example.com", UserRole.STUDENT)
    insert_enrollment(clean_db, subject_id, student_b.id)
    token_b = login_token(client, student_b.email)
    _grant_consent(client, token_b)

    response = client.post(
        CHAT,
        json={
            "subject_id": subject_id,
            "conversation_id": conv_id,
            "message": "algebra equations",
        },
        headers=bearer(token_b),
    )
    assert response.status_code == 404


# --------------------------------------------------------- validation 422


def test_chat_empty_message_returns_422(
    client: TestClient, enrolled_student: tuple[str, str]
) -> None:
    token, subject_id = enrolled_student
    response = client.post(
        CHAT,
        json={"subject_id": subject_id, "message": ""},
        headers=bearer(token),
    )
    assert response.status_code == 422


def test_chat_oversized_message_returns_422(
    client: TestClient, enrolled_student: tuple[str, str]
) -> None:
    token, subject_id = enrolled_student
    response = client.post(
        CHAT,
        json={"subject_id": subject_id, "message": "x" * 2001},
        headers=bearer(token),
    )
    assert response.status_code == 422


# ----------------------------------------- conversation continuity


def test_chat_continues_existing_conversation(
    client: TestClient,
    clean_db: str,
    enrolled_student: tuple[str, str],
) -> None:
    token, subject_id = enrolled_student
    _seed_chunks(clean_db, subject_id)
    r1 = client.post(
        CHAT,
        json={"subject_id": subject_id, "message": "algebra equations"},
        headers=bearer(token),
    )
    conv_id = r1.json()["conversation_id"]
    r2 = client.post(
        CHAT,
        json={
            "subject_id": subject_id,
            "conversation_id": conv_id,
            "message": "algebra equations formulas",
        },
        headers=bearer(token),
    )
    assert r2.status_code == 200
    assert r2.json()["conversation_id"] == conv_id


# ------------------------------- conversation of the same student, other subject


def test_chat_conversation_of_other_subject_returns_404(
    client: TestClient,
    clean_db: str,
    teacher: TestUser,
    student: TestUser,
    enrolled_student: tuple[str, str],
) -> None:
    token, subject_id = enrolled_student
    _seed_chunks(clean_db, subject_id)
    other_subject = insert_subject(clean_db, teacher.id, name="Physics")
    insert_enrollment(clean_db, other_subject, student.id)
    _seed_chunks(clean_db, other_subject)
    first = client.post(
        CHAT,
        json={"subject_id": subject_id, "message": "algebra equations"},
        headers=bearer(token),
    )
    response = client.post(
        CHAT,
        json={
            "subject_id": other_subject,
            "conversation_id": first.json()["conversation_id"],
            "message": "algebra equations",
        },
        headers=bearer(token),
    )
    assert response.status_code == 404


def test_chat_whitespace_message_returns_422(
    client: TestClient, enrolled_student: tuple[str, str]
) -> None:
    token, subject_id = enrolled_student
    response = client.post(
        CHAT, json={"subject_id": subject_id, "message": "   "}, headers=bearer(token)
    )
    assert response.status_code == 422


def test_chat_unknown_subject_returns_404(client: TestClient, student: TestUser) -> None:
    token = login_token(client, student.email)
    _grant_consent(client, token)
    response = client.post(
        CHAT,
        json={"subject_id": str(uuid.uuid4()), "message": "hello"},
        headers=bearer(token),
    )
    assert response.status_code == 404
