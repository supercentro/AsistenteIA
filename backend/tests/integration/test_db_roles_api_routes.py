"""Every API route runs under the application role and its persisted state is asserted
(change `database-least-privilege`, task 9.2).

The API is the real application (`create_app`) connected as the application role of a database
prepared like production (bootstrap, migrations to head, grants). Every write is read back with the
administrator in a separate session, because a write that fails at commit after the answer was
sent would otherwise look successful. Documents are processed by the real ingestion service under
the worker role, and retrieved with `find_similar` under the application role.
`tests/integration/test_least_privilege_coverage.py` fails when a route has no scenario here.
"""

import uuid
from collections.abc import Iterator
from contextlib import contextmanager
from typing import Any

from fastapi.testclient import TestClient

from app.core.database import create_db_engine, create_session_factory
from app.models.user import UserRole
from app.rag.embedder import FakeEmbedder
from app.repositories.chunk_repository import ChunkRepository, SearchActor
from app.services.ingestion_service import Outcome
from tests.db_admin_support import Cluster
from tests.db_admin_support import cluster as cluster  # noqa: F401  (fixture)
from tests.db_admin_support import scratch_database as scratch_database  # noqa: F401  (fixture)
from tests.db_roles_support import own_database as own_database
from tests.integration.helpers import (
    DEFAULT_PASSWORD,
    bearer,
    build_app,
    insert_enrollment,
    insert_subject,
    insert_user,
    login_token,
)
from tests.integration.test_ingestion_end_to_end import PDF_LIMITS, linux_only
from tests.pdf_support import pdf_with_pages
from tests.service_support import built_service
from tests.sql_support import insert_chunk as insert_chunk_row
from tests.sql_support import insert_document as insert_document_row

API = "/api/v1"
CURRENT = "2026-10-v1"
MARKDOWN = b"# Limits\n\nA limit describes the value a function approaches near a point."
TEXT = b"Derivatives measure the rate of change of a function over time."

SCENARIOS = {
    ("GET", f"{API}/health"): "test_registration_login_profile_and_consent_are_persisted",
    ("POST", f"{API}/auth/register"): "test_registration_login_profile_and_consent_are_persisted",
    ("POST", f"{API}/auth/login"): "test_registration_login_profile_and_consent_are_persisted",
    ("GET", f"{API}/users/me"): "test_registration_login_profile_and_consent_are_persisted",
    (
        "POST",
        f"{API}/users/me/consent",
    ): "test_registration_login_profile_and_consent_are_persisted",
    ("GET", f"{API}/subjects"): "test_subjects_and_enrollments_are_persisted_and_cascade",
    ("POST", f"{API}/subjects"): "test_subjects_and_enrollments_are_persisted_and_cascade",
    (
        "GET",
        f"{API}/subjects/{{subject_id}}",
    ): "test_subjects_and_enrollments_are_persisted_and_cascade",
    (
        "DELETE",
        f"{API}/subjects/{{subject_id}}",
    ): "test_subjects_and_enrollments_are_persisted_and_cascade",
    (
        "GET",
        f"{API}/subjects/{{subject_id}}/enrollments",
    ): "test_subjects_and_enrollments_are_persisted_and_cascade",
    (
        "POST",
        f"{API}/subjects/{{subject_id}}/enrollments",
    ): "test_subjects_and_enrollments_are_persisted_and_cascade",
    (
        "DELETE",
        f"{API}/subjects/{{subject_id}}/enrollments/{{student_id}}",
    ): "test_subjects_and_enrollments_are_persisted_and_cascade",
    (
        "GET",
        f"{API}/subjects/{{subject_id}}/documents",
    ): "test_text_and_markdown_are_uploaded_processed_retrieved_and_deleted",
    (
        "POST",
        f"{API}/subjects/{{subject_id}}/documents",
    ): "test_text_and_markdown_are_uploaded_processed_retrieved_and_deleted",
    (
        "DELETE",
        f"{API}/subjects/{{subject_id}}/documents/{{document_id}}",
    ): "test_text_and_markdown_are_uploaded_processed_retrieved_and_deleted",
    ("POST", f"{API}/chat"): "test_chat_and_conversations_are_persisted_and_cascade",
    ("GET", f"{API}/conversations"): "test_chat_and_conversations_are_persisted_and_cascade",
    (
        "GET",
        f"{API}/conversations/{{conversation_id}}/messages",
    ): "test_chat_and_conversations_are_persisted_and_cascade",
    (
        "DELETE",
        f"{API}/conversations/{{conversation_id}}",
    ): "test_chat_and_conversations_are_persisted_and_cascade",
    (
        "DELETE",
        f"{API}/users/me/conversations",
    ): "test_chat_and_conversations_are_persisted_and_cascade",
}


