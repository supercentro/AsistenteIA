"""`GET` and `PUT /subjects/{id}/documents/{id}/topics` against a real PostgreSQL database.

Change `frequent-questions-and-topics`, task 2.2. Fictitious data only. The capability is switched
off by default, so the tests that use it build the application with both settings on.
"""

import logging
import uuid
from collections.abc import Iterator
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from app.models.user import UserRole
from app.repositories.topic_repository import TopicRepository
from tests.integration.helpers import (
    MakeUser,
    TestUser,
    bearer,
    build_app,
    insert_subject,
    login_token,
)
from tests.sql_support import count, insert_chunk, insert_document, run, scalar

API = "/api/v1"
ON = {"teacher_activity_enabled": True, "teacher_topics_enabled": True}


@dataclass
class Material:
    url: str
    owner: TestUser
    subject: uuid.UUID
    document: uuid.UUID

    @property
    def path(self) -> str:
        return f"{API}/subjects/{self.subject}/documents/{self.document}/topics"


@pytest.fixture
def enabled(clean_db: str) -> Iterator[TestClient]:
    with TestClient(build_app(clean_db, **ON), raise_server_exceptions=False) as client:
        yield client


def document_with_pages(url: str, subject: uuid.UUID, name: str, pages: tuple[int | None, ...]):  # type: ignore[no-untyped-def]
    document = insert_document(url, subject, name, "ready")
    for index, page in enumerate(pages):
        insert_chunk(url, document, subject, chunk_index=index, page_number=page)
    return document


@pytest.fixture
def material(clean_db: str, make_user: MakeUser) -> Material:
    owner = make_user("owner-topics@example.com", UserRole.TEACHER)
    subject = uuid.UUID(insert_subject(clean_db, owner.id, "Fictitious databases"))
    document = document_with_pages(clean_db, subject, "unit.pdf", (1, 2, 5, 8))
    return Material(clean_db, owner, subject, document)


def headers(client: TestClient, user: TestUser) -> dict[str, str]:
    return bearer(login_token(client, user.email, user.password))


def entry(title: str, start: int, end: int) -> dict[str, object]:
    return {"title": title, "start_page": start, "end_page": end}


def put(client: TestClient, material: Material, revision: int, *topics: dict[str, object]):  # type: ignore[no-untyped-def]
    return client.put(
        material.path,
        json={"revision": revision, "topics": list(topics)},
        headers=headers(client, material.owner),
    )


def get(client: TestClient, material: Material):  # type: ignore[no-untyped-def]
    return client.get(material.path, headers=headers(client, material.owner))


def marker(material: Material) -> object:
    return scalar(
        material.url,
        "SELECT ranges_changed_at FROM document_topic_sets WHERE document_id = :d",
        d=material.document,
    )


# --- the owner --------------------------------------------------------------------------------


def test_a_ready_pdf_without_topics_reads_as_editable_and_empty(
    enabled: TestClient, material: Material
) -> None:
    response = get(enabled, material)

    assert response.status_code == 200, response.text
    assert response.json() == {
        "document_id": str(material.document),
        "filename": "unit.pdf",
        "editable": True,
        "reason": None,
        "last_page": 8,
        "revision": 0,
        "source": None,
        "counting_from": None,
        "topics": [],
    }
    assert count(material.url, "document_topic_sets") == 0  # reading stores nothing


def test_the_owner_defines_topics_with_pages(enabled: TestClient, material: Material) -> None:
    response = put(enabled, material, 0, entry("Formas", 4, 8), entry("Modelo", 1, 3))

    assert response.status_code == 200, response.text
    body = response.json()
    assert body["revision"] == 1 and body["source"] == "teacher" and body["counting_from"] is None
    assert body["topics"] == [entry("Modelo", 1, 3), entry("Formas", 4, 8)]
    assert get(enabled, material).json() == body
    assert marker(material) is None


def test_a_rename_keeps_the_marker_and_a_changed_page_sets_it(
    enabled: TestClient, material: Material
) -> None:
    put(enabled, material, 0, entry("Modelo", 1, 5))

    renamed = put(enabled, material, 1, entry("Modelo relacional", 1, 5))

    assert renamed.status_code == 200 and renamed.json()["revision"] == 2
    assert marker(material) is None

    moved = put(enabled, material, 2, entry("Modelo relacional", 1, 4))

    assert moved.status_code == 200 and moved.json()["counting_from"] is not None
    assert marker(material) is not None


