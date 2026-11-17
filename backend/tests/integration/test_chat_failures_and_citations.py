"""LLM 502, search 503 and citation integrity over HTTP (tasks 8.1, 8.2, 9.2, 9.3)."""

import logging
import uuid
from typing import Any

import pytest
from fastapi.testclient import TestClient
from google.genai.errors import ClientError

from app.models.user import UserRole
from app.rag.embedder import FakeEmbedder
from app.repositories.chunk_repository import ChunkRepository
from app.services.llm_service import GeminiLLMService
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
API_KEY = "AIza-test-key-for-unit-tests-only"
CHUNK_SECRET = "zebra-quartz-secret-chunk-text"
SQL_SECRET = "sql-param-sentinel-7781"
CONTENT = f"algebra equations formulas {CHUNK_SECRET}"


class _FailingModel:
    def __init__(self, exc: BaseException) -> None:
        self._exc = exc

    async def ainvoke(self, messages: Any) -> Any:
        raise self._exc


def _vec(content: str) -> str:
    return "[" + ",".join(repr(v) for v in FakeEmbedder().embed([content])[0]) + "]"


def _seed(
    db_url: str, subject_id: str, content: str = CONTENT, filename: str = "notes.pdf"
) -> uuid.UUID:
    doc_id = insert_document(db_url, uuid.UUID(subject_id), filename, "ready")
    insert_chunk(
        db_url,
        doc_id,
        uuid.UUID(subject_id),
        chunk_index=0,
        embedding=_vec(content),
        content=content,
        page_number=7,
    )
    return doc_id


@pytest.fixture
def teacher(make_user: MakeUser) -> TestUser:
    return make_user("teacher-fail@example.com", UserRole.TEACHER)


@pytest.fixture
def student(make_user: MakeUser) -> TestUser:
    return make_user("student-fail@example.com", UserRole.STUDENT)


@pytest.fixture
def subject_id(clean_db: str, teacher: TestUser) -> str:
    return insert_subject(clean_db, teacher.id)


@pytest.fixture
def ready(client: TestClient, clean_db: str, student: TestUser, subject_id: str) -> tuple[str, str]:
    insert_enrollment(clean_db, subject_id, student.id)
    token = login_token(client, student.email)
    client.post(CONSENT, json={"consent_version": CONSENT_VERSION}, headers=bearer(token))
    return token, subject_id


def _ask(
    client: TestClient, token: str, subject_id: str, message: str = "algebra equations"
) -> Any:
    return client.post(
        CHAT, json={"subject_id": subject_id, "message": message}, headers=bearer(token)
    )


def _assert_no_leak(text: str, caplog: pytest.LogCaptureFixture) -> None:
    haystacks = [text, *[r.getMessage() for r in caplog.records]]
    for forbidden in (API_KEY, CHUNK_SECRET, SQL_SECRET, "gemini-2.5-flash", "Traceback"):
        for h in haystacks:
            assert forbidden not in h, forbidden


# ------------------------------------------------------------------ 8.1 LLM errors


@pytest.mark.parametrize(
    ("exc", "code"),
    [
        (TimeoutError(f"deadline {API_KEY}"), "LLM_UNAVAILABLE"),
        (RuntimeError(f"gemini-2.5-flash exploded {API_KEY}"), "LLM_UNAVAILABLE"),
        (
            ClientError(400, {"error": {"message": f"blocked by safety filter {CHUNK_SECRET}"}}),
            "LLM_BLOCKED",
        ),
        # the words alone do not make a block (spec: provider failures are classified by status)
        (RuntimeError(f"blocked by the proxy, safety check {CHUNK_SECRET}"), "LLM_UNAVAILABLE"),
        (
            ClientError(429, {"error": {"message": f"quota blocked for safety {CHUNK_SECRET}"}}),
            "LLM_UNAVAILABLE",
        ),
    ],
)
def test_llm_failures_return_controlled_502(
    client: TestClient,
    clean_db: str,
    ready: tuple[str, str],
    monkeypatch: pytest.MonkeyPatch,
    caplog: pytest.LogCaptureFixture,
    exc: BaseException,
    code: str,
) -> None:
    token, subject_id = ready
    _seed(clean_db, subject_id)
    monkeypatch.setattr(
        "app.api.chat_deps.build_llm_service",
        lambda settings: GeminiLLMService(_FailingModel(exc), 1),
    )
    with caplog.at_level(logging.DEBUG):
        resp = _ask(client, token, subject_id)
    assert resp.status_code == 502
    assert resp.json()["code"] == code
    _assert_no_leak(resp.text, caplog)


