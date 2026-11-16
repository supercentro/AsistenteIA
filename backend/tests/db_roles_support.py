"""Fixtures and helpers for the privilege tests that run UNDER the four roles (group 5).

They need the same disposable cluster as `tests/db_admin_support.py` (see its docstring). The
`prepared_database` fixture builds, once per test module, a database exactly as the design says:
bootstrap as the administrator, Alembic as the migrator, the grants, and a few rows inserted by the
administrator. Tests that only try forbidden statements share it; tests that change data build
their own.
"""

import secrets
from collections.abc import Callable, Iterator
from typing import Any

import psycopg
import pytest

from app.db_admin.bootstrap import bootstrap
from app.db_admin.migrate import migrate
from app.models.document import EMBEDDING_DIMENSIONS
from tests.db_admin_support import TEST_DATABASE_PREFIX, Cluster

TEACHER = "00000000-0000-0000-0000-000000000001"
STUDENT = "00000000-0000-0000-0000-000000000002"
SUBJECT = "00000000-0000-0000-0000-0000000000a1"
DOCUMENT = "00000000-0000-0000-0000-0000000000d1"
VECTOR = f"array_fill(0.1::real, ARRAY[{EMBEDDING_DIMENSIONS}])::vector"


def seed_rows(cluster: Cluster, database: str) -> None:
    """One teacher, one student, one subject with an enrolment, a ready document, a chunk, a job."""
    with cluster.admin_connection(database) as conn:
        conn.execute(
            "INSERT INTO users (id, name, email, password_hash, role) VALUES "
            f"('{TEACHER}', 'T', 't@example.com', 'x', 'teacher'), "
            f"('{STUDENT}', 'S', 's@example.com', 'x', 'student')"
        )
        conn.execute(
            f"INSERT INTO subjects (id, name, teacher_id) VALUES ('{SUBJECT}', 'Subject', '{TEACHER}')"  # noqa: E501
        )
        conn.execute(
            f"INSERT INTO enrollments (subject_id, student_id) VALUES ('{SUBJECT}', '{STUDENT}')"
        )
        conn.execute(
            "INSERT INTO documents (id, subject_id, filename, content_type, size_bytes, status) "
            f"VALUES ('{DOCUMENT}', '{SUBJECT}', 'a.txt', 'text/plain', 3, 'ready')"
        )
        conn.execute(
            "INSERT INTO document_chunks (document_id, subject_id, chunk_index, content, embedding) "  # noqa: E501
            f"VALUES ('{DOCUMENT}', '{SUBJECT}', 0, 'abc', {VECTOR})"
        )
        conn.execute(f"INSERT INTO ingestion_jobs (document_id) VALUES ('{DOCUMENT}')")


def build_prepared_database(cluster: Cluster, database: str) -> None:
    bootstrap(cluster.admin("postgres"), cluster.passwords, database=database, names=cluster.names)
    migrate(cluster.migrator_url(database), names=cluster.names)
    seed_rows(cluster, database)


@pytest.fixture(scope="module")
def prepared_database(cluster: Cluster) -> Iterator[str]:
    database = f"{TEST_DATABASE_PREFIX}{secrets.token_hex(4)}_test"
    with cluster.admin_connection() as conn:
        conn.execute(f'CREATE DATABASE "{database}"')
    try:
        build_prepared_database(cluster, database)
        yield database
    finally:
        with cluster.admin_connection() as conn:
            conn.execute(f'DROP DATABASE IF EXISTS "{database}" WITH (FORCE)')


@pytest.fixture
def own_database(cluster: Cluster, scratch_database: Callable[[], str]) -> str:
    """A prepared database that only this test uses (it may change its rows and privileges)."""
    database = scratch_database()
    build_prepared_database(cluster, database)
    return database


def as_role(cluster: Cluster, logical: str, database: str) -> "psycopg.Connection[Any]":
    """An autocommit session of the role, opened with the password the bootstrap set."""
    return cluster.connect(cluster.role_url(logical, database), application_name=f"tst-{logical}")


def sqlstate_of(conn: "psycopg.Connection[Any]", sql: str) -> str | None:
    """Run `sql`; return the SQLSTATE of its failure, or None if it succeeded."""
    try:
        conn.execute(sql)
    except psycopg.Error as exc:
        return exc.sqlstate
    return None
