"""Integrity of `ingestion_jobs` and `documents.error_code` (group 3, task 3.3).

Rows are inserted by SQL so the constraints themselves are exercised, as in change 5. The ORM
mapping is checked at the end.
"""

import uuid
from dataclasses import dataclass

import pytest
from psycopg import errors as pg_errors
from sqlalchemy.exc import DataError, DBAPIError, IntegrityError
from sqlalchemy.orm import Session

from app.core.database import Base
from app.models.document import Document, DocumentStatus
from app.models.ingestion import IngestionJob
from app.models.user import UserRole
from tests.integration.helpers import MakeUser
from tests.sql_support import (
    count,
    insert_document,
    insert_subject,
    insert_user,
    run,
    scalar,
)


@dataclass(frozen=True)
class Scene:
    url: str
    teacher: uuid.UUID
    subject: uuid.UUID
    document: uuid.UUID


@pytest.fixture
def scene(clean_db: str) -> Scene:
    teacher = insert_user(clean_db, "job-teacher@example.com", "teacher")
    subject = insert_subject(clean_db, teacher)
    document = insert_document(clean_db, subject, "pending.pdf", "pending")
    return Scene(clean_db, teacher, subject, document)


def insert_job(url: str, document: uuid.UUID, payload: bytes | None = b"%PDF-1.7") -> None:
    run(
        url,
        "INSERT INTO ingestion_jobs (document_id, payload) VALUES (:id, :payload)",
        id=document,
        payload=payload,
    )


def violation(exc: pytest.ExceptionInfo[DBAPIError]) -> type[BaseException]:
    assert exc.value.orig is not None
    return type(exc.value.orig)


def test_deleting_a_document_removes_its_job_and_bytes(scene: Scene) -> None:
    insert_job(scene.url, scene.document, b"x" * 2048)

    run(scene.url, "DELETE FROM documents WHERE id = :id", id=scene.document)

    assert count(scene.url, "ingestion_jobs") == 0


def test_deleting_a_subject_removes_the_jobs_of_all_its_documents(scene: Scene) -> None:
    second = insert_document(scene.url, scene.subject, "second.pdf", "processing")
    insert_job(scene.url, scene.document)
    insert_job(scene.url, second)
    other_subject = insert_subject(scene.url, scene.teacher, "Physics")
    other_document = insert_document(scene.url, other_subject, "other.pdf", "pending")
    insert_job(scene.url, other_document)

    run(scene.url, "DELETE FROM subjects WHERE id = :id", id=scene.subject)

    assert count(scene.url, "ingestion_jobs") == 1
    assert count(scene.url, "ingestion_jobs", "document_id = :id", id=other_document) == 1


def test_a_teacher_with_documents_cannot_be_deleted_and_nothing_is_lost(scene: Scene) -> None:
    """The subject owner keeps RESTRICT (unchanged since change 3): no partial erasure."""
    insert_job(scene.url, scene.document)

    with pytest.raises(IntegrityError) as exc:
        run(scene.url, "DELETE FROM users WHERE id = :id", id=scene.teacher)

    assert violation(exc) is pg_errors.ForeignKeyViolation
    assert count(scene.url, "documents") == 1
    assert count(scene.url, "ingestion_jobs") == 1


def test_a_second_job_for_the_same_document_is_rejected(scene: Scene) -> None:
    insert_job(scene.url, scene.document)

    with pytest.raises(IntegrityError) as exc:
        insert_job(scene.url, scene.document)

    assert violation(exc) is pg_errors.UniqueViolation
    assert count(scene.url, "ingestion_jobs") == 1


def test_a_job_needs_an_existing_document(scene: Scene) -> None:
    with pytest.raises(IntegrityError) as exc:
        insert_job(scene.url, uuid.uuid4())

    assert violation(exc) is pg_errors.ForeignKeyViolation


@pytest.mark.parametrize("status", ["pending", "processing", "ready"])
def test_an_error_code_on_a_document_that_has_not_failed_is_rejected(
    scene: Scene, status: str
) -> None:
    document = insert_document(scene.url, scene.subject, f"{status}.pdf", status)

    with pytest.raises(IntegrityError) as exc:
        run(
            scene.url,
            "UPDATE documents SET error_code = 'CORRUPT_FILE' WHERE id = :id",
            id=document,
        )

    assert violation(exc) is pg_errors.CheckViolation
    assert scalar(scene.url, "SELECT error_code FROM documents WHERE id = :id", id=document) is None


def test_an_error_code_cannot_be_set_in_the_same_statement_as_a_non_failed_status(
    scene: Scene,
) -> None:
    with pytest.raises(IntegrityError) as exc:
        run(
            scene.url,
            "INSERT INTO documents (subject_id, filename, content_type, size_bytes, status, "
            "error_code) VALUES (:subject, 'x.pdf', 'application/pdf', 1, "
            "CAST('ready' AS document_status), 'CORRUPT_FILE')",
            subject=scene.subject,
        )

    assert violation(exc) is pg_errors.CheckViolation


def test_a_failed_document_may_carry_a_code_or_none(scene: Scene) -> None:
    with_code = insert_document(scene.url, scene.subject, "coded.pdf", "failed")
    without_code = insert_document(scene.url, scene.subject, "legacy.pdf", "failed")

    run(
        scene.url,
        "UPDATE documents SET error_code = 'ENCRYPTED_PDF' WHERE id = :id",
        id=with_code,
    )

    assert scalar(scene.url, "SELECT error_code FROM documents WHERE id = :id", id=with_code) == (
        "ENCRYPTED_PDF"
    )
    # Existing fixtures insert failed documents without a code; the reverse rule is the service's.
    assert (
        scalar(scene.url, "SELECT error_code FROM documents WHERE id = :id", id=without_code)
        is None
    )