def test_llm_failure_persists_nothing(
    client: TestClient,
    clean_db: str,
    ready: tuple[str, str],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    token, subject_id = ready
    _seed(clean_db, subject_id)
    monkeypatch.setattr(
        "app.api.chat_deps.build_llm_service",
        lambda settings: GeminiLLMService(_FailingModel(TimeoutError()), 1),
    )
    assert _ask(client, token, subject_id).status_code == 502
    assert client.get(CONVERSATIONS, headers=bearer(token)).json() == []


# ------------------------------------------------------------- 8.2 search failure


def test_search_failure_returns_controlled_503(
    client: TestClient,
    clean_db: str,
    ready: tuple[str, str],
    monkeypatch: pytest.MonkeyPatch,
    caplog: pytest.LogCaptureFixture,
) -> None:
    token, subject_id = ready
    _seed(clean_db, subject_id)

    def boom(self: ChunkRepository, *args: Any, **kwargs: Any) -> Any:
        raise RuntimeError(f"SELECT ... WHERE x = '{SQL_SECRET}' chunk {CHUNK_SECRET}")

    monkeypatch.setattr(ChunkRepository, "find_similar", boom)
    with caplog.at_level(logging.DEBUG):
        resp = _ask(client, token, subject_id)
    assert resp.status_code == 503
    assert resp.json()["code"] == "SEARCH_UNAVAILABLE"
    _assert_no_leak(resp.text, caplog)
    assert client.get(CONVERSATIONS, headers=bearer(token)).json() == []


# ------------------------------------------------------------ 9.2 snippet and topics


def test_snippet_is_capped_at_300_characters(
    client: TestClient, clean_db: str, ready: tuple[str, str]
) -> None:
    token, subject_id = ready
    long_content = "algebra equations " + ("formula " * 200)
    _seed(clean_db, subject_id, content=long_content)
    resp = _ask(client, token, subject_id, message=long_content[:1500])
    assert resp.status_code == 200
    sources = resp.json()["sources"]
    assert sources
    assert all(len(s["snippet"]) <= 300 for s in sources)
    # History sources carry no snippet: the data model does not store it (reported divergence).


def test_unrelated_topic_returns_no_material_even_with_material(
    client: TestClient, clean_db: str, ready: tuple[str, str]
) -> None:
    token, subject_id = ready
    _seed(clean_db, subject_id)
    resp = _ask(client, token, subject_id, message="volcanic basalt tectonic lava")
    assert resp.status_code == 200
    assert resp.json()["no_material"] is True
    assert resp.json()["sources"] == []


# ------------------------------------------------- 9.3 citations survive deletion


def test_citation_snapshot_survives_document_deletion(
    client: TestClient,
    clean_db: str,
    ready: tuple[str, str],
    teacher: TestUser,
) -> None:
    token, subject_id = ready
    doc_id = _seed(clean_db, subject_id, filename="lecture-7.pdf")
    resp = _ask(client, token, subject_id)
    assert resp.status_code == 200 and resp.json()["sources"]
    conv_id = resp.json()["conversation_id"]

    teacher_token = login_token(client, teacher.email)
    deleted = client.delete(
        f"/api/v1/subjects/{subject_id}/documents/{doc_id}", headers=bearer(teacher_token)
    )
    assert deleted.status_code == 204, deleted.text

    msgs = client.get(f"{CONVERSATIONS}/{conv_id}/messages", headers=bearer(token))
    assert msgs.status_code == 200
    sources = next(m for m in msgs.json() if m["role"] == "assistant")["sources"]
    assert sources
    for s in sources:
        assert s["chunk_id"] is None
        assert s["document_id"] is None
        assert s["snippet"] == ""
        assert s["filename"] == "lecture-7.pdf"
        assert s["page_number"] == 7


def test_history_sources_follow_the_canonical_source_contract(
    client: TestClient, clean_db: str, ready: tuple[str, str]
) -> None:
    token, subject_id = ready
    doc_id = _seed(clean_db, subject_id, filename="contract.pdf")
    chat = _ask(client, token, subject_id)
    live = chat.json()["sources"][0]
    msgs = client.get(
        f"{CONVERSATIONS}/{chat.json()['conversation_id']}/messages", headers=bearer(token)
    ).json()
    stored = next(m for m in msgs if m["role"] == "assistant")["sources"][0]
    assert (
        set(stored)
        == set(live)
        == {
            "chunk_id",
            "document_id",
            "filename",
            "page_number",
            "rank",
            "snippet",
        }
    )
    assert stored["document_id"] == str(doc_id) == live["document_id"]
    assert stored["snippet"] == live["snippet"] == CONTENT[:300]
