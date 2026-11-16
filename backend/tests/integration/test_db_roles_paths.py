"""The real repositories run under the real roles (change `database-least-privilege`, task 5.4).

The inventory of group 2 derived the privileges from the code and left five SQLAlchemy behaviours
as assumptions; this file proves them against PostgreSQL by running the repositories of the API and
of the worker with the role URLs, and then removes the one grant the worker needs only because of
`RETURNING` to show that a one-chunk document fails (the mutation the task asks for).
"""

import uuid
from datetime import UTC, datetime

import pytest
from sqlalchemy.exc import ProgrammingError
from sqlalchemy.orm import Session

from app.core.database import create_db_engine
from app.db_admin.grants import apply_grants
from app.models.subject import Subject
from app.models.user import User
from app.rag.chunker import Chunk
from app.repositories.document_repository import AdmissionLimits, DocumentRepository
from app.repositories.enrollment_repository import EnrollmentRepository
from app.repositories.ingestion_job_repository import IngestionJobRepository
from app.repositories.subject_repository import SubjectRepository
from app.repositories.user_repository import UserRepository
from tests.db_admin_support import Cluster
from tests.db_admin_support import cluster as cluster  # noqa: F401  (fixture)
from tests.db_admin_support import scratch_database as scratch_database  # noqa: F401  (fixture)
from tests.db_roles_support import (
    DOCUMENT,
    STUDENT,
    SUBJECT,
    TEACHER,
    VECTOR,
)
from tests.db_roles_support import (
    own_database as own_database,
)

LIMITS = AdmissionLimits(max_documents=50, queue_max=100, pending_bytes_max=10_000_000)
UNIT = [1.0] + [0.0] * 383


def session_for(cluster: Cluster, logical: str, database: str) -> Session:
    engine = create_db_engine(cluster.role_url(logical, database))
    return Session(engine)


def pending_document(cluster: Cluster, database: str, name: str) -> uuid.UUID:
    """A pending document with its job and bytes, as an upload leaves it (inserted by the admin)."""
    document = uuid.uuid4()
    with cluster.admin_connection(database) as conn:
        conn.execute(
            "INSERT INTO documents (id, subject_id, filename, content_type, size_bytes, status) "
            f"VALUES ('{document}', '{SUBJECT}', '{name}', 'text/plain', 3, 'pending')"
        )
        conn.execute(
            "INSERT INTO ingestion_jobs (document_id, payload) "
            f"VALUES ('{document}', decode('616263', 'hex'))"
        )
    return document


def document_state(
    cluster: Cluster, database: str, document: uuid.UUID
) -> tuple[str, int, int, bool]:
    with cluster.admin_connection(database) as conn:
        row = conn.execute(
            "SELECT d.status::text, d.chunks_count, (SELECT count(*) FROM document_chunks c "
            f"WHERE c.document_id = d.id), j.payload IS NULL FROM documents d "
            f"JOIN ingestion_jobs j ON j.document_id = d.id WHERE d.id = '{document}'"
        ).fetchone()
    assert row is not None
    return str(row[0]), int(row[1]), int(row[2]), bool(row[3])


# noqa: E501

# --- the API under the application role ---