def test_clearing_keeps_the_marker_and_it_never_moves_back(
    enabled: TestClient, material: Material
) -> None:
    put(enabled, material, 0, entry("A", 1, 5))
    cleared = put(enabled, material, 1)
    assert cleared.status_code == 200 and cleared.json()["topics"] == []
    assert count(material.url, "document_topics") == 0
    first = marker(material)
    assert first is not None
    run(
        material.url,
        "UPDATE document_topic_sets SET ranges_changed_at = '2099-01-01' WHERE document_id = :d",
        d=material.document,
    )

    again = put(enabled, material, 2, entry("A", 1, 5))

    assert again.status_code == 200
    kept = marker(material)
    assert kept is not None and str(kept).startswith("2099-01-01")


def test_an_identical_write_changes_nothing(enabled: TestClient, material: Material) -> None:
    put(enabled, material, 0, entry("A", 1, 5))

    same = put(enabled, material, 1, entry("A", 1, 5))

    assert same.status_code == 200 and same.json()["revision"] == 1
    assert marker(material) is None


# --- who may ----------------------------------------------------------------------------------


@pytest.mark.parametrize("method", ["get", "put"])
def test_another_teacher_gets_the_answer_of_an_unknown_document(
    enabled: TestClient, material: Material, make_user: MakeUser, method: str
) -> None:
    other = make_user("other-topics@example.com", UserRole.TEACHER)
    body = {"revision": 0, "topics": [entry("A", 1, 2)]} if method == "put" else None
    foreign = enabled.request(method, material.path, headers=headers(enabled, other), json=body)
    unknown = enabled.request(
        method,
        f"{API}/subjects/{material.subject}/documents/{uuid.uuid4()}/topics",
        headers=headers(enabled, other),
        json=body,
    )

    assert foreign.status_code == unknown.status_code == 404
    assert foreign.json() == unknown.json()
    assert count(material.url, "document_topic_sets") == 0


@pytest.mark.parametrize("method", ["get", "put"])
def test_students_and_anonymous_callers_are_refused(
    enabled: TestClient, material: Material, make_user: MakeUser, method: str
) -> None:
    student = make_user("student-topics@example.com")
    body = {"revision": 0, "topics": []} if method == "put" else None

    assert enabled.request(method, material.path, json=body).status_code == 401
    refused = enabled.request(method, material.path, headers=headers(enabled, student), json=body)
    assert refused.status_code == 403
    assert count(material.url, "document_topic_sets") == 0


@pytest.mark.parametrize("method", ["get", "put"])
def test_a_document_of_another_subject_of_the_same_teacher_is_not_found(
    enabled: TestClient, material: Material, method: str
) -> None:
    second = uuid.UUID(insert_subject(material.url, material.owner.id, "Other subject"))
    body = {"revision": 0, "topics": [entry("A", 1, 2)]} if method == "put" else None

    response = enabled.request(
        method,
        f"{API}/subjects/{second}/documents/{material.document}/topics",
        headers=headers(enabled, material.owner),
        json=body,
    )

    assert response.status_code == 404 and count(material.url, "document_topic_sets") == 0


@pytest.mark.parametrize(
    "settings",
    [{}, {"teacher_activity_enabled": True}, {"teacher_topics_enabled": True}],
)
def test_the_routes_answer_404_unless_both_switches_are_on(
    clean_db: str, material: Material, make_user: MakeUser, settings: dict[str, object]
) -> None:
    student = make_user("student-off@example.com")
    with TestClient(build_app(clean_db, **settings), raise_server_exceptions=False) as client:
        assert get(client, material).status_code == 404
        assert put(client, material, 0, entry("A", 1, 2)).status_code == 404
        # whatever the settings are, other callers keep the usual refusal
        assert client.get(material.path).status_code == 401
        assert client.get(material.path, headers=headers(client, student)).status_code == 403
        documents = client.get(
            f"{API}/subjects/{material.subject}/documents",
            headers=headers(client, material.owner),
        )
        assert documents.status_code == 200


