"""Fixtures and helpers for the tests of the database administration commands (group 4).

They need a **disposable PostgreSQL cluster** (a pgvector 0.8.7 / PostgreSQL 15 container with a
throwaway superuser, or the CI service container): the bootstrap closes `PUBLIC` on every database
of the cluster it runs against. Two environment variables select it and both are required:

- `TEST_ADMIN_DATABASE_URL`: administrator URL of that cluster (the guard of `tests/db_support.py`
  also needs `TEST_DATABASE_URL` and `DATABASE_URL`);
- `TEST_CLUSTER_IS_DISPOSABLE=true`: the explicit statement that the cluster may be altered.

Every role carries the reserved prefix `tstrole_` and every database the prefix `tstdb_` and the
suffix `_test`; leftovers of both are removed before and after the session. Nothing here touches
`asistenteia` or `asistenteia_test`.
"""

import os
import secrets
from collections.abc import Callable, Iterator
from dataclasses import dataclass
from typing import Any, cast

import psycopg
import pytest
from sqlalchemy.engine import URL, make_url

from app.db_admin.names import RoleNames, RolePasswords
from tests.db_support import (
    MissingTestDatabaseError,
    require_test_admin_database_url,
    require_test_database_url,
)
from tests.role_support import TEST_ROLE_PREFIX, RoleConnection, sweep_test_roles

TEST_DATABASE_PREFIX = "tstdb_"
DISPOSABLE_FLAG = "TEST_CLUSTER_IS_DISPOSABLE"


@dataclass
class Cluster:
    admin_url: str
    names: RoleNames
    passwords: RolePasswords

    def url(self, role: str, password: str, database: str) -> str:
        base = make_url(self.admin_url)
        return URL.create(
            "postgresql+psycopg",
            username=role,
            password=password,
            host=base.host,
            port=base.port,
            database=database,
        ).render_as_string(hide_password=False)

    def admin(self, database: str = "postgres") -> str:
        return make_url(self.admin_url).set(database=database).render_as_string(hide_password=False)

    def migrator_url(self, database: str) -> str:
        return self.url(self.names.migrator, self.passwords.migrator, database)

    def role_url(self, logical: str, database: str) -> str:
        return self.url(getattr(self.names, logical), getattr(self.passwords, logical), database)

    def connect(
        self, url: str, *, autocommit: bool = True, application_name: str = "tst-session"
    ) -> "psycopg.Connection[Any]":
        parts = make_url(url)
        return psycopg.connect(
            host=parts.host,
            port=parts.port,
            user=parts.username,
            password=parts.password,
            dbname=parts.database,
            autocommit=autocommit,
            connect_timeout=10,
            application_name=application_name,
        )

    def admin_connection(self, database: str = "postgres") -> "psycopg.Connection[Any]":
        return self.connect(self.admin(database))


def _drop_leftovers(cluster: Cluster) -> None:
    with cluster.admin_connection() as conn:
        rows = conn.execute(
            "SELECT datname FROM pg_catalog.pg_database WHERE datname LIKE %s",
            (TEST_DATABASE_PREFIX.replace("_", r"\_") + "%",),
        ).fetchall()
        for (name,) in rows:
            assert name.startswith(TEST_DATABASE_PREFIX) and name.endswith("_test"), name
            conn.execute(f'DROP DATABASE IF EXISTS "{name}" WITH (FORCE)')
        sweep_test_roles(cast(RoleConnection, conn))


ALWAYS_PRESENT = {"postgres", "template0", "template1"}


def assert_cluster_is_disposable(cluster: Cluster) -> None:
    """Refuse a cluster that holds anything but our own scratch databases and roles.

    The bootstrap closes PUBLIC on every database of the cluster it runs against, so the only thing
    between these tests and a real server must not be a flag alone: a cluster with the application
    database or the real roles in it is refused before any statement that changes something.
    """
    with cluster.admin_connection() as conn:
        databases = {str(r[0]) for r in conn.execute("SELECT datname FROM pg_catalog.pg_database")}
        real_roles = [
            str(r[0])
            for r in conn.execute(
                "SELECT rolname FROM pg_catalog.pg_roles WHERE rolname LIKE 'asistente%%'"
            )
        ]
    foreign = sorted(
        d
        for d in databases - ALWAYS_PRESENT
        if not (d.startswith(TEST_DATABASE_PREFIX) and d.endswith("_test"))
    )
    if foreign or real_roles:
        raise MissingTestDatabaseError(
            "this cluster is not disposable: it holds "
            f"{len(foreign)} database(s) and {len(real_roles)} role(s) that are not test scratch "
            "objects; refusing to run the cluster-wide bootstrap tests against it"
        )


@pytest.fixture(scope="session")
def cluster() -> Iterator[Cluster]:
    if os.environ.get(DISPOSABLE_FLAG, "").lower() != "true":
        raise MissingTestDatabaseError(
            f"{DISPOSABLE_FLAG}=true is required: the bootstrap closes PUBLIC on every database "
            "of the cluster, so these tests run only against a disposable cluster"
        )
    require_test_database_url()  # the guard: *_test name, not the application database
    admin_url = require_test_admin_database_url()
    value = Cluster(
        admin_url=admin_url,
        names=RoleNames.with_prefix(TEST_ROLE_PREFIX),
        passwords=RolePasswords(
            migrator=secrets.token_urlsafe(24),
            app=secrets.token_urlsafe(24),
            worker=secrets.token_urlsafe(24),
            cli=secrets.token_urlsafe(24),
        ),
    )
    assert_cluster_is_disposable(value)
    _drop_leftovers(value)
    try:
        yield value
    finally:
        _drop_leftovers(value)


