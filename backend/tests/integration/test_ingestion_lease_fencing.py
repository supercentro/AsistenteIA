"""Lease renewal and token fencing at repository level (change 6, task 7.4).

A stale token, a deleted job and an expired lease must be rejected by every fenced write, and
the rejection must write nothing. A renewal is one short statement and leaves no lock or open
transaction behind.
"""

import uuid
from collections.abc import Callable

import pytest
from sqlalchemy import event, text

from app.models.ingestion import DocumentErrorCode
from app.rag.chunker import Chunk
from app.repositories.ingestion_job_repository import ClaimedJob, IngestionJobRepository
from tests.ingestion_support import (
    Scene,
    chunk_count,
    document_state,
    expire_lease,
    insert_pending,
    job_state,
    make_scene,
    session_for,
)
from tests.sql_support import run, scalar, unit_vector

LEASE = 120
DIMENSIONS = 384


def vector(index: int) -> list[float]:
    values = [0.0] * DIMENSIONS
    values[index % DIMENSIONS] = 1.0
    return values


Operation = Callable[[IngestionJobRepository, ClaimedJob, str], bool]

OPERATIONS: dict[str, Operation] = {
    "renew": lambda repo, job, token: repo.renew(job.job_id, token, LEASE),
    "mark_failed": lambda repo, job, token: repo.mark_failed(
        job.job_id, token, DocumentErrorCode.PROCESSING_FAILED
    ),
    "complete": lambda repo, job, token: repo.complete(
        job.job_id, token, [Chunk(index=0, page_number=1, text="hello")], [vector(0)]
    ),
    "erase_payload": lambda repo, job, token: repo.erase_payload(job.job_id, token),
}
OPERATION_PARAMS = [pytest.param(op, id=name) for name, op in OPERATIONS.items()]


@pytest.fixture
def scene(clean_db: str) -> Scene:
    return make_scene(clean_db)


def claim(url: str, lease: int = LEASE) -> ClaimedJob:
    with session_for(url) as session:
        job = IngestionJobRepository(session).claim(lease, 3)
        session.commit()
    assert job is not None
    return job


def attempt(url: str, operation: Operation, job: ClaimedJob, token: str) -> bool:
    with session_for(url) as session:
        accepted = operation(IngestionJobRepository(session), job, token)
        session.commit()
    return accepted


def snapshot(url: str, document: uuid.UUID, job: uuid.UUID) -> tuple[object, ...]:
    """Everything a fenced write could change, as plain values."""
    return (
        document_state(url, document),
        job_state(url, job),
        chunk_count(url, document),
    )


class TestOwnerWrites:
    @pytest.mark.parametrize("operation", OPERATION_PARAMS)
    def test_the_owner_with_a_valid_lease_is_accepted(
        self, scene: Scene, operation: Operation
    ) -> None:
        insert_pending(scene.url, scene.subject)
        job = claim(scene.url)

        assert attempt(scene.url, operation, job, job.token) is True


class TestStaleToken:
    @pytest.mark.parametrize("operation", OPERATION_PARAMS)
    def test_a_worker_that_lost_the_job_to_another_writes_nothing(
        self, scene: Scene, operation: Operation
    ) -> None:
        document, job_id = insert_pending(scene.url, scene.subject)
        stale = claim(scene.url)
        expire_lease(scene.url, job_id)
        current = claim(scene.url)
        before = snapshot(scene.url, document, job_id)

        accepted = attempt(scene.url, operation, stale, stale.token)

        assert accepted is False
        assert snapshot(scene.url, document, job_id) == before
        assert job_state(scene.url, job_id)["locked_by"] == current.token

    @pytest.mark.parametrize("operation", OPERATION_PARAMS)
    def test_a_made_up_token_writes_nothing(self, scene: Scene, operation: Operation) -> None:
        document, job_id = insert_pending(scene.url, scene.subject)
        job = claim(scene.url)
        before = snapshot(scene.url, document, job_id)

        assert attempt(scene.url, operation, job, "not-the-token") is False
        assert attempt(scene.url, operation, job, "") is False
        assert snapshot(scene.url, document, job_id) == before

    @pytest.mark.parametrize("operation", OPERATION_PARAMS)
    def test_a_job_nobody_holds_cannot_be_written_with_any_token(
        self, scene: Scene, operation: Operation
    ) -> None:
        document, job_id = insert_pending(scene.url, scene.subject)
        job = claim(scene.url)
        run(
            scene.url,
            "UPDATE ingestion_jobs SET locked_by = NULL, locked_until = NULL WHERE id = :j",
            j=job_id,
        )
        before = snapshot(scene.url, document, job_id)

        assert attempt(scene.url, operation, job, job.token) is False
        assert snapshot(scene.url, document, job_id) == before