def test_the_upload_the_subject_and_the_consent_paths_work_under_the_application_role(
    cluster: Cluster, own_database: str
) -> None:
    with session_for(cluster, "app", own_database) as session:
        documents = DocumentRepository(session)

        created = documents.add_with_job(
            teacher_id=uuid.UUID(TEACHER),
            subject_id=uuid.UUID(SUBJECT),
            filename="upload.txt",
            content_type="text/plain",
            payload=b"hello",
            limits=LIMITS,
        )  # SELECT ... FOR UPDATE, advisory lock, ORM INSERTs with RETURNING of server defaults
        session.commit()
        assert created.id and created.created_at and created.chunks_count == 0

        listed = documents.list_for_teacher(uuid.UUID(SUBJECT), uuid.UUID(TEACHER))
        assert listed is not None and {d.filename for d in listed} >= {"upload.txt"}

        subjects = SubjectRepository(session)
        added = subjects.add(
            Subject(name="New subject", description=None, teacher_id=uuid.UUID(TEACHER))
        )
        session.commit()
        assert added.id and subjects.list_for_teacher(uuid.UUID(TEACHER))

        enrollments = EnrollmentRepository(session)
        assert enrollments.delete_for_teacher_subject(
            uuid.UUID(SUBJECT), uuid.UUID(TEACHER), uuid.UUID(STUDENT)
        )
        session.commit()
        assert (
            enrollments.add(uuid.UUID(SUBJECT), uuid.UUID(TEACHER), uuid.UUID(STUDENT)) is not None
        )
        session.commit()

        user = UserRepository(session).get_by_email("s@example.com")
        assert user is not None
        user.consent_version = "2026-10-v1"
        user.consent_accepted_at = datetime.now(UTC)
        session.commit()  # UPDATE users SET consent_* WHERE id; persisted, read back below

    with cluster.admin_connection(own_database) as conn:
        consent = conn.execute(
            f"SELECT consent_version FROM users WHERE id = '{STUDENT}'"
        ).fetchone()
    assert consent == ("2026-10-v1",)


def test_deleting_a_document_and_a_subject_cascades_without_delete_on_the_children(
    cluster: Cluster, own_database: str
) -> None:
    other = pending_document(cluster, own_database, "doomed.txt")
    with session_for(cluster, "app", own_database) as session:
        assert DocumentRepository(session).delete_for_teacher(
            uuid.UUID(SUBJECT), other, uuid.UUID(TEACHER)
        )
        session.commit()
    with cluster.admin_connection(own_database) as conn:
        assert conn.execute(
            f"SELECT count(*) FROM ingestion_jobs WHERE document_id = '{other}'"
        ).fetchone() == (0,)

    with session_for(cluster, "app", own_database) as session:
        assert SubjectRepository(session).delete_for_teacher(uuid.UUID(SUBJECT), uuid.UUID(TEACHER))
        session.commit()
    with cluster.admin_connection(own_database) as conn:
        for table in ("documents", "document_chunks", "ingestion_jobs", "enrollments"):
            assert conn.execute(f"SELECT count(*) FROM {table}").fetchone() == (0,), table


def test_registration_stores_a_student_under_the_application_role(
    cluster: Cluster, own_database: str
) -> None:
    # The code no longer inserts `role`: the server default of migration 0006 supplies `student`.
    user = User(name="X", email="x@example.com", password_hash="h")
    with session_for(cluster, "app", own_database) as session:
        created = UserRepository(session).add(user)
        assert created.role.value == "student"
        session.commit()
    with cluster.admin_connection(own_database) as conn:
        assert conn.execute(
            "SELECT role::text FROM users WHERE email = 'x@example.com'"
        ).fetchone() == ("student",)


# noqa: E501

