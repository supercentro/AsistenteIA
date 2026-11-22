"""The answer of the chat and the history say whether the sources were cited or only retrieved.

Change chat-source-presentation (slice 2). The fake embedder and a scripted model are used: no
real model is called.
"""

import uuid
from typing import Any

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
CONTENT = "algebra equations formulas about attribution"


class _ScriptedLLM:
    def __init__(self, answer: str) -> None:
        self._answer = answer

    async def generate(self, system_prompt: str, user_messages: list[dict[str, str]]) -> str:
        return self._answer


def _vec(content: str) -> str:
    return "[" + ",".join(repr(v) for v in FakeEmbedder().embed([content])[0]) + "]"


def _seed(db_url: str, subject_id: str) -> None:
    doc_id = insert_document(db_url, uuid.UUID(subject_id), "notes.pdf", "ready")
    insert_chunk(
        db_url,
        doc_id,
        uuid.UUID(subject_id),
        chunk_index=0,
        embedding=_vec(CONTENT),
        content=CONTENT,
        page_number=3,
    )


@pytest.fixture
def ready(client: TestClient, clean_db: str, make_user: MakeUser) -> tuple[str, str]:
    teacher: TestUser = make_user("teacher-attr@example.com", UserRole.TEACHER)
    student: TestUser = make_user("student-attr@example.com", UserRole.STUDENT)
    subject_id = insert_subject(clean_db, teacher.id)
    insert_enrollment(clean_db, subject_id, student.id)
    token = login_token(client, student.email)
    client.post(CONSENT, json={"consent_version": CONSENT_VERSION}, headers=bearer(token))
    _seed(clean_db, subject_id)
    return token, subject_id


def _ask(client: TestClient, token: str, subject_id: str, message: str) -> Any:
    return client.post(
        CHAT, json={"subject_id": subject_id, "message": message}, headers=bearer(token)
    )


def _history(client: TestClient, token: str, conversation_id: str) -> list[dict[str, Any]]:
    response = client.get(f"{CONVERSATIONS}/{conversation_id}/messages", headers=bearer(token))
    assert response.status_code == 200
    return list(response.json())


@pytest.mark.parametrize(
    ("answer", "expected"),
    [("According to the notes [1].", "cited"), ("According to the notes.", "retrieved")],
)
def test_the_chat_answer_and_the_history_carry_the_same_flag(
    client: TestClient,
    ready: tuple[str, str],
    monkeypatch: pytest.MonkeyPatch,
    answer: str,
    expected: str,
) -> None:
    token, subject_id = ready
    monkeypatch.setattr(
        "app.api.chat_deps.build_llm_service", lambda settings: _ScriptedLLM(answer)
    )

    chat = _ask(client, token, subject_id, "algebra equations")

    assert chat.status_code == 200
    body = chat.json()
    assert body["attribution"] == expected
    assert [s["rank"] for s in body["sources"]] == [1]
    stored = _history(client, token, body["conversation_id"])
    assistant = next(m for m in stored if m["role"] == "assistant")
    assert assistant["attribution"] == expected
    assert [s["rank"] for s in assistant["sources"]] == [1]


def test_a_question_and_a_no_material_answer_have_no_flag(
    client: TestClient, ready: tuple[str, str], monkeypatch: pytest.MonkeyPatch
) -> None:
    token, subject_id = ready
    monkeypatch.setattr(
        "app.api.chat_deps.build_llm_service", lambda settings: _ScriptedLLM("Answer [1].")
    )
    first = _ask(client, token, subject_id, "algebra equations").json()
    off_topic = _ask(client, token, subject_id, "volcanic basalt tectonic lava").json()

    assert off_topic["no_material"] is True
    assert off_topic["sources"] == []
    assert off_topic["attribution"] is None
    messages = _history(client, token, first["conversation_id"])
    assert next(m for m in messages if m["role"] == "user")["attribution"] is None


def test_the_sources_are_the_same_as_before_the_flag(
    client: TestClient, ready: tuple[str, str], monkeypatch: pytest.MonkeyPatch
) -> None:
    token, subject_id = ready
    monkeypatch.setattr(
        "app.api.chat_deps.build_llm_service", lambda settings: _ScriptedLLM("Answer [1].")
    )

    body = _ask(client, token, subject_id, "algebra equations").json()

    assert set(body["sources"][0]) == {
        "chunk_id",
        "document_id",
        "filename",
        "page_number",
        "rank",
        "snippet",
    }
