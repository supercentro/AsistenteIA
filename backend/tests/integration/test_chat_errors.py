"""Integration tests for LLM/search error handling and extreme inputs (tasks 8.1-8.3)."""

import logging
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


@pytest.fixture
def teacher(make_user: MakeUser) -> TestUser:
    return make_user("teacher-err@example.com", UserRole.TEACHER)


@pytest.fixture
def student(make_user: MakeUser) -> TestUser:
    return make_user("student-err@example.com", UserRole.STUDENT)


@pytest.fixture
def subject_id(clean_db: str, teacher: TestUser) -> str:
    return insert_subject(clean_db, teacher.id)


@pytest.fixture
def ready_student(
    client: TestClient, clean_db: str, student: TestUser, subject_id: str
) -> tuple[str, str]:
    insert_enrollment(clean_db, subject_id, student.id)
    token = login_token(client, student.email)
    _grant_consent(client, token)
    _seed_chunks(clean_db, subject_id)
    return token, subject_id


# ------------------------------------------------ 8.3 negative and extreme inputs


def test_control_characters_in_message(client: TestClient, ready_student: tuple[str, str]) -> None:
    token, subject_id = ready_student
    resp = client.post(
        CHAT,
        json={"subject_id": subject_id, "message": "hello\x00\x01\x02world"},
        headers=bearer(token),
    )
    assert resp.status_code in (200, 422)
    assert resp.status_code != 500


def test_unicode_edge_cases(client: TestClient, ready_student: tuple[str, str]) -> None:
    token, subject_id = ready_student
    resp = client.post(
        CHAT,
        json={"subject_id": subject_id, "message": "\U0001f600 emoji ​ zero-width"},
        headers=bearer(token),
    )
    assert resp.status_code in (200, 422)
    assert resp.status_code != 500


def test_invalid_uuid_subject_id(client: TestClient, student: TestUser) -> None:
    token = login_token(client, student.email)
    _grant_consent(client, token)
    resp = client.post(
        CHAT,
        json={"subject_id": "not-a-uuid", "message": "hello"},
        headers=bearer(token),
    )
    assert resp.status_code == 422


def test_invalid_uuid_conversation_id(client: TestClient, ready_student: tuple[str, str]) -> None:
    token, subject_id = ready_student
    resp = client.post(
        CHAT,
        json={
            "subject_id": subject_id,
            "conversation_id": "not-a-uuid",
            "message": "hello",
        },
        headers=bearer(token),
    )
    assert resp.status_code == 422


def test_error_responses_do_not_leak_secrets(
    client: TestClient, ready_student: tuple[str, str], caplog: pytest.LogCaptureFixture
) -> None:
    """Captured logs and error responses never expose sensitive data."""
    token, subject_id = ready_student
    with caplog.at_level(logging.WARNING):
        resp = client.post(
            CHAT,
            json={"subject_id": str(uuid.uuid4()), "message": "hello"},
            headers=bearer(token),
        )
    assert resp.status_code in (404, 422, 500, 502, 503)
    response_text = resp.text
    for forbidden in ("AIza", "password", "psycopg", "Traceback", "SELECT"):
        assert forbidden not in response_text
        for record in caplog.records:
            assert forbidden not in record.getMessage()


def test_conversations_endpoint_invalid_uuid(client: TestClient, student: TestUser) -> None:
    token = login_token(client, student.email)
    resp = client.get("/api/v1/conversations/not-a-uuid/messages", headers=bearer(token))
    assert resp.status_code == 422
