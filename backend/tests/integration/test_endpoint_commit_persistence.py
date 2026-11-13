"""Registration, subjects and enrollments commit before they answer (TD-039, change
`database-least-privilege`, 8A.5 to 8A.7).

The API runs under the real application role on a prepared database. A deferred constraint trigger
makes PostgreSQL refuse the transaction at COMMIT (the write itself succeeds), which is what a
serialization failure or a lost connection looks like to the application. Before the fix the
success status had already been sent when that commit ran.
"""

import uuid
from collections.abc import Iterator
from contextlib import contextmanager
from typing import Any

import pytest
from fastapi.testclient import TestClient

from app.models.user import UserRole
from tests.db_admin_support import Cluster
from tests.db_admin_support import cluster as cluster  # noqa: F401  (fixture)
from tests.db_admin_support import scratch_database as scratch_database  # noqa: F401  (fixture)
from tests.db_roles_support import own_database as own_database
from tests.integration.helpers import DEFAULT_PASSWORD, bearer, build_app, insert_user, login_token

FUNCTION = (
    "CREATE OR REPLACE FUNCTION public.tst_refuse_commit() RETURNS trigger LANGUAGE plpgsql AS "
    "$$ BEGIN RAISE EXCEPTION 'commit refused by the test'; END $$"
)


def refuse_commit(cluster: Cluster, database: str, table: str, event: str) -> None:
    with cluster.admin_connection(database) as conn:
        conn.execute(FUNCTION)
        conn.execute(
            f"CREATE CONSTRAINT TRIGGER tst_refuse AFTER {event} ON public.{table} "
            "DEFERRABLE INITIALLY DEFERRED FOR EACH ROW EXECUTE FUNCTION public.tst_refuse_commit()"
        )


def accept_commit(cluster: Cluster, database: str, table: str) -> None:
    with cluster.admin_connection(database) as conn:
        conn.execute(f"DROP TRIGGER tst_refuse ON public.{table}")


def scalar(cluster: Cluster, database: str, sql: str) -> Any:
    with cluster.admin_connection(database) as conn:
        row = conn.execute(sql).fetchone()
    assert row is not None
    return row[0]


@contextmanager
def api_client(cluster: Cluster, database: str) -> Iterator[TestClient]:
    with TestClient(
        build_app(cluster.role_url("app", database)), raise_server_exceptions=False
    ) as client:
        yield client


class World:
    """A prepared database with a teacher, a student and (on demand) a subject."""

    def __init__(self, cluster: Cluster, database: str) -> None:
        self.cluster, self.database = cluster, database
        admin = cluster.admin(database)
        self.teacher = insert_user(admin, "owner.teacher@example.com", UserRole.TEACHER)
        self.student = insert_user(admin, "pupil.student@example.com", UserRole.STUDENT)

    def subject(self, name: str = "Algebra") -> uuid.UUID:
        subject = uuid.uuid4()
        with self.cluster.admin_connection(self.database) as conn:
            conn.execute(
                "INSERT INTO subjects (id, name, teacher_id) "
                f"VALUES ('{subject}', '{name}', '{self.teacher.id}')"
            )
        return subject

    def count(self, table: str, where: str = "true") -> int:
        return int(
            scalar(self.cluster, self.database, f"SELECT count(*) FROM {table} WHERE {where}")
        )

    def teacher_headers(self, client: TestClient) -> dict[str, str]:
        return bearer(login_token(client, self.teacher.email, DEFAULT_PASSWORD))


@pytest.fixture
def world(cluster: Cluster, own_database: str) -> World:
    return World(cluster, own_database)


def assert_standard_500(response: Any, *forbidden: str) -> None:
    assert response.status_code == 500
    assert response.json()["code"] == "INTERNAL_ERROR"
    for text in ("commit refused by the test", "Traceback", *forbidden):
        assert text not in response.text


REGISTRATION = {"name": "Ana", "email": "ana.new@example.com", "password": DEFAULT_PASSWORD}


def test_registration_is_stored_when_it_answers_201_and_is_an_error_when_the_commit_is_refused(
    cluster: Cluster, world: World
) -> None:
    where = "email = 'ana.new@example.com'"
    refuse_commit(cluster, world.database, "users", "INSERT")
    with api_client(cluster, world.database) as client:
        refused = client.post("/api/v1/auth/register", json=REGISTRATION)
        assert_standard_500(refused, "ana.new@example.com", DEFAULT_PASSWORD)
        assert world.count("users", where) == 0  # nothing stored, no partial change

        accept_commit(cluster, world.database, "users")
        accepted = client.post("/api/v1/auth/register", json=REGISTRATION)

    assert accepted.status_code == 201  # the service recovered: no broken session left behind
    assert world.count("users", where) == 1
    assert (
        scalar(cluster, world.database, f"SELECT role::text FROM users WHERE {where}") == "student"
    )