UNGRANTED = [
    ("app", "UPDATE users SET role = 'teacher'"),
    ("app", "UPDATE users SET email = 'forged@example.com'"),
    ("app", "UPDATE users SET password_hash = 'forged'"),
    ("app", "UPDATE subjects SET teacher_id = teacher_id"),
    ("app", "UPDATE subjects SET name = 'renamed'"),
    ("app", "UPDATE documents SET status = 'ready'"),
    ("app", "UPDATE ingestion_jobs SET attempts = 0"),
    ("app", "SELECT locked_by FROM ingestion_jobs"),
    ("app", "SELECT locked_until FROM ingestion_jobs"),
    ("app", "SELECT attempts FROM ingestion_jobs"),
    (
        "app",
        "INSERT INTO users (name, email, password_hash, consent_version) "
        "VALUES ('c', 'c@example.com', 'h', '2026-10-v1')",
    ),
    (
        "app",
        "INSERT INTO users (name, email, password_hash, consent_accepted_at) "
        "VALUES ('c', 'c2@example.com', 'h', now())",
    ),
    (
        "cli",
        "INSERT INTO users (name, email, password_hash, role, consent_version) "
        "VALUES ('c', 'c3@example.com', 'h', 'teacher', '2026-10-v1')",
    ),
    (
        "app",
        "INSERT INTO documents "
        "(subject_id, filename, content_type, size_bytes, status, error_code) "
        f"VALUES ('{SUBJECT}', 'f', 'text/plain', 1, 'pending', 'PROCESSING_FAILED')",
    ),
    (
        "app",
        "INSERT INTO documents "
        "(subject_id, filename, content_type, size_bytes, status, error_message) "
        f"VALUES ('{SUBJECT}', 'f', 'text/plain', 1, 'pending', 'forged')",
    ),
    (
        "app",
        "INSERT INTO ingestion_jobs (document_id, payload, locked_by) "
        "VALUES (gen_random_uuid(), 'x', 't')",
    ),
    (
        "app",
        "INSERT INTO ingestion_jobs (document_id, payload, locked_until) "
        "VALUES (gen_random_uuid(), 'x', now())",
    ),
    ("app", "SELECT created_at FROM document_chunks"),
    ("app", "DELETE FROM document_chunks"),
    ("app", "DELETE FROM ingestion_jobs"),
    ("app", "DELETE FROM users"),
    (
        "app",
        "INSERT INTO users (name, email, password_hash, role) VALUES ('a', 'a@b.co', 'h', 'teacher')",  # noqa: E501
    ),
    ("worker", "SELECT content FROM document_chunks"),
    ("worker", "SELECT embedding FROM document_chunks"),
    ("worker", "UPDATE documents SET filename = 'x'"),
    ("worker", "UPDATE documents SET subject_id = subject_id"),
    ("worker", "UPDATE ingestion_jobs SET document_id = document_id"),
    ("worker", "SELECT email FROM users"),
    ("worker", "SELECT name FROM subjects"),
    ("worker", "SELECT student_id FROM enrollments"),
    ("worker", "DELETE FROM documents"),
    ("worker", "DELETE FROM document_chunks"),
    ("worker", "SELECT version_num FROM alembic_version"),
    ("cli", "SELECT name FROM subjects"),
    ("cli", "UPDATE users SET role = 'teacher'"),
    ("cli", "DELETE FROM users"),
    ("cli", "SELECT id FROM documents"),
]


@pytest.mark.parametrize(
    ("logical", "sql"), UNGRANTED, ids=[f"{r}: {s[:48]}" for r, s in UNGRANTED]
)
def test_columns_and_operations_that_are_not_granted_are_refused_and_change_nothing(
    cluster: Cluster, own_database: str, logical: str, sql: str
) -> None:
    from tests.db_roles_support import as_role, sqlstate_of

    before = counts(cluster, own_database)
    with as_role(cluster, logical, own_database) as conn:
        assert sqlstate_of(conn, sql) == "42501", sql
    assert counts(cluster, own_database) == before
    with cluster.admin_connection(own_database) as conn:
        assert conn.execute(
            "SELECT role::text FROM users WHERE id = %s", (TEACHER,)
        ).fetchone() == ("teacher",)
        assert conn.execute(
            "SELECT role::text FROM users WHERE id = %s", (STUDENT,)
        ).fetchone() == ("student",)


def counts(cluster: Cluster, database: str) -> dict[str, int]:
    from tests.db_admin_support import row_counts

    return row_counts(cluster, database)


# --- the worker under the worker role ---


def run_job(cluster: Cluster, database: str, chunks: int) -> tuple[uuid.UUID, bool]:
    document = pending_document(cluster, database, f"job{chunks}.txt")
    with session_for(cluster, "worker", database) as session:
        repo = IngestionJobRepository(session)
        job = repo.claim(lease_seconds=120, max_attempts=3)
        session.commit()
        assert job is not None and job.document_id == document
        assert repo.renew(job.job_id, job.token, 120)
        session.commit()
        done = repo.complete(
            job.job_id,
            job.token,
            [Chunk(index=i, page_number=1, text=f"text {i}") for i in range(chunks)],
            [UNIT for _ in range(chunks)],
        )
        session.commit()
    return document, done


