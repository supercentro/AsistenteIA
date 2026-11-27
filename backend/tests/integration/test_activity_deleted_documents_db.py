"""V7 end to end: a real database and the real deletion of a document.

Before the correction the same steps ended with one entry of 9 appearances, which added a withheld
figure to a shown one. The correction removes that addition only: the withheld figure still follows
from the cell total and the shown figure (V8, open, `test_activity_residual_risks.py`).
Fictitious data only; the switch is on for this test application only.
"""

import uuid
from collections.abc import Iterator

import pytest
from fastapi.testclient import TestClient

from app.models.user import UserRole
from tests.activity_support import CITED_ANSWER, Classroom, at, insert_document_with_chunk
from tests.integration.helpers import MakeUser, TestUser, bearer, build_app, login_token
from tests.sql_support import insert_document, run

API = "/api/v1"
DAY = "2026-03-03"
WINDOW = {"start": "2026-03-02", "end": "2026-03-29"}


@pytest.fixture
def enabled(clean_db: str) -> Iterator[TestClient]:
    with TestClient(
        build_app(clean_db, teacher_activity_enabled=True), raise_server_exceptions=False
    ) as test_client:
        yield test_client


@pytest.fixture
def owner(make_user: MakeUser) -> TestUser:
    return make_user("owner-v7@example.com", UserRole.TEACHER)


def cite(room: Classroom, student: uuid.UUID, chunk: uuid.UUID, name: str) -> None:
    answer = room.turn(student, at(DAY), "none")
    run(room.url, "UPDATE messages SET content = :c WHERE id = :m", c=CITED_ANSWER, m=answer)
    run(
        room.url,
        "INSERT INTO message_sources (message_id, chunk_id, document_filename, page_number, "
        "rank, score) VALUES (:message, :chunk, :name, 1, 1, 0.9)",
        message=answer,
        chunk=chunk,
        name=name,
    )


def test_two_documents_of_a_subject_may_have_the_same_name(
    enabled: TestClient, owner: TestUser, clean_db: str
) -> None:
    """The precondition of V7 that the teacher controls: the upload accepts a repeated name."""
    room = Classroom(clean_db, students=5, teacher=uuid.UUID(owner.id))
    headers = bearer(login_token(enabled, owner.email, owner.password))

    for _ in range(2):
        response = enabled.post(
            f"{API}/subjects/{room.subject}/documents",
            files={"file": ("notes.txt", b"Fictitious material of the unit.")},
            headers=headers,
        )
        assert response.status_code == 202, response.text


def test_deleting_two_documents_with_one_name_never_adds_their_figures(
    enabled: TestClient, owner: TestUser, clean_db: str
) -> None:
    room = Classroom(clean_db, students=6, teacher=uuid.UUID(owner.id))
    first_id, first_chunk = insert_document_with_chunk(clean_db, room.subject, "notes.pdf")
    second_id, second_chunk = insert_document_with_chunk(clean_db, room.subject, "notes.pdf")
    for student in room.students:
        cite(room, student, first_chunk, "notes.pdf")
    for student in room.students[:3]:
        cite(room, student, second_chunk, "notes.pdf")
    headers = bearer(login_token(enabled, owner.email, owner.password))

    def read() -> tuple[list[int | None], int | None, float | None]:
        response = enabled.get(
            f"{API}/subjects/{room.subject}/activity", params=WINDOW, headers=headers
        )
        assert response.status_code == 200, response.text
        body = response.json()
        assert all(d["document_id"] is not None for d in body["documents"])
        notes = [d for d in body["documents"] if d["filename"] == "notes.pdf"]
        return (
            sorted((d["cited_appearances"] for d in notes), key=str),
            body["active_students"],
            body["no_cited_source_rate"],
        )

    def delete(document: uuid.UUID) -> None:
        response = enabled.delete(
            f"{API}/subjects/{room.subject}/documents/{document}", headers=headers
        )
        assert response.status_code == 204, response.text

    before = read()
    delete(first_id)
    after_first = read()
    delete(second_id)
    after_both = read()

    assert before == ([6, None], 6, 0.0)
    assert after_first == ([None], 6, 0.0)
    assert after_both == ([], 6, 0.0)


def test_a_document_that_is_not_ready_is_not_listed(
    enabled: TestClient, owner: TestUser, clean_db: str
) -> None:
    room = Classroom(clean_db, students=5, teacher=uuid.UUID(owner.id))
    insert_document(clean_db, room.subject, "pending.pdf", "processing")
    headers = bearer(login_token(enabled, owner.email, owner.password))

    response = enabled.get(
        f"{API}/subjects/{room.subject}/activity", params=WINDOW, headers=headers
    )

    assert response.status_code == 200, response.text
    assert [d["filename"] for d in response.json()["documents"]] == ["a.pdf", "b.pdf"]
