"""The declarative database privilege matrix (change `database-least-privilege`, task 2.3).

One place states which logical role may do what on which table and column. It is data only: the
grants command (task 4.4) renders it as SQL, the verifier (task 4.5) compares it with the live
catalog, and the tests of `tests/unit/test_db_privileges_*.py` prove that it equals what the
application code needs (derived mechanically by `tests/privilege_inventory.py`).

Rules of the matrix:

* A role has a decision for every table of the model, even if empty (a new table fails a test).
* `KNOWN_COLUMNS` is the snapshot of columns the matrix was reviewed against: a new or removed
  column fails a test until somebody decides who may use it.
* The migrator owns every object and is not listed; `alembic_version` is owned by the migrator
  and has no runtime access, so it is not a model table.
* `select`/`insert`/`update` are column sets. A set equal to every column of the table may be
  rendered as a table-level grant, because a new column fails the test above first.
"""

from dataclasses import dataclass, field
from typing import Final

APP: Final = "app"
WORKER: Final = "worker"
CLI: Final = "cli"
RUNTIME_ROLES: Final = (APP, WORKER, CLI)

KNOWN_COLUMNS: Final[dict[str, frozenset[str]]] = {
    "users": frozenset(
        {
            "id",
            "name",
            "email",
            "password_hash",
            "role",
            "consent_version",
            "consent_accepted_at",
            "created_at",
        }
    ),
    "subjects": frozenset({"id", "name", "description", "teacher_id", "created_at"}),
    "enrollments": frozenset({"id", "subject_id", "student_id", "created_at"}),
    "documents": frozenset(
        {
            "id",
            "subject_id",
            "filename",
            "content_type",
            "size_bytes",
            "status",
            "error_message",
            "error_code",
            "chunks_count",
            "created_at",
        }
    ),
    "document_chunks": frozenset(
        {
            "id",
            "document_id",
            "subject_id",
            "chunk_index",
            "page_number",
            "content",
            "embedding",
            "created_at",
        }
    ),
    "ingestion_jobs": frozenset(
        {
            "id",
            "document_id",
            "payload",
            "attempts",
            "locked_by",
            "locked_until",
            "available_at",
            "created_at",
            "updated_at",
        }
    ),
}


@dataclass(frozen=True)
class TableGrant:
    """What one role may do on one table. Empty means the table is closed to the role."""

    select: frozenset[str] = frozenset()
    insert: frozenset[str] = frozenset()
    update: frozenset[str] = frozenset()
    delete: bool = False
    # A column granted UPDATE only so that SELECT ... FOR UPDATE works (task 2.5 may remove it).
    lock_carrier: str | None = None
    notes: tuple[str, ...] = field(default=(), compare=False)


def _all(table: str) -> frozenset[str]:
    return KNOWN_COLUMNS[table]


def _cols(*names: str) -> frozenset[str]:
    return frozenset(names)


MATRIX: Final[dict[str, dict[str, TableGrant]]] = {
    APP: {
        "users": TableGrant(
            select=_all("users"),
            # `role` is NOT granted: the registration code still inserts it, so registering a
            # user under this role fails until task 8.4 (decision DD-9, option A). The database
            # switch of group 17 must not happen before 8.4. The consent columns are
            # in the list because the ORM sends every column without a server default, as NULL.
            insert=_cols(
                "name", "email", "password_hash", "consent_version", "consent_accepted_at"
            ),
            update=_cols("consent_version", "consent_accepted_at"),
        ),
        "subjects": TableGrant(
            select=_all("subjects"),
            insert=_cols("name", "description", "teacher_id"),
            update=_cols("description"),
            delete=True,
            lock_carrier="description",
        ),
        "enrollments": TableGrant(
            select=_all("enrollments"),
            insert=_cols("subject_id", "student_id"),
            delete=True,
        ),
        "documents": TableGrant(
            select=_all("documents"),
            # error_message and error_code: unset nullable columns are sent as NULL by the ORM.
            insert=_cols(
                "subject_id",
                "filename",
                "content_type",
                "size_bytes",
                "status",
                "error_message",
                "error_code",
            ),  # fmt: skip
            delete=True,
        ),
        "document_chunks": TableGrant(
            select=_cols(
                "id",
                "document_id",
                "subject_id",
                "chunk_index",
                "page_number",
                "content",
                "embedding",
            ),  # fmt: skip
            notes=("read by the retrieval query that the chat endpoint will use",),
        ),
        "ingestion_jobs": TableGrant(
            # Not `locked_by` (the fencing token), `locked_until` or `document_id`.
            select=_cols("id", "payload", "attempts", "available_at", "created_at", "updated_at"),
            # locked_by and locked_until: sent as NULL by the ORM (no server default).
            insert=_cols("document_id", "payload", "locked_by", "locked_until"),
        ),
    },
    WORKER: {
        "users": TableGrant(),
        "subjects": TableGrant(),
        "enrollments": TableGrant(),
        "documents": TableGrant(
            select=_cols("id", "subject_id", "filename", "content_type", "status"),
            update=_cols("status", "chunks_count", "error_code", "error_message"),
        ),
        "document_chunks": TableGrant(
            insert=_cols(
                "document_id", "subject_id", "chunk_index", "page_number", "content", "embedding"
            ),
            select=_cols("id"),  # a one-row bulk insert is INSERT ... RETURNING id
        ),
        "ingestion_jobs": TableGrant(
            select=_cols(
                "id",
                "document_id",
                "payload",
                "attempts",
                "locked_by",
                "locked_until",
                "available_at",
                "created_at",
            ),  # fmt: skip
            update=_cols("payload", "attempts", "locked_by", "locked_until", "updated_at"),
        ),
    },
    CLI: {
        "users": TableGrant(
            select=_all("users"),
            insert=_cols(
                "name", "email", "password_hash", "role", "consent_version", "consent_accepted_at"
            ),
        ),
        "subjects": TableGrant(),
        "enrollments": TableGrant(),
        "documents": TableGrant(),
        "document_chunks": TableGrant(),
        "ingestion_jobs": TableGrant(),
    },
}