class TestExpiredLease:
    @pytest.mark.parametrize("operation", OPERATION_PARAMS)
    def test_an_expired_lease_rejects_its_own_owner(
        self, scene: Scene, operation: Operation
    ) -> None:
        document, job_id = insert_pending(scene.url, scene.subject)
        job = claim(scene.url)
        expire_lease(scene.url, job_id)
        before = snapshot(scene.url, document, job_id)

        assert attempt(scene.url, operation, job, job.token) is False
        assert snapshot(scene.url, document, job_id) == before

    def test_a_late_renewal_does_not_revive_an_expired_lease(self, scene: Scene) -> None:
        _, job_id = insert_pending(scene.url, scene.subject)
        job = claim(scene.url)
        expire_lease(scene.url, job_id)

        assert attempt(scene.url, OPERATIONS["renew"], job, job.token) is False

        assert job_state(scene.url, job_id)["leased"] is False
        assert claim(scene.url).token != job.token  # another worker can take it

    def test_a_late_renewal_after_another_worker_claimed_changes_nothing(
        self, scene: Scene
    ) -> None:
        _, job_id = insert_pending(scene.url, scene.subject)
        first = claim(scene.url)
        expire_lease(scene.url, job_id)
        second = claim(scene.url)
        before = job_state(scene.url, job_id)

        assert attempt(scene.url, OPERATIONS["renew"], first, first.token) is False

        assert job_state(scene.url, job_id) == before
        assert before["locked_by"] == second.token


class TestDeletedJob:
    @pytest.mark.parametrize("operation", OPERATION_PARAMS)
    def test_a_deleted_document_makes_every_write_a_quiet_no_op(
        self, scene: Scene, operation: Operation
    ) -> None:
        document, job_id = insert_pending(scene.url, scene.subject)
        job = claim(scene.url)
        run(scene.url, "DELETE FROM documents WHERE id = :d", d=document)

        assert attempt(scene.url, operation, job, job.token) is False
        assert document_state(scene.url, document) == {}
        assert job_state(scene.url, job_id) == {}
        assert chunk_count(scene.url, document) == 0

    def test_a_cancelled_worker_cannot_record_a_failure(self, scene: Scene) -> None:
        document, _ = insert_pending(scene.url, scene.subject)
        job = claim(scene.url)
        run(scene.url, "DELETE FROM documents WHERE id = :d", d=document)

        assert attempt(scene.url, OPERATIONS["mark_failed"], job, job.token) is False
        assert document_state(scene.url, document) == {}


class TestTerminalDocuments:
    @pytest.mark.parametrize("status", ["ready", "failed"])
    def test_a_terminal_document_is_never_updated(self, scene: Scene, status: str) -> None:
        document, job_id = insert_pending(scene.url, scene.subject)
        job = claim(scene.url)
        run(
            scene.url,
            "UPDATE documents SET status = CAST(:s AS document_status) WHERE id = :d",
            s=status,
            d=document,
        )
        before = document_state(scene.url, document)

        for name in ("mark_failed", "complete"):
            attempt(scene.url, OPERATIONS[name], job, job.token)

        assert document_state(scene.url, document) == before
        assert chunk_count(scene.url, document) == 0


