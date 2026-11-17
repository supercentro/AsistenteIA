"""Integration tests for conversation endpoints (task 7.3)."""

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
CONVERSATIONS = "/api/v1/conversations"
CONSENT = "/api/v1/users/me/consent"
CONSENT_VERSION = "2026-10-v1"
DELETE_ALL = "/api/v1/users/me/conversations"


def _seed_chunks(db_url: str, subject_id: str) -> None:
    embedder = FakeEmbedder()
    content = "algebra equations formulas"
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


def _create_conversation(client: TestClient, token: str, subject_id: str) -> str:
    resp = client.post(
        CHAT,
        json={"subject_id": subject_id, "message": "algebra equations"},
        headers=bearer(token),
    )
    assert resp.status_code == 200, resp.text
    return str(resp.json()["conversation_id"])


@pytest.fixture
def teacher(make_user: MakeUser) -> TestUser:
    return make_user("teacher-conv-api@example.com", UserRole.TEACHER)


@pytest.fixture
def student(make_user: MakeUser) -> TestUser:
    return make_user("student-conv-api@example.com", UserRole.STUDENT)


@pytest.fixture
def subject_id(clean_db: str, teacher: TestUser) -> str:
    return insert_subject(clean_db, teacher.id)


@pytest.fixture
def ready_student(
    client: TestClient, clean_db: str, student: TestUser, subject_id: str
) -> tuple[str, str]:
    """Return (token, subject_id) for an enrolled+consented student with seeded chunks."""
    insert_enrollment(clean_db, subject_id, student.id)
    token = login_token(client, student.email)
    _grant_consent(client, token)
    _seed_chunks(clean_db, subject_id)
    return token, subject_id


# ------------------------------------------------ GET /conversations


def test_list_conversations(client: TestClient, ready_student: tuple[str, str]) -> None:
    token, subject_id = ready_student
    _create_conversation(client, token, subject_id)
    _create_conversation(client, token, subject_id)
    resp = client.get(CONVERSATIONS, headers=bearer(token))
    assert resp.status_code == 200
    assert len(resp.json()) == 2
    for conv in resp.json():
        assert "id" in conv
        assert conv["subject_id"] == subject_id


def test_list_conversations_filter_by_subject(
    client: TestClient,
    clean_db: str,
    ready_student: tuple[str, str],
    teacher: TestUser,
    student: TestUser,
) -> None:
    token, subject_id = ready_student
    sub2 = insert_subject(clean_db, teacher.id, name="Physics")
    insert_enrollment(clean_db, sub2, student.id)
    _seed_chunks(clean_db, sub2)
    _create_conversation(client, token, subject_id)
    _create_conversation(client, token, sub2)
    resp = client.get(CONVERSATIONS, params={"subject_id": subject_id}, headers=bearer(token))
    assert resp.status_code == 200
    assert len(resp.json()) == 1
    assert resp.json()[0]["subject_id"] == subject_id


def test_list_conversations_empty(client: TestClient, student: TestUser) -> None:
    token = login_token(client, student.email)
    _grant_consent(client, token)
    resp = client.get(CONVERSATIONS, headers=bearer(token))
    assert resp.status_code == 200
    assert resp.json() == []


def test_list_conversations_teacher_forbidden(client: TestClient, teacher: TestUser) -> None:
    token = login_token(client, teacher.email)
    resp = client.get(CONVERSATIONS, headers=bearer(token))
    assert resp.status_code == 403


# --------------------------------------- GET /conversations/{id}/messages


def test_get_messages_with_sources(client: TestClient, ready_student: tuple[str, str]) -> None:
    token, subject_id = ready_student
    conv_id = _create_conversation(client, token, subject_id)
    resp = client.get(f"{CONVERSATIONS}/{conv_id}/messages", headers=bearer(token))
    assert resp.status_code == 200
    messages = resp.json()
    assert len(messages) == 2
    roles = [m["role"] for m in messages]
    assert "user" in roles
    assert "assistant" in roles
    assistant = next(m for m in messages if m["role"] == "assistant")
    assert len(assistant["sources"]) >= 1


def test_get_messages_other_student_404(
    client: TestClient,
    clean_db: str,
    ready_student: tuple[str, str],
    make_user: MakeUser,
) -> None:
    token_a, subject_id = ready_student
    conv_id = _create_conversation(client, token_a, subject_id)
    student_b = make_user("other-conv-api@example.com", UserRole.STUDENT)
    token_b = login_token(client, student_b.email)
    resp = client.get(f"{CONVERSATIONS}/{conv_id}/messages", headers=bearer(token_b))
    assert resp.status_code == 404