# --- which documents --------------------------------------------------------------------------


def test_a_text_file_has_no_pages_and_accepts_no_topics(
    enabled: TestClient, material: Material
) -> None:
    text = document_with_pages(material.url, material.subject, "notes.md", (None, None))
    target = Material(material.url, material.owner, material.subject, text)

    read = get(enabled, target).json()
    written = put(enabled, target, 0, entry("A", 1, 1))

    assert read["editable"] is False and read["reason"] == "no_pages" and read["last_page"] is None
    assert written.status_code == 409 and written.json()["details"] == {"reason": "no_pages"}


@pytest.mark.parametrize("status", ["pending", "processing", "failed"])
def test_a_document_that_is_not_ready_accepts_no_topics(
    enabled: TestClient, material: Material, status: str
) -> None:
    document = insert_document(material.url, material.subject, "later.pdf", status)
    target = Material(material.url, material.owner, material.subject, document)

    read = get(enabled, target).json()
    written = put(enabled, target, 0, entry("A", 1, 1))

    assert read["editable"] is False and read["reason"] == "not_ready"
    assert written.status_code == 409 and written.json()["details"] == {"reason": "not_ready"}


# --- refusals change nothing ------------------------------------------------------------------


@pytest.mark.parametrize(
    ("topics", "reason"),
    [
        ([entry("A", 1, 5), entry("B", 5, 8)], "overlap"),
        ([entry("A", 1, 9)], "page_range"),
        ([entry("A", 6, 2)], "page_range"),
    ],
)
def test_an_invalid_set_is_refused_and_nothing_changes(
    enabled: TestClient, material: Material, topics: list[dict[str, object]], reason: str
) -> None:
    put(enabled, material, 0, entry("Kept", 1, 2))

    response = put(enabled, material, 1, *topics)

    assert response.status_code == 422 and response.json()["details"] == {"reason": reason}
    assert get(enabled, material).json()["topics"] == [entry("Kept", 1, 2)]
    assert marker(material) is None


@pytest.mark.parametrize(
    "raw",
    [
        b'{"revision": 0, "topics": [{"title": "\\ud800", "start_page": 1, "end_page": 2}]}',
        b'{"revision": 0, "topics": [{"title": "a\\u0000", "start_page": 1, "end_page": 2}]}',
        b'{"revision": 0, "topics": [{"title": "A", "start_page": 1e999, "end_page": 2}]}',
        b'{"revision": 99999999999999999999999999, "topics": []}',
        b'{"revision": 0, "topics": [], "extra": 1}',
        b'{"revision": 0, "topics": "all"}',
        b"[]",
        b"{not json",
        b"",
        b'{"revision": 0, "topics": [' + b"[" * 5000 + b"]" * 5000 + b"]}",
    ],
)
def test_extreme_input_is_a_client_error_and_never_a_server_error(
    enabled: TestClient, material: Material, raw: bytes
) -> None:
    auth = headers(enabled, material.owner) | {"content-type": "application/json"}

    response = enabled.put(material.path, content=raw, headers=auth)

    assert 400 <= response.status_code < 500, response.text
    assert count(material.url, "document_topic_sets") == 0


@pytest.mark.parametrize(
    "path",
    [
        "{api}/subjects/not-a-uuid/documents/{document}/topics",
        "{api}/subjects/{subject}/documents/not-a-uuid/topics",
    ],
)
def test_a_malformed_identifier_is_not_found(
    enabled: TestClient, material: Material, path: str
) -> None:
    url = path.format(api=API, subject=material.subject, document=material.document)

    assert enabled.get(url, headers=headers(enabled, material.owner)).status_code == 404


def test_titles_never_reach_the_logs(
    enabled: TestClient, material: Material, caplog: pytest.LogCaptureFixture
) -> None:
    secret = "Titulo-muy-reconocible-9137"
    with caplog.at_level(logging.DEBUG):
        put(enabled, material, 0, entry(secret, 1, 2))
        put(enabled, material, 1, entry(secret, 1, 2), entry(secret, 2, 3))  # refused

    assert secret not in caplog.text


# --- concurrency ------------------------------------------------------------------------------


