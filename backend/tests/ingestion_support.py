"""Helpers for the repository tests of the ingestion queue (change 6, group 7).

They build scenes with SQL (so the repositories under test are not used to prepare their own
data), read job and document state back with SQL, and run work from several real sessions at
once. The test database is the guarded `*_test` database, as in every integration test.
"""

import threading
import uuid
from collections.abc import Callable, Iterator
from concurrent.futures import ThreadPoolExecutor
from contextlib import contextmanager
from dataclasses import dataclass

from sqlalchemy.orm import Session

from app.core.database import create_db_engine, create_session_factory
from tests.sql_support import insert_subject, insert_user, run, scalar

PDF_BYTES = b"%PDF-1.7 test payload"


@dataclass(frozen=True)
class Scene:
    url: str
    teacher: uuid.UUID
    subject: uuid.UUID


def make_scene(url: str, label: str = "a") -> Scene:
    teacher = insert_user(url, f"{label}-{uuid.uuid4().hex[:8]}@example.com", "teacher")
    return Scene(url, teacher, insert_subject(url, teacher, f"Subject {label}"))


def add_subject(url: str, teacher: uuid.UUID, name: str) -> uuid.UUID:
    return insert_subject(url, teacher, name)


@contextmanager
def session_for(url: str) -> Iterator[Session]:
    """A short-lived session on its own engine (so threads never share a connection)."""
    engine = create_db_engine(url)
    session = create_session_factory(engine)()
    try:
        yield session
    finally:
        session.rollback()
        session.close()
        engine.dispose()


def insert_pending(
    url: str,
    subject: uuid.UUID,
    payload: bytes | None = PDF_BYTES,
    status: str = "pending",
    filename: str = "file.pdf",
    content_type: str = "application/pdf",
) -> tuple[uuid.UUID, uuid.UUID]:
    """A document with its job (document id, job id), inserted by SQL."""
    document, job = uuid.uuid4(), uuid.uuid4()
    run(
        url,
        "INSERT INTO documents (id, subject_id, filename, content_type, size_bytes, status) "
        "VALUES (:d, :s, :f, :ct, :n, CAST(:status AS document_status))",
        d=document,
        s=subject,
        f=filename,
        ct=content_type,
        n=len(payload or b""),
        status=status,
    )
    run(
        url,
        "INSERT INTO ingestion_jobs (id, document_id, payload) VALUES (:j, :d, :p)",
        j=job,
        d=document,
        p=payload,
    )
    return document, job


def expire_lease(url: str, job: uuid.UUID, seconds: int = 5) -> None:
    run(
        url,
        "UPDATE ingestion_jobs SET locked_until = clock_timestamp() - make_interval(secs => :s) "
        "WHERE id = :j",
        s=seconds,
        j=job,
    )


def age_job(url: str, job: uuid.UUID, hours: int) -> None:
    run(
        url,
        "UPDATE ingestion_jobs SET created_at = now() - make_interval(hours => :h) WHERE id = :j",
        h=hours,
        j=job,
    )


def document_state(url: str, document: uuid.UUID) -> dict[str, object]:
    """status, error_code, error_message and chunks_count of a document (empty if deleted)."""
    from sqlalchemy import text

    from tests.db_support import guarded_engine

    with guarded_engine(url) as engine, engine.connect() as conn:
        row = conn.execute(
            text(
                "SELECT status::text AS status, error_code, error_message, chunks_count "
                "FROM documents WHERE id = :d"
            ),
            {"d": document},
        ).first()
    return dict(row._mapping) if row else {}


def job_state(url: str, job: uuid.UUID) -> dict[str, object]:
    """Lease, attempts and payload presence of a job (empty if deleted)."""
    from sqlalchemy import text

    from tests.db_support import guarded_engine

    with guarded_engine(url) as engine, engine.connect() as conn:
        row = conn.execute(
            text(
                "SELECT locked_by, locked_until, attempts, payload IS NOT NULL AS has_payload, "
                "(locked_until IS NOT NULL AND locked_until > clock_timestamp()) AS leased "
                "FROM ingestion_jobs WHERE id = :j"
            ),
            {"j": job},
        ).first()
    return dict(row._mapping) if row else {}


def chunk_count(url: str, document: uuid.UUID) -> int:
    value = scalar(url, "SELECT count(*) FROM document_chunks WHERE document_id = :d", d=document)
    assert isinstance(value, int)
    return value


def run_together[T](count: int, work: Callable[[int], T]) -> list[T | BaseException]:
    """Run `work(i)` in `count` threads released at the same instant; keep results or errors."""
    barrier = threading.Barrier(count)

    def task(index: int) -> T | BaseException:
        barrier.wait(timeout=30)
        try:
            return work(index)
        except BaseException as error:  # noqa: BLE001 - the tests inspect every failure
            return error

    with ThreadPoolExecutor(max_workers=count) as pool:
        return list(pool.map(task, range(count)))
