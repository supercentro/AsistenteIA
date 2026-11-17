"""Integration tests for RAG quality: retrieval, citations, no-material (tasks 9.1-9.3)."""

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


def _seed_chunk(
    db_url: str,
    subject_id: str,
    content: str,
    filename: str = "notes.pdf",
    page: int = 1,
    chunk_index: int = 0,
    *,
    doc_id: uuid.UUID | None = None,
) -> uuid.UUID:
    embedder = FakeEmbedder()
    vector = embedder.embed([content])[0]
    literal = "[" + ",".join(repr(v) for v in vector) + "]"
    if doc_id is None:
        doc_id = insert_document(db_url, uuid.UUID(subject_id), filename, "ready")
    insert_chunk(
        db_url,
        doc_id,
        uuid.UUID(subject_id),
        chunk_index=chunk_index,
        embedding=literal,
        content=content,
        page_number=page,
    )
    return doc_id


def _grant_consent(client: TestClient, token: str) -> None:
    client.post(CONSENT, json={"consent_version": CONSENT_VERSION}, headers=bearer(token))


@pytest.fixture
def teacher(make_user: MakeUser) -> TestUser:
    return make_user("teacher-rag@example.com", UserRole.TEACHER)


@pytest.fixture
def student(make_user: MakeUser) -> TestUser:
    return make_user("student-rag@example.com", UserRole.STUDENT)


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
    return token, subject_id


# ------------------------------------------------ 9.1 retrieval quality


def test_answer_contains_source_citation(
    client: TestClient, clean_db: str, ready_student: tuple[str, str]
) -> None:
    """Every assistant answer persists its source chunks (traceable citations)."""
    token, subject_id = ready_student
    _seed_chunk(clean_db, subject_id, "pythagorean theorem hypotenuse formula", filename="math.pdf")
    resp = client.post(
        CHAT,
        json={"subject_id": subject_id, "message": "pythagorean theorem hypotenuse"},
        headers=bearer(token),
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["no_material"] is False
    assert len(body["sources"]) >= 1
    src = body["sources"][0]
    assert src["filename"] == "math.pdf"
    assert src["chunk_id"] is not None


def test_sources_are_persisted_in_messages(
    client: TestClient, clean_db: str, ready_student: tuple[str, str]
) -> None:
    """Sources are retrievable from the conversation messages endpoint."""
    token, subject_id = ready_student
    _seed_chunk(clean_db, subject_id, "linear algebra matrices vectors", filename="algebra.pdf")
    r = client.post(
        CHAT,
        json={"subject_id": subject_id, "message": "linear algebra matrices vectors"},
        headers=bearer(token),
    )
    conv_id = r.json()["conversation_id"]
    msgs = client.get(f"{CONVERSATIONS}/{conv_id}/messages", headers=bearer(token))
    assert msgs.status_code == 200
    assistant_msg = next(m for m in msgs.json() if m["role"] == "assistant")
    assert len(assistant_msg["sources"]) >= 1
    assert assistant_msg["sources"][0]["filename"] == "algebra.pdf"


def test_multiple_chunks_multiple_sources(
    client: TestClient, clean_db: str, ready_student: tuple[str, str]
) -> None:
    """When multiple chunks match, multiple sources are returned."""
    token, subject_id = ready_student
    doc_id = _seed_chunk(
        clean_db,
        subject_id,
        "calculus derivatives limits",
        filename="calc.pdf",
        page=1,
        chunk_index=0,
    )
    _seed_chunk(
        clean_db,
        subject_id,
        "calculus derivatives integrals",
        filename="calc.pdf",
        page=5,
        chunk_index=1,
        doc_id=doc_id,
    )
    resp = client.post(
        CHAT,
        json={"subject_id": subject_id, "message": "calculus derivatives"},
        headers=bearer(token),
    )
    assert resp.status_code == 200
    assert len(resp.json()["sources"]) >= 2


# ------------------------------------------------ 9.2 no-material behavior


def test_no_material_when_no_chunks_at_all(
    client: TestClient, ready_student: tuple[str, str]
) -> None:
    """With no chunks seeded, the controlled no-material response is returned."""
    token, subject_id = ready_student
    resp = client.post(
        CHAT,
        json={"subject_id": subject_id, "message": "quantum mechanics"},
        headers=bearer(token),
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["no_material"] is True
    assert body["sources"] == []
    assert body["answer"] != ""


def test_no_material_does_not_call_llm(client: TestClient, ready_student: tuple[str, str]) -> None:
    """No-material responses should not contain FakeLLM markers."""
    token, subject_id = ready_student
    resp = client.post(
        CHAT,
        json={"subject_id": subject_id, "message": "quantum field theory"},
        headers=bearer(token),
    )
    body = resp.json()
    assert body["no_material"] is True
    assert "[FakeLLM:" not in body["answer"]


# ------------------------------------------------ 9.3 cross-subject isolation


def test_chunks_from_other_subject_not_returned(
    client: TestClient,
    clean_db: str,
    ready_student: tuple[str, str],
    teacher: TestUser,
    student: TestUser,
) -> None:
    """Chunks from a different subject must never appear in sources."""
    token, subject_id = ready_student
    other_sub = insert_subject(clean_db, teacher.id, name="Physics")
    insert_enrollment(clean_db, other_sub, student.id)
    _seed_chunk(clean_db, other_sub, "thermodynamics entropy heat", filename="physics.pdf")
    resp = client.post(
        CHAT,
        json={"subject_id": subject_id, "message": "thermodynamics entropy heat"},
        headers=bearer(token),
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["no_material"] is True
    assert body["sources"] == []