def test_a_duplicate_registration_is_a_409_and_changes_nothing(
    cluster: Cluster, world: World
) -> None:
    with api_client(cluster, world.database) as client:
        assert client.post("/api/v1/auth/register", json=REGISTRATION).status_code == 201
        before = world.count("users")

        duplicate = client.post("/api/v1/auth/register", json=REGISTRATION)

    assert duplicate.status_code == 409
    assert world.count("users") == before


def test_a_subject_is_stored_when_it_answers_201_and_is_an_error_when_the_commit_is_refused(
    cluster: Cluster, world: World
) -> None:
    refuse_commit(cluster, world.database, "subjects", "INSERT")
    with api_client(cluster, world.database) as client:
        headers = world.teacher_headers(client)
        refused = client.post("/api/v1/subjects", json={"name": "Geometry"}, headers=headers)
        assert_standard_500(refused, "Geometry")
        assert world.count("subjects", "name = 'Geometry'") == 0

        accept_commit(cluster, world.database, "subjects")
        accepted = client.post("/api/v1/subjects", json={"name": "Geometry"}, headers=headers)
        duplicate = client.post("/api/v1/subjects", json={"name": "Geometry"}, headers=headers)

    assert accepted.status_code == 201
    assert duplicate.status_code == 409
    assert world.count("subjects", "name = 'Geometry'") == 1


def test_a_subject_deletion_is_stored_when_it_answers_204_and_keeps_the_row_when_refused(
    cluster: Cluster, world: World
) -> None:
    subject = world.subject()
    refuse_commit(cluster, world.database, "subjects", "DELETE")
    with api_client(cluster, world.database) as client:
        headers = world.teacher_headers(client)
        refused = client.delete(f"/api/v1/subjects/{subject}", headers=headers)
        assert_standard_500(refused)
        assert world.count("subjects", f"id = '{subject}'") == 1

        accept_commit(cluster, world.database, "subjects")
        accepted = client.delete(f"/api/v1/subjects/{subject}", headers=headers)
        missing = client.delete(f"/api/v1/subjects/{subject}", headers=headers)

    assert accepted.status_code == 204
    assert world.count("subjects", f"id = '{subject}'") == 0
    assert missing.status_code == 404  # deleting twice is not a second success


def test_an_enrollment_is_stored_when_it_answers_201_and_is_an_error_when_the_commit_is_refused(
    cluster: Cluster, world: World
) -> None:
    subject = world.subject()
    url = f"/api/v1/subjects/{subject}/enrollments"
    body = {"student_email": world.student.email}
    refuse_commit(cluster, world.database, "enrollments", "INSERT")
    with api_client(cluster, world.database) as client:
        headers = world.teacher_headers(client)
        refused = client.post(url, json=body, headers=headers)
        assert_standard_500(refused, world.student.email)
        assert world.count("enrollments", f"subject_id = '{subject}'") == 0

        accept_commit(cluster, world.database, "enrollments")
        accepted = client.post(url, json=body, headers=headers)
        duplicate = client.post(url, json=body, headers=headers)

    assert accepted.status_code == 201
    assert duplicate.status_code == 409
    assert world.count("enrollments", f"subject_id = '{subject}'") == 1  # no partial duplicate


def test_an_enrollment_removal_is_stored_when_it_answers_204_and_keeps_the_row_when_refused(
    cluster: Cluster, world: World
) -> None:
    subject = world.subject()
    with cluster.admin_connection(world.database) as conn:
        conn.execute(
            "INSERT INTO enrollments (subject_id, student_id) "
            f"VALUES ('{subject}', '{world.student.id}')"
        )
    url = f"/api/v1/subjects/{subject}/enrollments/{world.student.id}"
    refuse_commit(cluster, world.database, "enrollments", "DELETE")
    with api_client(cluster, world.database) as client:
        headers = world.teacher_headers(client)
        refused = client.delete(url, headers=headers)
        assert_standard_500(refused)
        assert world.count("enrollments", f"subject_id = '{subject}'") == 1

        accept_commit(cluster, world.database, "enrollments")
        accepted = client.delete(url, headers=headers)
        missing = client.delete(url, headers=headers)

    assert accepted.status_code == 204
    assert world.count("enrollments", f"subject_id = '{subject}'") == 0
    assert missing.status_code == 404