@contextmanager
def api(cluster: Cluster, database: str) -> Iterator[TestClient]:
    app = build_app(cluster.role_url("app", database))
    with TestClient(app, raise_server_exceptions=False) as client:
        yield client


def rows(cluster: Cluster, database: str, sql: str) -> list[tuple[Any, ...]]:
    with cluster.admin_connection(database) as conn:
        return [tuple(r) for r in conn.execute(sql).fetchall()]


def one(cluster: Cluster, database: str, sql: str) -> Any:
    found = rows(cluster, database, sql)
    assert len(found) == 1, (sql, found)
    return found[0][0]


def teacher_and_subject(cluster: Cluster, database: str, client: TestClient) -> tuple[Any, ...]:
    """A teacher (inserted by the administrator), their token and a subject created by the API."""
    teacher = insert_user(cluster.admin(database), "route.teacher@example.com", UserRole.TEACHER)
    headers = bearer(login_token(client, teacher.email, DEFAULT_PASSWORD))
    created = client.post(f"{API}/subjects", json={"name": "Calculus"}, headers=headers)
    assert created.status_code == 201, created.text
    return teacher, headers, created.json()["id"]


def test_registration_login_profile_and_consent_are_persisted(
    cluster: Cluster, own_database: str
) -> None:
    with api(cluster, own_database) as client:
        assert client.get(f"{API}/health").status_code == 200

        registered = client.post(
            f"{API}/auth/register",
            json={"name": "Ana", "email": "ana.route@example.com", "password": DEFAULT_PASSWORD},
        )
        assert registered.status_code == 201
        assert registered.json()["role"] == "student"
        user_id = registered.json()["id"]
        assert (
            one(cluster, own_database, f"SELECT role::text FROM users WHERE id = '{user_id}'")
            == "student"
        )

        headers = bearer(login_token(client, "ana.route@example.com", DEFAULT_PASSWORD))
        me = client.get(f"{API}/users/me", headers=headers)
        assert me.status_code == 200 and me.json()["id"] == user_id
        assert me.json()["consent_version"] is None

        consent = client.post(
            f"{API}/users/me/consent", json={"consent_version": CURRENT}, headers=headers
        )
        assert consent.status_code == 200
        assert rows(
            cluster,
            own_database,
            "SELECT consent_version, consent_accepted_at IS NOT NULL FROM users "
            f"WHERE id = '{user_id}'",
        ) == [(CURRENT, True)]


def test_subjects_and_enrollments_are_persisted_and_cascade(
    cluster: Cluster, own_database: str
) -> None:
    student = insert_user(
        cluster.admin(own_database), "route.student@example.com", UserRole.STUDENT
    )
    with api(cluster, own_database) as client:
        teacher, headers, subject = teacher_and_subject(cluster, own_database, client)
        student_headers = bearer(login_token(client, student.email, DEFAULT_PASSWORD))
        assert (
            one(cluster, own_database, f"SELECT name FROM subjects WHERE id = '{subject}'")
            == "Calculus"
        )
        assert [s["id"] for s in client.get(f"{API}/subjects", headers=headers).json()] == [subject]
        assert client.get(f"{API}/subjects/{subject}", headers=headers).status_code == 200

        enrolled = client.post(
            f"{API}/subjects/{subject}/enrollments",
            json={"student_email": student.email},
            headers=headers,
        )
        assert enrolled.status_code == 201
        assert (
            one(
                cluster,
                own_database,
                f"SELECT count(*) FROM enrollments WHERE subject_id = '{subject}'",
            )
            == 1
        )
        listed = client.get(f"{API}/subjects/{subject}/enrollments", headers=headers).json()
        assert [e["student_email"] for e in listed] == [student.email]
        assert client.get(f"{API}/subjects/{subject}", headers=student_headers).status_code == 200

        removed = client.delete(
            f"{API}/subjects/{subject}/enrollments/{student.id}", headers=headers
        )
        assert removed.status_code == 204
        assert (
            one(
                cluster,
                own_database,
                f"SELECT count(*) FROM enrollments WHERE subject_id = '{subject}'",
            )
            == 0
        )

        client.post(
            f"{API}/subjects/{subject}/enrollments",
            json={"student_email": student.email},
            headers=headers,
        )
        deleted = client.delete(f"{API}/subjects/{subject}", headers=headers)
        assert deleted.status_code == 204
        for table in ("subjects", "enrollments"):  # the cascade removed the children as well
            column = "id" if table == "subjects" else "subject_id"
            assert (
                one(
                    cluster,
                    own_database,
                    f"SELECT count(*) FROM {table} WHERE {column} = '{subject}'",
                )
                == 0
            )
        assert teacher is not None