def test_a_code_longer_than_the_column_is_rejected(scene: Scene) -> None:
    failed = insert_document(scene.url, scene.subject, "long.pdf", "failed")

    with pytest.raises(DataError) as exc:
        run(
            scene.url,
            "UPDATE documents SET error_code = :code WHERE id = :id",
            code="X" * 41,
            id=failed,
        )

    assert violation(exc) is pg_errors.StringDataRightTruncation


def test_a_lease_needs_both_owner_and_expiry(scene: Scene) -> None:
    insert_job(scene.url, scene.document)

    for assignment in ("locked_by = 'token'", "locked_until = now()"):
        with pytest.raises(IntegrityError) as exc:
            run(
                scene.url,
                "UPDATE ingestion_jobs SET " + assignment + " WHERE document_id = :id",  # noqa: S608
                id=scene.document,
            )
        assert violation(exc) is pg_errors.CheckViolation


def test_a_complete_lease_is_accepted_and_can_be_cleared(scene: Scene) -> None:
    insert_job(scene.url, scene.document)

    run(
        scene.url,
        "UPDATE ingestion_jobs SET locked_by = 'token', "
        "locked_until = now() + interval '2 minutes' WHERE document_id = :id",
        id=scene.document,
    )
    assert count(scene.url, "ingestion_jobs", "locked_by = 'token'") == 1
    run(
        scene.url,
        "UPDATE ingestion_jobs SET locked_by = NULL, locked_until = NULL WHERE document_id = :id",
        id=scene.document,
    )
    assert count(scene.url, "ingestion_jobs", "locked_by IS NULL AND locked_until IS NULL") == 1


def test_the_lease_owner_fits_a_random_claim_token(scene: Scene) -> None:
    insert_job(scene.url, scene.document)
    token = uuid.uuid4().hex + uuid.uuid4().hex  # 64 characters

    run(
        scene.url,
        "UPDATE ingestion_jobs SET locked_by = :token, locked_until = now() "
        "WHERE document_id = :id",
        token=token,
        id=scene.document,
    )

    assert scalar(scene.url, "SELECT length(locked_by) FROM ingestion_jobs") == 64
    with pytest.raises(DataError) as exc:
        run(
            scene.url,
            "UPDATE ingestion_jobs SET locked_by = :token WHERE document_id = :id",
            token=token + "0",
            id=scene.document,
        )
    assert violation(exc) is pg_errors.StringDataRightTruncation


def test_negative_attempts_are_rejected(scene: Scene) -> None:
    insert_job(scene.url, scene.document)

    with pytest.raises(IntegrityError) as exc:
        run(
            scene.url,
            "UPDATE ingestion_jobs SET attempts = -1 WHERE document_id = :id",
            id=scene.document,
        )

    assert violation(exc) is pg_errors.CheckViolation


def test_the_payload_round_trips_and_can_be_cleared(scene: Scene) -> None:
    payload = bytes(range(256)) * 40
    insert_job(scene.url, scene.document, payload)
    stored = scalar(scene.url, "SELECT payload FROM ingestion_jobs")
    assert isinstance(stored, bytes | memoryview)
    assert bytes(stored) == payload

    run(
        scene.url,
        "UPDATE ingestion_jobs SET payload = NULL WHERE document_id = :id",
        id=scene.document,
    )

    assert scalar(scene.url, "SELECT payload FROM ingestion_jobs") is None
    assert count(scene.url, "documents", "id = :id", id=scene.document) == 1


def test_a_cleared_job_is_not_in_the_claim_index_predicate(scene: Scene) -> None:
    insert_job(scene.url, scene.document, None)
    insert_job(scene.url, insert_document(scene.url, scene.subject, "b.pdf", "pending"))

    assert count(scene.url, "ingestion_jobs", "payload IS NOT NULL") == 1


def test_models_are_registered_and_map_the_new_columns() -> None:
    assert "ingestion_jobs" in Base.metadata.tables
    assert set(Base.metadata.tables["ingestion_jobs"].columns.keys()) == {
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
    assert "error_code" in Base.metadata.tables["documents"].columns


def test_the_orm_inserts_a_job_and_an_error_code(db_session: Session, make_user: MakeUser) -> None:
    from app.models.subject import Subject

    teacher = make_user("orm-job-teacher@example.com", UserRole.TEACHER)
    subject = Subject(name="Algebra", teacher_id=teacher.id)
    db_session.add(subject)
    db_session.flush()
    document = Document(
        subject_id=subject.id, filename="a.pdf", content_type="application/pdf", size_bytes=3
    )
    db_session.add(document)
    db_session.flush()
    job = IngestionJob(document_id=document.id, payload=b"abc")
    db_session.add(job)
    db_session.flush()
    db_session.refresh(job)

    assert job.attempts == 0 and job.locked_by is None and job.locked_until is None
    assert job.payload == b"abc"
    assert job.created_at is not None and job.updated_at is not None
    assert document.error_code is None

    document.status = DocumentStatus.FAILED
    document.error_code = "CORRUPT_FILE"
    db_session.flush()
    assert document.error_code == "CORRUPT_FILE"

    document.status = DocumentStatus.READY
    with pytest.raises(IntegrityError):
        db_session.flush()
    db_session.rollback()