def test_get_messages_nonexistent_404(client: TestClient, student: TestUser) -> None:
    token = login_token(client, student.email)
    fake_id = str(uuid.uuid4())
    resp = client.get(f"{CONVERSATIONS}/{fake_id}/messages", headers=bearer(token))
    assert resp.status_code == 404


# --------------------------------- DELETE /conversations/{id}


def test_delete_own_conversation_204(client: TestClient, ready_student: tuple[str, str]) -> None:
    token, subject_id = ready_student
    conv_id = _create_conversation(client, token, subject_id)
    resp = client.delete(f"{CONVERSATIONS}/{conv_id}", headers=bearer(token))
    assert resp.status_code == 204
    list_resp = client.get(CONVERSATIONS, headers=bearer(token))
    assert len(list_resp.json()) == 0


def test_delete_other_student_conversation_404(
    client: TestClient,
    clean_db: str,
    ready_student: tuple[str, str],
    make_user: MakeUser,
) -> None:
    token_a, subject_id = ready_student
    conv_id = _create_conversation(client, token_a, subject_id)
    student_b = make_user("del-other-conv@example.com", UserRole.STUDENT)
    token_b = login_token(client, student_b.email)
    resp = client.delete(f"{CONVERSATIONS}/{conv_id}", headers=bearer(token_b))
    assert resp.status_code == 404


# -------------------------------- DELETE /users/me/conversations


def test_delete_all_conversations_204(client: TestClient, ready_student: tuple[str, str]) -> None:
    token, subject_id = ready_student
    _create_conversation(client, token, subject_id)
    _create_conversation(client, token, subject_id)
    resp = client.delete(DELETE_ALL, headers=bearer(token))
    assert resp.status_code == 204
    list_resp = client.get(CONVERSATIONS, headers=bearer(token))
    assert list_resp.json() == []


def test_delete_all_does_not_touch_other_student(
    client: TestClient,
    clean_db: str,
    ready_student: tuple[str, str],
    make_user: MakeUser,
    teacher: TestUser,
) -> None:
    token_a, subject_id = ready_student
    _create_conversation(client, token_a, subject_id)

    student_b = make_user("other-del-all@example.com", UserRole.STUDENT)
    sub2 = insert_subject(clean_db, teacher.id, name="Physics 2")
    insert_enrollment(clean_db, sub2, student_b.id)
    _seed_chunks(clean_db, sub2)
    token_b = login_token(client, student_b.email)
    _grant_consent(client, token_b)
    _create_conversation(client, token_b, sub2)

    client.delete(DELETE_ALL, headers=bearer(token_a))
    b_list = client.get(CONVERSATIONS, headers=bearer(token_b))
    assert len(b_list.json()) == 1


def test_delete_all_teacher_forbidden(client: TestClient, teacher: TestUser) -> None:
    token = login_token(client, teacher.email)
    resp = client.delete(DELETE_ALL, headers=bearer(token))
    assert resp.status_code == 403


# ------------------------- teacher and anonymous callers on every conversation route (PR #14)


def test_get_messages_teacher_forbidden(client: TestClient, teacher: TestUser) -> None:
    token = login_token(client, teacher.email)
    resp = client.get(f"{CONVERSATIONS}/{uuid.uuid4()}/messages", headers=bearer(token))
    assert resp.status_code == 403


def test_delete_conversation_teacher_forbidden(client: TestClient, teacher: TestUser) -> None:
    token = login_token(client, teacher.email)
    resp = client.delete(f"{CONVERSATIONS}/{uuid.uuid4()}", headers=bearer(token))
    assert resp.status_code == 403


@pytest.mark.parametrize(
    ("method", "path"),
    [
        ("GET", CONVERSATIONS),
        ("GET", f"{CONVERSATIONS}/00000000-0000-4000-8000-000000000001/messages"),
        ("DELETE", f"{CONVERSATIONS}/00000000-0000-4000-8000-000000000001"),
        ("DELETE", DELETE_ALL),
    ],
)
def test_conversation_routes_require_authentication(
    client: TestClient, method: str, path: str
) -> None:
    assert client.request(method, path).status_code == 401