def upload(
    client: TestClient, headers: dict[str, str], subject: str, name: str, body: bytes, kind: str
) -> Any:
    return client.post(
        f"{API}/subjects/{subject}/documents", files={"file": (name, body, kind)}, headers=headers
    )


def retrieve(url: str, actor: SearchActor, subject: uuid.UUID, question: str) -> list[Any]:
    engine = create_db_engine(url)
    try:
        with create_session_factory(engine)() as session:
            vector = FakeEmbedder().embed([question])[0]
            return ChunkRepository(session).find_similar(actor, subject, vector, top_k=5)
    finally:
        engine.dispose()


def test_text_and_markdown_are_uploaded_processed_retrieved_and_deleted(
    cluster: Cluster, own_database: str
) -> None:
    with api(cluster, own_database) as client:
        teacher, headers, subject = teacher_and_subject(cluster, own_database, client)
        accepted = [
            upload(client, headers, subject, "calculus.txt", TEXT, "text/plain"),
            upload(client, headers, subject, "limits.md", MARKDOWN, "text/markdown"),
        ]
        assert [r.status_code for r in accepted] == [202, 202]
        ids = [r.json()["id"] for r in accepted]
        # persisted by the commit that preceded the 202: pending documents with their bytes
        assert rows(
            cluster,
            own_database,
            "SELECT d.status::text, j.payload IS NOT NULL, j.locked_by FROM documents d "
            "JOIN ingestion_jobs j ON j.document_id = d.id "
            f"WHERE d.subject_id = '{subject}' ORDER BY d.filename",
        ) == [("pending", True, None), ("pending", True, None)]

        worker_url = cluster.role_url("worker", own_database)
        with built_service(worker_url) as built:  # the real service under the worker role
            assert [built.service.run_once(), built.service.run_once()] == [Outcome.READY] * 2
        assert rows(
            cluster,
            own_database,
            "SELECT status::text, chunks_count > 0 FROM documents "
            f"WHERE subject_id = '{subject}' ORDER BY filename",
        ) == [("ready", True), ("ready", True)]
        assert (
            one(
                cluster,
                own_database,
                "SELECT count(*) FROM ingestion_jobs WHERE payload IS NOT NULL",
            )
            == 0
        )

        listed = client.get(f"{API}/subjects/{subject}/documents", headers=headers).json()
        assert {d["status"] for d in listed} == {"ready"}

        app_url = cluster.role_url("app", own_database)  # find_similar under the application role
        hits = retrieve(
            app_url,
            SearchActor(uuid.UUID(str(teacher.id)), UserRole.TEACHER),
            uuid.UUID(subject),
            "rate of change of a function",
        )
        assert hits and hits[0].document_filename == "calculus.txt"

        first = ids[0]
        assert (
            client.delete(
                f"{API}/subjects/{subject}/documents/{first}", headers=headers
            ).status_code
            == 204
        )
        assert (
            one(cluster, own_database, f"SELECT count(*) FROM documents WHERE id = '{first}'") == 0
        )
        assert (
            one(
                cluster,
                own_database,
                f"SELECT count(*) FROM document_chunks WHERE document_id = '{first}'",
            )
            == 0
        )
        assert (
            one(
                cluster,
                own_database,
                f"SELECT count(*) FROM ingestion_jobs WHERE document_id = '{first}'",
            )
            == 0
        )


