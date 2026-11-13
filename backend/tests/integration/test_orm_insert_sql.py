"""The SQL the ORM emits for the objects the API creates (change `database-least-privilege`, 8A).

SQLAlchemy sends every column that has no default of any kind as NULL, which forced six extra
`INSERT` grants (group 5, analysis in group 6). The columns are now fetched server values
(`FetchedValue()`), so they must be absent from the emitted `INSERT` and from its `RETURNING`.
The statements are captured on a real connection of the application role of a prepared database,
for one object and for a batch, and the persisted rows are read back with the administrator.
"""

import re
import uuid
from collections.abc import Iterator
from contextlib import contextmanager
from typing import Any

import pytest
from sqlalchemy import event
from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session

from app.core.database import create_db_engine
from app.models.document import Document, DocumentStatus
from app.models.ingestion import IngestionJob
from app.models.user import User, UserRole
from tests.db_admin_support import Cluster
from tests.db_admin_support import cluster as cluster  # noqa: F401  (fixture)
from tests.db_admin_support import scratch_database as scratch_database  # noqa: F401  (fixture)
from tests.db_roles_support import SUBJECT
from tests.db_roles_support import own_database as own_database

JOB_COLUMNS = {"document_id", "payload"}
USER_COLUMNS = {"name", "email", "password_hash"}
DOCUMENT_COLUMNS = {"subject_id", "filename", "content_type", "size_bytes", "status"}


@contextmanager
def app_session(cluster: Cluster, database: str) -> Iterator[tuple[Session, list[str]]]:
    """A session of the application role plus the INSERT statements it emitted, in order."""
    engine: Engine = create_db_engine(cluster.role_url("app", database))
    statements: list[str] = []

    @event.listens_for(engine, "before_cursor_execute")
    def capture(_conn: Any, _cursor: Any, statement: str, *_rest: Any) -> None:
        if statement.lstrip().upper().startswith("INSERT"):
            statements.append(statement)

    try:
        with Session(engine) as session:
            yield session, statements
    finally:
        engine.dispose()


def inserted_columns(statement: str) -> set[str]:
    match = re.search(r"INSERT INTO \w+ \(([^)]*)\)", statement)
    assert match, statement
    return {name.strip() for name in match.group(1).split(",")}


def returning_columns(statement: str) -> set[str]:
    match = re.search(r"RETURNING (.*)$", statement.replace("\n", " "))
    return set() if match is None else {part.strip() for part in match.group(1).split(",")}


def pending_documents(cluster: Cluster, database: str, count: int) -> list[uuid.UUID]:
    """Documents without a job, inserted by the administrator."""
    ids = [uuid.uuid4() for _ in range(count)]
    with cluster.admin_connection(database) as conn:
        for number, document in enumerate(ids):
            conn.execute(
                "INSERT INTO documents "
                "(id, subject_id, filename, content_type, size_bytes, status) "
                f"VALUES ('{document}', '{SUBJECT}', 'f{number}.txt', 'text/plain', 3, 'pending')"
            )
    return ids


def stored(cluster: Cluster, database: str, sql: str) -> list[tuple[Any, ...]]:
    with cluster.admin_connection(database) as conn:
        return [tuple(row) for row in conn.execute(sql).fetchall()]


# ---- pair 1: ingestion_jobs.locked_by and locked_until (the fencing token) -------------------


def test_a_job_insert_omits_the_fencing_token_and_asks_nothing_back_about_it(
    cluster: Cluster, own_database: str
) -> None:
    (document,) = pending_documents(cluster, own_database, 1)
    with app_session(cluster, own_database) as (session, statements):
        session.add(IngestionJob(document_id=document, payload=b"abc"))
        session.flush()
        session.commit()

    (statement,) = statements
    assert inserted_columns(statement) == JOB_COLUMNS
    assert "locked_" not in statement  # neither in the column list nor in RETURNING
    assert returning_columns(statement) == {"ingestion_jobs.id"}
    assert stored(
        cluster,
        own_database,
        f"SELECT locked_by, locked_until FROM ingestion_jobs WHERE document_id = '{document}'",
    ) == [(None, None)]


def test_a_batch_of_jobs_keeps_the_same_columns_and_stores_every_row(
    cluster: Cluster, own_database: str
) -> None:
    documents = pending_documents(cluster, own_database, 3)
    with app_session(cluster, own_database) as (session, statements):
        session.add_all([IngestionJob(document_id=d, payload=b"x" * 3) for d in documents])
        session.flush()
        session.commit()

    assert statements
    for statement in statements:
        assert inserted_columns(statement) == JOB_COLUMNS
        assert "locked_" not in statement
    listed = ", ".join(f"'{d}'" for d in documents)
    rows = stored(
        cluster,
        own_database,
        "SELECT locked_by, locked_until, attempts FROM ingestion_jobs "
        f"WHERE document_id IN ({listed})",
    )
    assert rows == [(None, None, 0)] * 3