class TestTokenAndDeadlineIndependence:
    def test_the_owner_keeps_renewing_a_job_longer_than_one_lease(self, scene: Scene) -> None:
        _, job_id = insert_pending(scene.url, scene.subject)
        job = claim(scene.url, lease=3)
        run(
            scene.url,
            "UPDATE ingestion_jobs SET locked_until = clock_timestamp() + interval '1 second' "
            "WHERE id = :j",
            j=job_id,
        )

        assert attempt(scene.url, OPERATIONS["renew"], job, job.token) is True

        remaining = scalar(
            scene.url,
            "SELECT extract(epoch FROM locked_until - clock_timestamp()) FROM ingestion_jobs",
        )
        assert float(remaining) > 100  # type: ignore[arg-type]  # lease of 120 s from now

    def test_a_renewal_does_not_change_the_token_or_the_attempts(self, scene: Scene) -> None:
        _, job_id = insert_pending(scene.url, scene.subject)
        job = claim(scene.url)
        attempt(scene.url, OPERATIONS["renew"], job, job.token)

        state = job_state(scene.url, job_id)

        assert (state["locked_by"], state["attempts"]) == (job.token, 1)


class TestRenewalIsOneShortTransaction:
    def test_a_renewal_is_a_single_statement(self, scene: Scene) -> None:
        insert_pending(scene.url, scene.subject)
        job = claim(scene.url)
        statements: list[str] = []
        with session_for(scene.url) as session:
            event.listen(
                session.get_bind(),
                "before_cursor_execute",
                lambda conn, cursor, statement, params, context, many: statements.append(statement),
            )

            IngestionJobRepository(session).renew(job.job_id, job.token, LEASE)
            session.commit()

        writes = [s for s in statements if s.lstrip().upper().startswith(("UPDATE", "INSERT"))]
        assert len(writes) == 1
        assert "ingestion_jobs" in writes[0]

    def test_a_renewal_leaves_no_lock_and_no_open_transaction(self, scene: Scene) -> None:
        insert_pending(scene.url, scene.subject)
        job = claim(scene.url)
        attempt(scene.url, OPERATIONS["renew"], job, job.token)

        idle = scalar(
            scene.url,
            "SELECT count(*) FROM pg_stat_activity WHERE datname = current_database() "
            "AND pid <> pg_backend_pid() AND state LIKE 'idle in transaction%'",
        )
        locks = scalar(
            scene.url,
            "SELECT count(*) FROM pg_locks l JOIN pg_stat_activity a ON a.pid = l.pid "
            "WHERE a.datname = current_database() AND a.pid <> pg_backend_pid() "
            "AND l.locktype IN ('relation', 'tuple', 'transactionid', 'advisory') "
            "AND l.relation IS DISTINCT FROM 'pg_locks'::regclass",
        )
        assert idle == 0
        assert locks == 0

    def test_a_renewal_only_takes_row_level_locks_before_the_commit(self, scene: Scene) -> None:
        insert_pending(scene.url, scene.subject)
        job = claim(scene.url)
        with session_for(scene.url) as session:
            IngestionJobRepository(session).renew(job.job_id, job.token, LEASE)
            modes = {
                row[0]
                for row in session.execute(
                    text(
                        "SELECT mode FROM pg_locks WHERE pid = pg_backend_pid() "
                        "AND locktype = 'relation' AND granted"
                    )
                )
            }
            session.commit()

        assert modes <= {"AccessShareLock", "RowShareLock", "RowExclusiveLock"}

    def test_other_requests_are_not_blocked_while_a_renewal_waits_for_the_commit(
        self, scene: Scene
    ) -> None:
        document, _ = insert_pending(scene.url, scene.subject)
        job = claim(scene.url)
        with session_for(scene.url) as holder:
            IngestionJobRepository(holder).renew(job.job_id, job.token, LEASE)

            # Reading the document (listing) and the queue is not delayed by the open renewal.
            assert document_state(scene.url, document)["status"] == "processing"
            holder.rollback()


def test_helper_vector_is_a_unit_vector() -> None:
    assert sum(value * value for value in vector(5)) == 1.0
    assert unit_vector(0).startswith("[")