@pytest.fixture
def scratch_database(cluster: Cluster) -> Iterator[Callable[[], str]]:
    """Factory of empty databases `tstdb_<random>_test`; dropped when the test ends."""
    created: list[str] = []

    def make() -> str:
        name = f"{TEST_DATABASE_PREFIX}{secrets.token_hex(4)}_test"
        with cluster.admin_connection() as conn:
            conn.execute(f'CREATE DATABASE "{name}"')
        created.append(name)
        return name

    yield make
    with cluster.admin_connection() as conn:
        for name in created:
            conn.execute(f'DROP DATABASE IF EXISTS "{name}" WITH (FORCE)')


# --- a database as it exists today: created and migrated by the administrator, with rows --------

TABLE_ORDER = (
    "users",
    "subjects",
    "enrollments",
    "documents",
    "document_chunks",
    "ingestion_jobs",
)


def build_legacy_database(cluster: Cluster, database: str) -> dict[str, int]:
    """The shape of the development database: the administrator owns everything; rows exist."""
    from alembic import command

    from app.models.document import EMBEDDING_DIMENSIONS
    from tests.db_support import alembic_config

    with cluster.admin_connection(database) as conn:
        conn.execute("CREATE EXTENSION IF NOT EXISTS vector")
    command.upgrade(alembic_config(cluster.admin(database)), "head")
    with cluster.admin_connection(database) as conn:
        conn.execute(
            "INSERT INTO users (id, name, email, password_hash, role) VALUES "
            "('00000000-0000-0000-0000-000000000001', 'T', 't@example.com', 'x', 'teacher'), "
            "('00000000-0000-0000-0000-000000000002', 'S', 's@example.com', 'x', 'student')"
        )
        conn.execute(
            "INSERT INTO subjects (id, name, teacher_id) VALUES "
            "('00000000-0000-0000-0000-0000000000a1', 'Subject', "
            "'00000000-0000-0000-0000-000000000001')"
        )
        conn.execute(
            "INSERT INTO enrollments (subject_id, student_id) VALUES "
            "('00000000-0000-0000-0000-0000000000a1', '00000000-0000-0000-0000-000000000002')"
        )
        conn.execute(
            "INSERT INTO documents (id, subject_id, filename, content_type, size_bytes, status) "
            "VALUES ('00000000-0000-0000-0000-0000000000d1', "
            "'00000000-0000-0000-0000-0000000000a1', 'a.txt', 'text/plain', 3, 'ready')"
        )
        conn.execute(
            "INSERT INTO document_chunks (document_id, subject_id, chunk_index, content, embedding) "  # noqa: E501
            "VALUES ('00000000-0000-0000-0000-0000000000d1', "
            "'00000000-0000-0000-0000-0000000000a1', 0, 'abc', "
            f"array_fill(0.1::real, ARRAY[{EMBEDDING_DIMENSIONS}])::vector)"
        )
        conn.execute(
            "INSERT INTO ingestion_jobs (document_id) VALUES "
            "('00000000-0000-0000-0000-0000000000d1')"
        )
    return row_counts(cluster, database)


def row_counts(cluster: Cluster, database: str) -> dict[str, int]:
    with cluster.admin_connection(database) as conn:
        counts: dict[str, int] = {}
        for table in TABLE_ORDER:
            row = conn.execute(f'SELECT count(*) FROM "{table}"').fetchone()
            assert row is not None
            counts[table] = int(row[0])
        return counts


def owners(cluster: Cluster, database: str) -> dict[str, str]:
    """Owner of every table, index and type of schema public (extension members excluded)."""
    with cluster.admin_connection(database) as conn:
        rows = conn.execute(
            "SELECT c.relname, r.rolname FROM pg_catalog.pg_class c "
            "JOIN pg_catalog.pg_roles r ON r.oid = c.relowner "
            "JOIN pg_catalog.pg_namespace n ON n.oid = c.relnamespace "
            "WHERE n.nspname = 'public' AND c.relkind IN ('r', 'i', 'S') "
            "AND NOT EXISTS (SELECT 1 FROM pg_catalog.pg_depend d WHERE d.objid = c.oid "
            "AND d.deptype = 'e') "
            "UNION ALL SELECT t.typname, r.rolname FROM pg_catalog.pg_type t "
            "JOIN pg_catalog.pg_roles r ON r.oid = t.typowner "
            "JOIN pg_catalog.pg_namespace n ON n.oid = t.typnamespace "
            "WHERE n.nspname = 'public' AND t.typtype = 'e'"
        ).fetchall()
        return {str(name): str(owner) for name, owner in rows}


def catalog_fingerprint(cluster: Cluster, database: str) -> str:
    """Hash of tables, columns, indexes and constraints, blind to owners and privileges."""
    with cluster.admin_connection(database) as conn:
        row = conn.execute(
            "SELECT md5(string_agg(x, '|' ORDER BY x)) FROM ("
            "SELECT 'c:' || c.relname || '.' || a.attname || ':' || "
            "pg_catalog.format_type(a.atttypid, a.atttypmod) AS x "
            "FROM pg_catalog.pg_class c JOIN pg_catalog.pg_attribute a ON a.attrelid = c.oid "
            "JOIN pg_catalog.pg_namespace n ON n.oid = c.relnamespace "
            "WHERE n.nspname = 'public' AND c.relkind = 'r' AND a.attnum > 0 "
            "AND NOT a.attisdropped "
            "UNION ALL SELECT 'i:' || indexname || ':' || indexdef FROM pg_catalog.pg_indexes "
            "WHERE schemaname = 'public' "
            "UNION ALL SELECT 'k:' || conname || ':' || pg_catalog.pg_get_constraintdef(oid) "
            "FROM pg_catalog.pg_constraint WHERE connamespace = 'public'::regnamespace) s"
        ).fetchone()
        assert row is not None
        return str(row[0])
