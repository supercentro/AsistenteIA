"""Chat endpoints over real HTTP against a Uvicorn process with the production arguments.

Covers consent, enrolment, isolation between students and messages with sources (tasks 13.3,
13.5). The LLM and the embedder are the deterministic fakes; Gemini is never called.
"""

import json
import uuid
from collections.abc import Iterator, Mapping

import pytest

from app.models.user import UserRole
from app.rag.embedder import FakeEmbedder
from tests.integration.helpers import insert_enrollment, insert_subject, insert_user
from tests.server_support import Reply, Server, login, request, running_server
from tests.sql_support import insert_chunk, insert_document, run

CONTENT = "algebra equations formulas"
CONSENT = {"consent_version": "2026-10-v1"}


@pytest.fixture(scope="module")
def server(migrated_db: str) -> Iterator[Server]:
    with running_server(migrated_db, LLM_BACKEND="fake", CHAT_RATE_LIMIT="10000/minute") as s:
        yield s


def _post(server: Server, path: str, token: str | None, payload: Mapping[str, object]) -> Reply:
    return request(server, "POST", path, token, json.dumps(payload).encode())


def _body(reply: Reply) -> dict[str, object]:
    data = reply.json()
    assert isinstance(data, dict)
    return data


def _user(url: str, role: UserRole) -> tuple[str, str]:
    email = f"{role.value}-{uuid.uuid4().hex[:8]}@example.com"
    return insert_user(url, email, role).id, email


def _student(server: Server, url: str, subject_id: str | None, consent: bool) -> str:
    student_id, email = _user(url, UserRole.STUDENT)
    if subject_id:
        insert_enrollment(url, subject_id, student_id)
    token = login(server, email)
    if consent:
        assert _post(server, "/api/v1/users/me/consent", token, CONSENT).status == 200
    return token


@pytest.fixture
def subject(clean_db: str) -> str:
    teacher_id, _ = _user(clean_db, UserRole.TEACHER)
    subject_id = insert_subject(clean_db, teacher_id)
    doc = insert_document(clean_db, uuid.UUID(subject_id), "notes.pdf", "ready")
    vector = "[" + ",".join(repr(v) for v in FakeEmbedder().embed([CONTENT])[0]) + "]"
    insert_chunk(
        clean_db, doc, uuid.UUID(subject_id), embedding=vector, content=CONTENT, page_number=3
    )
    return subject_id


def _ask(server: Server, token: str | None, subject_id: str, **extra: object) -> Reply:
    payload: dict[str, object] = {"subject_id": subject_id, "message": "algebra equations"}
    payload.update(extra)
    return _post(server, "/api/v1/chat", token, payload)


def test_unauthenticated_is_401(server: Server, subject: str) -> None:
    assert _ask(server, None, subject).status == 401


def test_teacher_is_403(server: Server, clean_db: str, subject: str) -> None:
    _, email = _user(clean_db, UserRole.TEACHER)
    assert _ask(server, login(server, email), subject).status == 403


def test_missing_consent_is_403_consent_required(
    server: Server, clean_db: str, subject: str
) -> None:
    token = _student(server, clean_db, subject, consent=False)
    reply = _ask(server, token, subject)
    assert reply.status == 403
    assert _body(reply)["code"] == "CONSENT_REQUIRED"


def test_not_enrolled_is_403(server: Server, clean_db: str, subject: str) -> None:
    token = _student(server, clean_db, None, consent=True)
    assert _ask(server, token, subject).status == 403
    assert _ask(server, token, str(uuid.uuid4())).status == 404


def test_answer_has_sources_and_history_keeps_them(
    server: Server, clean_db: str, subject: str
) -> None:
    token = _student(server, clean_db, subject, consent=True)
    reply = _ask(server, token, subject)
    assert reply.status == 200
    body = _body(reply)
    assert body["no_material"] is False
    sources = body["sources"]
    assert isinstance(sources, list) and sources
    assert sources[0]["filename"] == "notes.pdf" and sources[0]["page_number"] == 3
    history = request(
        server, "GET", f"/api/v1/conversations/{body['conversation_id']}/messages", token
    )
    assert history.status == 200
    messages = history.json()
    assert isinstance(messages, list)
    assistant = next(m for m in messages if m["role"] == "assistant")
    assert assistant["sources"] and assistant["sources"][0]["filename"] == "notes.pdf"


def test_other_student_cannot_read_continue_or_delete(
    server: Server, clean_db: str, subject: str
) -> None:
    owner = _student(server, clean_db, subject, consent=True)
    other = _student(server, clean_db, subject, consent=True)
    conv = str(_body(_ask(server, owner, subject))["conversation_id"])
    assert request(server, "GET", f"/api/v1/conversations/{conv}/messages", other).status == 404
    assert _ask(server, other, subject, conversation_id=conv).status == 404
    assert request(server, "DELETE", f"/api/v1/conversations/{conv}", other).status == 404
    assert request(server, "GET", f"/api/v1/conversations/{conv}/messages", owner).status == 200
    listed = request(server, "GET", "/api/v1/conversations", other)
    assert listed.json() == []


def test_outdated_consent_is_403_consent_required(
    server: Server, clean_db: str, subject: str
) -> None:
    token = _student(server, clean_db, subject, consent=True)
    assert _ask(server, token, subject).status == 200
    run(clean_db, "UPDATE users SET consent_version = '2025-01-v0'")
    reply = _ask(server, token, subject)
    assert reply.status == 403
    assert _body(reply)["code"] == "CONSENT_REQUIRED"
