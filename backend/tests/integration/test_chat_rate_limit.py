"""Integration tests for POST /chat rate limiting (task 7.5)."""

import uuid

import pytest
from fastapi.testclient import TestClient

from app.models.user import UserRole
from app.rag.embedder import FakeEmbedder
from tests.integration.helpers import (
    MakeUser,
    TestUser,
    bearer,
    build_app,
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


@pytest.fixture
def _low_rate_client(clean_db: str) -> TestClient:
    """Build an app with chat_rate_limit=2/minute."""
    app = build_app(clean_db, chat_rate_limit="2/minute")
    return TestClient(app)


@pytest.fixture
def teacher(make_user: MakeUser) -> TestUser:
    return make_user("teacher-rl@example.com", UserRole.TEACHER)


@pytest.fixture
def student(make_user: MakeUser) -> TestUser:
    return make_user("student-rl@example.com", UserRole.STUDENT)


@pytest.fixture
def subject_id(clean_db: str, teacher: TestUser) -> str:
    return insert_subject(clean_db, teacher.id)


def test_chat_rate_limit_returns_429_with_retry_after(
    _low_rate_client: TestClient,
    clean_db: str,
    student: TestUser,
    subject_id: str,
) -> None:
    client = _low_rate_client
    insert_enrollment(clean_db, subject_id, student.id)
    token = login_token(client, student.email)
    client.post(CONSENT, json={"consent_version": CONSENT_VERSION}, headers=bearer(token))

    for _ in range(2):
        resp = client.post(
            CHAT,
            json={"subject_id": subject_id, "message": "algebra equations"},
            headers=bearer(token),
        )
        assert resp.status_code == 200, resp.text

    resp = client.post(
        CHAT,
        json={"subject_id": subject_id, "message": "algebra equations"},
        headers=bearer(token),
    )
    assert resp.status_code == 429
    assert "Retry-After" in resp.headers
