"""Conversations of a subject the student is no longer enrolled in are not visible (spec
conversation-history), while the right to erasure stays intact."""

import uuid

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.models.user import UserRole
from app.rag.embedder import FakeEmbedder
from app.repositories.message_repository import MessageRepository
from tests.integration.helpers import (
    MakeUser,
    TestUser,
    bearer,
    insert_enrollment,
    insert_subject,
    login_token,
)
from tests.sql_support import count, insert_chunk, insert_document, run

CHAT = "/api/v1/chat"
CONVERSATIONS = "/api/v1/conversations"
CONSENT = "/api/v1/users/me/consent"
CONTENT = "algebra equations formulas"


class Scene:
    def __init__(self, url: str, student: TestUser, subject: str, token: str) -> None:
        self.url, self.student, self.subject, self.token = url, student, subject, token

    @property
    def headers(self) -> dict[str, str]:
        return bearer(self.token)

    def unenrol(self) -> None:
        run(self.url, "DELETE FROM enrollments WHERE student_id = :s", s=self.student.id)

    def enrol(self) -> None:
        insert_enrollment(self.url, self.subject, self.student.id)


@pytest.fixture
def scene(client: TestClient, clean_db: str, make_user: MakeUser) -> Scene:
    teacher = make_user("teacher-vis@example.com", UserRole.TEACHER)
    student = make_user("student-vis@example.com", UserRole.STUDENT)
    subject = insert_subject(clean_db, teacher.id)
    insert_enrollment(clean_db, subject, student.id)
    vector = "[" + ",".join(repr(v) for v in FakeEmbedder().embed([CONTENT])[0]) + "]"
    document = insert_document(clean_db, uuid.UUID(subject), "visible.pdf", "ready")
    insert_chunk(
        clean_db, document, uuid.UUID(subject), embedding=vector, content=CONTENT, page_number=1
    )
    token = login_token(client, student.email)
    client.post(CONSENT, json={"consent_version": "2026-10-v1"}, headers=bearer(token))
    return Scene(clean_db, student, subject, token)


def _chat(client: TestClient, scene: Scene, **extra: object) -> dict[str, object]:
    payload: dict[str, object] = {"subject_id": scene.subject, "message": CONTENT}
    payload.update(extra)
    response = client.post(CHAT, json=payload, headers=scene.headers)
    assert response.status_code == 200, response.text
    body = response.json()
    assert isinstance(body, dict)
    return body


def test_an_unenrolled_student_does_not_see_the_conversation_in_the_list(
    client: TestClient, scene: Scene
) -> None:
    _chat(client, scene)
    assert len(client.get(CONVERSATIONS, headers=scene.headers).json()) == 1

    scene.unenrol()

    assert client.get(CONVERSATIONS, headers=scene.headers).json() == []
    assert (
        client.get(
            CONVERSATIONS, params={"subject_id": scene.subject}, headers=scene.headers
        ).json()
        == []
    )


def test_an_unenrolled_student_gets_404_and_no_content_for_the_messages(
    client: TestClient, scene: Scene
) -> None:
    conversation = str(_chat(client, scene)["conversation_id"])
    scene.unenrol()

    response = client.get(f"{CONVERSATIONS}/{conversation}/messages", headers=scene.headers)

    assert response.status_code == 404
    for leaked in ("visible.pdf", CONTENT, "snippet", "document_id"):
        assert leaked not in response.text


def test_an_unenrolled_student_cannot_continue_the_conversation(
    client: TestClient, scene: Scene
) -> None:
    conversation = str(_chat(client, scene)["conversation_id"])
    scene.unenrol()

    response = client.post(
        CHAT,
        json={"subject_id": scene.subject, "conversation_id": conversation, "message": CONTENT},
        headers=scene.headers,
    )

    assert response.status_code == 403


def test_an_unenrolled_student_can_still_erase_one_conversation(
    client: TestClient, scene: Scene
) -> None:
    conversation = str(_chat(client, scene)["conversation_id"])
    scene.unenrol()

    assert (
        client.delete(f"{CONVERSATIONS}/{conversation}", headers=scene.headers).status_code == 204
    )
    assert count(scene.url, "conversations") == 0 and count(scene.url, "messages") == 0


def test_an_unenrolled_student_can_still_erase_everything(client: TestClient, scene: Scene) -> None:
    _chat(client, scene)
    _chat(client, scene)
    scene.unenrol()

    response = client.delete("/api/v1/users/me/conversations", headers=scene.headers)

    assert response.status_code == 204
    assert (count(scene.url, "conversations"), count(scene.url, "message_sources")) == (0, 0)


def test_unenrolment_deletes_nothing_and_re_enrolment_restores_visibility(
    client: TestClient, scene: Scene
) -> None:
    conversation = str(_chat(client, scene)["conversation_id"])
    scene.unenrol()
    assert count(scene.url, "conversations") == 1 and count(scene.url, "messages") == 2

    scene.enrol()

    listed = client.get(CONVERSATIONS, headers=scene.headers).json()
    assert [c["id"] for c in listed] == [conversation]
    messages = client.get(f"{CONVERSATIONS}/{conversation}/messages", headers=scene.headers)
    assert messages.status_code == 200 and len(messages.json()) == 2


def test_citation_details_return_nothing_for_an_unenrolled_student(
    client: TestClient, scene: Scene, db_session: Session
) -> None:
    conversation = uuid.UUID(str(_chat(client, scene)["conversation_id"]))
    repo = MessageRepository(db_session)
    student_id = uuid.UUID(scene.student.id)
    assert repo.citation_details(conversation, student_id) != {}

    scene.unenrol()

    assert repo.citation_details(conversation, student_id) == {}