@pytest.mark.parametrize("chunks", [1, 2, 5])
def test_the_worker_completes_one_and_many_chunk_documents(
    cluster: Cluster, own_database: str, chunks: int
) -> None:
    document, done = run_job(cluster, own_database, chunks)

    assert done is True
    assert document_state(cluster, own_database, document) == ("ready", chunks, chunks, True)


def test_the_worker_fails_a_document_and_sweeps_under_its_role(
    cluster: Cluster, own_database: str
) -> None:
    document = pending_document(cluster, own_database, "bad.txt")
    from app.models.ingestion import DocumentErrorCode

    with session_for(cluster, "worker", own_database) as session:
        repo = IngestionJobRepository(session)
        job = repo.claim(lease_seconds=120, max_attempts=3)
        session.commit()
        assert job is not None
        assert repo.mark_failed(job.job_id, job.token, DocumentErrorCode.PROCESSING_FAILED)
        session.commit()

    status, count, chunks, erased = document_state(cluster, own_database, document)
    assert (status, count, chunks, erased) == ("failed", 0, 0, True)


def test_the_sweep_writes_under_the_worker_role_on_each_of_its_three_branches(
    cluster: Cluster, own_database: str
) -> None:
    interrupted, expired, stale = uuid.uuid4(), uuid.uuid4(), uuid.uuid4()
    with cluster.admin_connection(own_database) as conn:
        for document, status in ((interrupted, "pending"), (expired, "pending"), (stale, "ready")):
            conn.execute(
                "INSERT INTO documents (id, subject_id, filename, content_type, size_bytes, status) "  # noqa: E501
                f"VALUES ('{document}', '{SUBJECT}', '{document}.txt', 'text/plain', 3, '{status}')"
            )
        # no attempts left (interrupted), older than the maximum age (expired), bytes left behind
        conn.execute(
            "INSERT INTO ingestion_jobs (document_id, payload, attempts) "
            f"VALUES ('{interrupted}', decode('616263', 'hex'), 3)"
        )
        conn.execute(
            "INSERT INTO ingestion_jobs (document_id, payload, created_at) "
            f"VALUES ('{expired}', decode('616263', 'hex'), now() - interval '30 hours')"
        )
        conn.execute(
            f"INSERT INTO ingestion_jobs (document_id, payload) VALUES ('{stale}', decode('616263', 'hex'))"  # noqa: E501
        )

    with session_for(cluster, "worker", own_database) as session:
        result = IngestionJobRepository(session).sweep(max_attempts=3, max_age_hours=24)
        session.commit()

    assert (result.interrupted, result.expired, result.erased) == (1, 1, 1)
    assert document_state(cluster, own_database, interrupted) == ("failed", 0, 0, True)
    assert document_state(cluster, own_database, expired) == ("failed", 0, 0, True)
    assert document_state(cluster, own_database, stale) == ("ready", 0, 0, True)


def test_a_chunk_cannot_carry_a_subject_other_than_the_one_of_its_document(
    cluster: Cluster, own_database: str
) -> None:
    from sqlalchemy import insert
    from sqlalchemy.exc import IntegrityError

    from app.models.document import DocumentChunk

    other_subject = uuid.uuid4()
    with cluster.admin_connection(own_database) as conn:
        conn.execute(
            f"INSERT INTO subjects (id, name, teacher_id) VALUES ('{other_subject}', 'Other', '{TEACHER}')"  # noqa: E501
        )

    with session_for(cluster, "worker", own_database) as session:
        with pytest.raises(IntegrityError):  # the composite key (document_id, subject_id)
            session.execute(
                insert(DocumentChunk),
                [
                    {
                        "document_id": uuid.UUID(DOCUMENT),
                        "subject_id": other_subject,
                        "chunk_index": 9,
                        "page_number": None,
                        "content": "cross-subject",
                        "embedding": UNIT,
                    }
                ],
            )
        session.rollback()