def test_a_stale_revision_is_refused(enabled: TestClient, material: Material) -> None:
    put(enabled, material, 0, entry("A", 1, 2))

    response = put(enabled, material, 0, entry("B", 3, 4))

    assert response.status_code == 409 and response.json()["details"] == {"reason": "stale"}
    assert get(enabled, material).json()["topics"] == [entry("A", 1, 2)]


@pytest.mark.parametrize("start_revision", [0, 1])
def test_concurrent_writes_on_one_revision_apply_only_one(
    enabled: TestClient, material: Material, start_revision: int
) -> None:
    if start_revision:
        put(enabled, material, 0, entry("Start", 1, 1))
    auth = headers(enabled, material.owner)

    def write(number: int) -> int:
        body = {"revision": start_revision, "topics": [entry(f"T{number}", number, number)]}
        return enabled.put(material.path, json=body, headers=auth).status_code

    with ThreadPoolExecutor(max_workers=6) as pool:
        codes = sorted(pool.map(write, range(2, 8)))

    assert codes == [200, 409, 409, 409, 409, 409]
    assert count(material.url, "document_topics") == 1


def test_deleting_the_document_removes_its_topics(enabled: TestClient, material: Material) -> None:
    put(enabled, material, 0, entry("A", 1, 2))

    deleted = enabled.delete(
        f"{API}/subjects/{material.subject}/documents/{material.document}",
        headers=headers(enabled, material.owner),
    )

    assert deleted.status_code == 204
    assert count(material.url, "document_topic_sets") == 0
    assert count(material.url, "document_topics") == 0
    assert put(enabled, material, 1, entry("A", 1, 2)).status_code == 404


def test_a_document_deleted_during_the_first_write_is_not_found(
    enabled: TestClient, material: Material, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The delete commits after the document was checked and before the set is inserted."""
    original = TopicRepository.create_topic_set

    def delete_first(self: TopicRepository, **kwargs: object) -> None:
        run(material.url, "DELETE FROM documents WHERE id = :d", d=material.document)
        original(self, **kwargs)  # type: ignore[arg-type]

    monkeypatch.setattr(TopicRepository, "create_topic_set", delete_first)

    response = put(enabled, material, 0, entry("A", 1, 2))

    assert response.status_code == 404, response.text
    assert count(material.url, "document_topic_sets") == 0
    assert count(material.url, "document_topics") == 0


def test_a_document_deleted_between_the_checks_of_a_write_is_not_found(
    enabled: TestClient, material: Material, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The delete commits after the document was found and before its pages are read."""
    original = TopicRepository.last_page

    def delete_first(self: TopicRepository, **kwargs: object) -> int | None:
        run(material.url, "DELETE FROM documents WHERE id = :d", d=material.document)
        return original(self, **kwargs)  # type: ignore[arg-type]

    monkeypatch.setattr(TopicRepository, "last_page", delete_first)

    response = put(enabled, material, 0, entry("A", 1, 2))

    assert response.status_code == 404, response.text
    assert count(material.url, "document_topic_sets") == 0


def test_the_repository_reads_nothing_for_another_teacher(
    enabled: TestClient, material: Material
) -> None:
    """Defence in depth (section 9.4): each query is scoped, not only the service."""
    assert put(enabled, material, 0, entry("A", 1, 2)).status_code == 200
    engine = create_engine(material.url)
    scope = {"subject_id": material.subject, "document_id": material.document}
    try:
        with Session(engine) as session:
            repository = TopicRepository(session)
            owner = uuid.UUID(material.owner.id)
            stranger = uuid.uuid4()

            assert repository.document(teacher_id=owner, **scope) is not None
            assert repository.last_page(teacher_id=owner, **scope) == 8
            assert (
                repository.stored(
                    teacher_id=owner, subject_id=material.subject, document_id=material.document
                )
                is not None
            )
            assert repository.material(teacher_id=owner, subject_id=material.subject)

            assert repository.document(teacher_id=stranger, **scope) is None
            assert repository.last_page(teacher_id=stranger, **scope) is None
            assert (
                repository.stored(
                    teacher_id=stranger, subject_id=material.subject, document_id=material.document
                )
                is None
            )
            assert repository.material(teacher_id=stranger, subject_id=material.subject) == []
    finally:
        engine.dispose()