def test_a_job_object_does_not_expose_the_token_without_a_read_privilege(
    cluster: Cluster, own_database: str
) -> None:
    (document,) = pending_documents(cluster, own_database, 1)
    with app_session(cluster, own_database) as (session, _statements):
        job = IngestionJob(document_id=document, payload=b"abc")
        session.add(job)
        session.flush()
        assert job.id is not None  # the key comes back with the insert
        with pytest.raises(Exception, match="permission denied"):
            _ = job.locked_by  # expired after the flush: the SELECT is refused, as intended
        session.rollback()


# ---- pair 2: documents.error_message and error_code -------------------------------------------


def new_document(number: int) -> Document:
    return Document(
        subject_id=uuid.UUID(SUBJECT),
        filename=f"n{number}.txt",
        content_type="text/plain",
        size_bytes=3,
        status=DocumentStatus.PENDING,
    )


def test_a_document_insert_omits_the_error_columns(cluster: Cluster, own_database: str) -> None:
    with app_session(cluster, own_database) as (session, statements):
        document = new_document(0)
        session.add(document)
        session.flush()
        session.commit()
        assert document.error_message is None and document.error_code is None

    (statement,) = statements
    assert inserted_columns(statement) == DOCUMENT_COLUMNS
    assert "error_" not in statement.split("RETURNING")[0]  # the columns list and the values
    assert stored(
        cluster,
        own_database,
        f"SELECT error_message, error_code, status::text FROM documents WHERE id = '{document.id}'",
    ) == [(None, None, "pending")]


def test_a_batch_of_documents_keeps_the_same_columns_and_stores_every_row(
    cluster: Cluster, own_database: str
) -> None:
    with app_session(cluster, own_database) as (session, statements):
        batch = [new_document(number) for number in range(3)]
        session.add_all(batch)
        session.flush()
        session.commit()
        ids = [d.id for d in batch]

    assert statements
    for statement in statements:
        assert inserted_columns(statement) == DOCUMENT_COLUMNS
    listed = ", ".join(f"'{i}'" for i in ids)
    rows = stored(
        cluster,
        own_database,
        f"SELECT error_message, error_code, chunks_count FROM documents WHERE id IN ({listed})",
    )
    assert rows == [(None, None, 0)] * 3


# ---- pair 3: users.consent_version and consent_accepted_at ------------------------------------


def new_user(number: int) -> User:
    return User(name=f"U{number}", email=f"u{number}@example.com", password_hash="hash")


def test_a_registration_insert_omits_the_consent_and_the_role(
    cluster: Cluster, own_database: str
) -> None:
    with app_session(cluster, own_database) as (session, statements):
        user = new_user(0)
        session.add(user)
        session.flush()
        session.commit()
        assert user.consent_version is None and user.consent_accepted_at is None
        assert user.role is UserRole.STUDENT

    (statement,) = statements
    assert inserted_columns(statement) == USER_COLUMNS  # no consent columns, no role
    assert stored(
        cluster,
        own_database,
        "SELECT consent_version, consent_accepted_at, role::text FROM users "
        "WHERE email = 'u0@example.com'",
    ) == [(None, None, "student")]


def test_a_batch_of_users_keeps_the_same_columns_and_stores_every_row(
    cluster: Cluster, own_database: str
) -> None:
    with app_session(cluster, own_database) as (session, statements):
        session.add_all([new_user(number) for number in range(3)])
        session.flush()
        session.commit()

    assert statements
    for statement in statements:
        assert inserted_columns(statement) == USER_COLUMNS
    rows = stored(
        cluster,
        own_database,
        "SELECT consent_version, consent_accepted_at, role::text FROM users "
        "WHERE email LIKE 'u_@example.com'",
    )
    assert rows == [(None, None, "student")] * 3


def test_the_cli_role_inserts_a_teacher_without_the_consent_columns(
    cluster: Cluster, own_database: str
) -> None:
    engine: Engine = create_db_engine(cluster.role_url("cli", own_database))
    statements: list[str] = []

    @event.listens_for(engine, "before_cursor_execute")
    def capture(_conn: Any, _cursor: Any, statement: str, *_rest: Any) -> None:
        if statement.lstrip().upper().startswith("INSERT"):
            statements.append(statement)

    try:
        with Session(engine) as session:
            session.add(
                User(name="T", email="cli.t@example.com", password_hash="h", role=UserRole.TEACHER)
            )
            session.flush()
            session.commit()
    finally:
        engine.dispose()

    (statement,) = statements
    assert inserted_columns(statement) == USER_COLUMNS | {"role"}
    assert stored(
        cluster, own_database, "SELECT role::text FROM users WHERE email = 'cli.t@example.com'"
    ) == [("teacher",)]