def test_without_select_on_the_chunk_key_a_one_chunk_document_fails_the_mutation(
    cluster: Cluster, own_database: str
) -> None:
    # The mutation of task 5.4: take away the `SELECT (id)` that exists only because a one-row bulk
    # insert returns the generated key (hypothesis H4), and the one-chunk document cannot finish.
    with cluster.admin_connection(own_database) as conn:
        conn.execute(
            f'REVOKE SELECT (id) ON TABLE "public"."document_chunks" FROM "{cluster.names.worker}"'
        )
    document = pending_document(cluster, own_database, "one.txt")

    with session_for(cluster, "worker", own_database) as session:
        repo = IngestionJobRepository(session)
        job = repo.claim(lease_seconds=120, max_attempts=3)
        session.commit()
        assert job is not None
        with pytest.raises(ProgrammingError) as caught:
            repo.complete(job.job_id, job.token, [Chunk(0, 1, "only")], [UNIT])
        assert getattr(caught.value.orig, "sqlstate", None) == "42501"
        session.rollback()
    assert document_state(cluster, own_database, document)[2] == 0  # nothing was written

    apply_grants(cluster.migrator_url(own_database), names=cluster.names)  # restore the matrix
    again, done = run_job(cluster, own_database, 1)
    assert done and document_state(cluster, own_database, again)[0] == "ready"


def test_the_worker_can_poison_chunks_of_an_existing_document_a_documented_residual(
    cluster: Cluster, own_database: str
) -> None:
    # R-chunks: a compromised worker can add chunks to any existing document (spike B-06).
    with session_for(cluster, "worker", own_database) as session:
        from sqlalchemy import insert

        from app.models.document import DocumentChunk

        session.execute(
            insert(DocumentChunk),
            [
                {
                    "document_id": uuid.UUID(DOCUMENT),
                    "subject_id": uuid.UUID(SUBJECT),
                    "chunk_index": 7,
                    "page_number": None,
                    "content": "planted",
                    "embedding": UNIT,
                }
            ],
        )
        session.commit()
    with cluster.admin_connection(own_database) as conn:
        assert conn.execute(
            "SELECT count(*) FROM document_chunks WHERE content = 'planted'"
        ).fetchone() == (1,)
        assert VECTOR  # the seeded chunk uses the same vector literal


def test_a_chunk_of_a_document_that_does_not_exist_is_rejected(
    cluster: Cluster, own_database: str
) -> None:
    from sqlalchemy import insert
    from sqlalchemy.exc import IntegrityError

    from app.models.document import DocumentChunk

    with session_for(cluster, "worker", own_database) as session:
        with pytest.raises(IntegrityError):
            session.execute(
                insert(DocumentChunk),
                [
                    {
                        "document_id": uuid.uuid4(),
                        "subject_id": uuid.UUID(SUBJECT),
                        "chunk_index": 0,
                        "page_number": None,
                        "content": "orphan",
                        "embedding": UNIT,
                    }
                ],
            )
        session.rollback()


def test_the_worker_erases_a_payload_and_clears_the_lease_under_its_role(
    cluster: Cluster, own_database: str
) -> None:
    document = pending_document(cluster, own_database, "erase.txt")
    with session_for(cluster, "worker", own_database) as session:
        repo = IngestionJobRepository(session)
        job = repo.claim(lease_seconds=120, max_attempts=3)
        session.commit()
        assert job is not None and job.document_id == document
        assert repo.erase_payload(job.job_id, job.token) is True
        session.commit()
        assert repo.erase_payload(job.job_id, "another-token") is False  # fenced
        session.rollback()

    with cluster.admin_connection(own_database) as conn:
        assert conn.execute(
            "SELECT payload IS NULL, locked_by IS NULL, locked_until IS NULL FROM ingestion_jobs "
            f"WHERE document_id = '{document}'"
        ).fetchone() == (True, True, True)