@linux_only
def test_a_pdf_is_uploaded_processed_with_its_pages_and_retrieved(
    cluster: Cluster, own_database: str
) -> None:
    pdf = pdf_with_pages(
        ["Limits and continuity of functions", "Series converge when their terms shrink"]
    )
    with api(cluster, own_database) as client:
        teacher, headers, subject = teacher_and_subject(cluster, own_database, client)
        response = upload(client, headers, subject, "analysis.pdf", pdf, "application/pdf")
        assert response.status_code == 202
        with built_service(cluster.role_url("worker", own_database), pdf=PDF_LIMITS) as built:
            assert built.service.run_once() is Outcome.READY
        hits = retrieve(
            cluster.role_url("app", own_database),
            SearchActor(uuid.UUID(str(teacher.id)), UserRole.TEACHER),
            uuid.UUID(subject),
            "series converge when their terms shrink",
        )
        assert {hit.page_number for hit in hits} == {1, 2}
        assert (
            one(
                cluster,
                own_database,
                f"SELECT status::text FROM documents WHERE id = '{response.json()['id']}'",
            )
            == "ready"
        )


def test_chat_and_conversations_are_persisted_and_cascade(
    cluster: Cluster, own_database: str
) -> None:
    admin = cluster.admin(own_database)
    teacher = insert_user(admin, "chat.teacher@example.com", UserRole.TEACHER)
    student = insert_user(admin, "chat.student@example.com", UserRole.STUDENT)
    subject = insert_subject(admin, teacher.id)
    insert_enrollment(admin, subject, student.id)
    content = "limits describe the value a function approaches"
    vector = "[" + ",".join(repr(v) for v in FakeEmbedder().embed([content])[0]) + "]"
    document = insert_document_row(admin, uuid.UUID(subject), "limits.pdf", "ready")
    insert_chunk_row(
        admin, document, uuid.UUID(subject), embedding=vector, content=content, page_number=4
    )

    def count(table: str) -> int:
        return int(one(cluster, own_database, f"SELECT count(*) FROM {table}"))

    with api(cluster, own_database) as client:
        headers = bearer(login_token(client, student.email, DEFAULT_PASSWORD))
        consent = client.post(
            f"{API}/users/me/consent", json={"consent_version": CURRENT}, headers=headers
        )
        assert consent.status_code == 200

        first = client.post(
            f"{API}/chat", json={"subject_id": subject, "message": content}, headers=headers
        )
        assert first.status_code == 200, first.text
        conversation = first.json()["conversation_id"]
        assert (count("conversations"), count("messages"), count("message_sources")) == (1, 2, 1)
        assert rows(
            cluster,
            own_database,
            "SELECT document_filename, page_number, rank FROM message_sources",
        ) == [("limits.pdf", 4, 1)]

        again = client.post(
            f"{API}/chat",
            json={"subject_id": subject, "conversation_id": conversation, "message": content},
            headers=headers,
        )
        assert again.status_code == 200, again.text
        assert (count("conversations"), count("messages"), count("message_sources")) == (1, 4, 2)

        listed = client.get(f"{API}/conversations", headers=headers)
        assert [c["id"] for c in listed.json()] == [conversation]
        history = client.get(f"{API}/conversations/{conversation}/messages", headers=headers)
        assert history.status_code == 200 and len(history.json()) == 4
        cited = next(m for m in history.json() if m["sources"])["sources"][0]
        assert cited["document_id"] == str(document) and cited["snippet"] == content

        # DELETE of the conversation alone: the children go through ON DELETE CASCADE, because the
        # application role has no DELETE privilege on messages or message_sources.
        assert (
            client.delete(f"{API}/conversations/{conversation}", headers=headers).status_code == 204
        )
        assert (count("conversations"), count("messages"), count("message_sources")) == (0, 0, 0)

        assert (
            client.post(
                f"{API}/chat", json={"subject_id": subject, "message": content}, headers=headers
            ).status_code
            == 200
        )
        assert count("conversations") == 1

        outsider = insert_user(admin, "chat.outsider@example.com", UserRole.STUDENT)
        outsider_headers = bearer(login_token(client, outsider.email, DEFAULT_PASSWORD))
        client.post(
            f"{API}/users/me/consent", json={"consent_version": CURRENT}, headers=outsider_headers
        )
        not_enrolled = client.post(
            f"{API}/chat",
            json={"subject_id": subject, "message": content},
            headers=outsider_headers,
        )
        unknown = client.post(
            f"{API}/chat",
            json={"subject_id": str(uuid.uuid4()), "message": content},
            headers=outsider_headers,
        )
        assert (not_enrolled.status_code, unknown.status_code) == (403, 404)
        assert count("conversations") == 1

        assert client.delete(f"{API}/users/me/conversations", headers=headers).status_code == 204
        assert (count("conversations"), count("messages"), count("message_sources")) == (0, 0, 0)
