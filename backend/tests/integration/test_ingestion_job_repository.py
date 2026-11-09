"""`IngestionJobRepository`: claim, attempts, restart behaviour and sweep (change 6, task 7.2)."""

import time
import uuid

import pytest
from sqlalchemy import event, text

from app.models.ingestion import DOCUMENT_ERROR_MESSAGES, DocumentErrorCode
from app.repositories.ingestion_job_repository import (
    ClaimedJob,
    IngestionJobRepository,
    SweepResult,
)
from tests.ingestion_support import (
    PDF_BYTES,
    Scene,
    age_job,
    document_state,
    expire_lease,
    insert_pending,
    job_state,
    make_scene,
    run_together,
    session_for,
)
from tests.sql_support import run

LEASE = 120
MAX_ATTEMPTS = 3
MAX_AGE_HOURS = 24


@pytest.fixture
def scene(clean_db: str) -> Scene:
    return make_scene(clean_db)


def claim(url: str, lease: int = LEASE, attempts: int = MAX_ATTEMPTS) -> ClaimedJob | None:
    with session_for(url) as session:
        job = IngestionJobRepository(session).claim(lease, attempts)
        session.commit()
    return job


def sweep(url: str) -> SweepResult:
    with session_for(url) as session:
        result = IngestionJobRepository(session).sweep(MAX_ATTEMPTS, MAX_AGE_HOURS)
        session.commit()
    return result


class TestClaim:
    def test_a_pending_job_is_claimed_with_a_lease_and_a_fresh_token(self, scene: Scene) -> None:
        document, job_id = insert_pending(scene.url, scene.subject, b"%PDF-bytes")

        job = claim(scene.url)

        assert job is not None
        assert (job.job_id, job.document_id, job.subject_id) == (job_id, document, scene.subject)
        assert job.payload == b"%PDF-bytes"
        assert job.attempts == 1
        assert (job.filename, job.content_type) == ("file.pdf", "application/pdf")
        assert 20 <= len(job.token) <= 64
        state = job_state(scene.url, job_id)
        assert state["locked_by"] == job.token
        assert state["leased"] is True
        assert state["attempts"] == 1
        assert document_state(scene.url, document)["status"] == "processing"

    def test_the_lease_lasts_as_long_as_requested(self, scene: Scene) -> None:
        _, job_id = insert_pending(scene.url, scene.subject)

        claim(scene.url, lease=100)

        remaining = run_scalar(
            scene.url,
            "SELECT extract(epoch FROM locked_until - clock_timestamp()) FROM ingestion_jobs",
        )
        assert 90 < float(remaining) <= 100  # type: ignore[arg-type]

    def test_there_is_nothing_to_claim_without_jobs(self, scene: Scene) -> None:
        assert claim(scene.url) is None

    def test_the_oldest_job_goes_first(self, scene: Scene) -> None:
        _, newer = insert_pending(scene.url, scene.subject)
        _, older = insert_pending(scene.url, scene.subject)
        run(
            scene.url,
            "UPDATE ingestion_jobs SET available_at = now() - interval '1 hour' WHERE id = :j",
            j=older,
        )

        first = claim(scene.url)
        second = claim(scene.url)

        assert first is not None and second is not None
        assert (first.job_id, second.job_id) == (older, newer)

    def test_a_job_that_is_not_yet_available_is_not_claimed(self, scene: Scene) -> None:
        _, job_id = insert_pending(scene.url, scene.subject)
        run(
            scene.url,
            "UPDATE ingestion_jobs SET available_at = now() + interval '1 hour' WHERE id = :j",
            j=job_id,
        )

        assert claim(scene.url) is None

    @pytest.mark.parametrize("status", ["ready", "failed"])
    def test_a_job_of_a_terminal_document_is_never_claimed(self, scene: Scene, status: str) -> None:
        insert_pending(scene.url, scene.subject, status=status)

        assert claim(scene.url) is None

    def test_a_job_without_bytes_is_never_claimed(self, scene: Scene) -> None:
        insert_pending(scene.url, scene.subject, payload=None)

        assert claim(scene.url) is None

    def test_two_sessions_looking_for_one_job_claim_it_once(self, scene: Scene) -> None:
        insert_pending(scene.url, scene.subject)

        outcomes = run_together(2, lambda _: claim(scene.url))

        claimed = [o for o in outcomes if isinstance(o, ClaimedJob)]
        assert len(claimed) == 1
        assert not [o for o in outcomes if isinstance(o, BaseException)]

    def test_many_workers_and_few_jobs_never_share_a_job(self, scene: Scene) -> None:
        jobs = {insert_pending(scene.url, scene.subject)[1] for _ in range(4)}

        outcomes = run_together(10, lambda _: claim(scene.url))

        claimed = [o for o in outcomes if isinstance(o, ClaimedJob)]
        assert len(claimed) == 4
        assert {c.job_id for c in claimed} == jobs
        assert len({c.token for c in claimed}) == 4

    def test_a_job_with_a_valid_lease_is_not_claimed_by_a_third_worker(self, scene: Scene) -> None:
        _, job_id = insert_pending(scene.url, scene.subject)
        first = claim(scene.url)
        expire_lease(scene.url, job_id)
        second = claim(scene.url)

        third = claim(scene.url)

        assert first is not None and second is not None and third is None
        assert second.token != first.token
        assert job_state(scene.url, job_id)["locked_by"] == second.token

    def test_a_job_whose_lease_expired_is_claimed_again_and_counts_an_attempt(
        self, scene: Scene
    ) -> None:
        _, job_id = insert_pending(scene.url, scene.subject)
        claim(scene.url)
        expire_lease(scene.url, job_id)

        again = claim(scene.url)

        assert again is not None and again.attempts == 2
        assert job_state(scene.url, job_id)["attempts"] == 2

    def test_a_job_whose_attempts_are_exhausted_is_not_claimed(self, scene: Scene) -> None:
        _, job_id = insert_pending(scene.url, scene.subject)
        for _ in range(MAX_ATTEMPTS):
            assert claim(scene.url) is not None
            expire_lease(scene.url, job_id)

        assert claim(scene.url) is None
        assert job_state(scene.url, job_id)["attempts"] == MAX_ATTEMPTS

    def test_claiming_does_not_change_a_document_that_became_terminal(self, scene: Scene) -> None:
        document, job_id = insert_pending(scene.url, scene.subject)
        run(scene.url, "UPDATE documents SET status = 'ready' WHERE id = :d", d=document)

        assert claim(scene.url) is None
        assert document_state(scene.url, document)["status"] == "ready"

    def test_an_orphaned_job_without_bytes_does_not_hide_a_valid_one(self, scene: Scene) -> None:
        _, orphan = insert_pending(scene.url, scene.subject, payload=None, status="processing")
        _, valid = insert_pending(scene.url, scene.subject)
        run(
            scene.url,
            "UPDATE ingestion_jobs SET available_at = now() - interval '1 hour' WHERE id = :j",
            j=orphan,
        )

        job = claim(scene.url)

        assert job is not None and job.job_id == valid

    def test_claim_does_not_wait_for_a_document_locked_by_another_session(
        self, scene: Scene
    ) -> None:
        first_document, first_job = insert_pending(scene.url, scene.subject)
        _, second_job = insert_pending(scene.url, scene.subject)
        run(
            scene.url,
            "UPDATE ingestion_jobs SET available_at = now() - interval '1 hour' WHERE id = :j",
            j=first_job,
        )
        with session_for(scene.url) as holder:
            holder.execute(
                text("SELECT id FROM documents WHERE id = :d FOR UPDATE"), {"d": first_document}
            )
            started = time.monotonic()

            job = claim(scene.url)

            elapsed = time.monotonic() - started
            holder.rollback()
        assert job is not None and job.job_id == second_job
        assert elapsed < 5

    def test_jobs_come_out_in_the_order_of_their_availability(self, scene: Scene) -> None:
        jobs = [insert_pending(scene.url, scene.subject)[1] for _ in range(6)]
        shuffled = [3, 0, 5, 1, 4, 2]
        for position, job_id in zip(shuffled, jobs, strict=True):
            run(
                scene.url,
                "UPDATE ingestion_jobs SET available_at = now() - make_interval(hours => :h) "
                "WHERE id = :j",
                h=10 - position,
                j=job_id,
            )
        expected = [job for _, job in sorted(zip(shuffled, jobs, strict=True))]

        claimed = [claim(scene.url) for _ in range(6)]

        assert [job.job_id for job in claimed if job is not None] == expected

    def test_an_exhausted_job_does_not_hide_a_claimable_one(self, scene: Scene) -> None:
        _, exhausted = insert_pending(scene.url, scene.subject)
        _, valid = insert_pending(scene.url, scene.subject)
        run(
            scene.url,
            "UPDATE ingestion_jobs SET attempts = 3, "
            "available_at = now() - interval '1 hour' WHERE id = :j",
            j=exhausted,
        )

        job = claim(scene.url)

        assert job is not None and job.job_id == valid

    @pytest.mark.parametrize("case", ["leased", "exhausted"])
    def test_the_update_refuses_a_job_that_stopped_being_claimable_after_it_was_chosen(
        self, scene: Scene, case: str
    ) -> None:
        _, job_id = insert_pending(scene.url, scene.subject)
        if case == "leased":
            first = claim(scene.url)
            assert first is not None
            holder_token = first.token
        else:
            run(scene.url, "UPDATE ingestion_jobs SET attempts = 3 WHERE id = :j", j=job_id)
            holder_token = None
        before = job_state(scene.url, job_id)

        def relax(conn, cursor, statement, parameters, context, executemany):  # type: ignore[no-untyped-def]
            if statement.lstrip().startswith("SELECT d.id AS document_id"):
                statement = statement.replace(
                    "AND (j.locked_until IS NULL OR j.locked_until <= clock_timestamp())", ""
                ).replace("AND j.attempts < %(max_attempts)s", "")
            return statement, parameters

        with session_for(scene.url) as session:
            event.listen(session.get_bind(), "before_cursor_execute", relax, retval=True)
            job = IngestionJobRepository(session).claim(LEASE, MAX_ATTEMPTS)
            session.commit()

        assert job is None  # the candidate was offered to the update, which refused it
        after = job_state(scene.url, job_id)
        assert after["attempts"] == before["attempts"]
        assert after["locked_by"] == holder_token


def run_scalar(url: str, sql: str) -> object:
    from tests.sql_support import scalar

    return scalar(url, sql)


class TestRestartBehaviour:
    def test_a_killed_worker_leaves_a_job_another_worker_finishes(self, scene: Scene) -> None:
        document, job_id = insert_pending(scene.url, scene.subject)
        crashed = claim(scene.url)
        assert crashed is not None  # the process dies here: nothing else is written
        expire_lease(scene.url, job_id)

        rescuer = claim(scene.url)

        assert rescuer is not None and rescuer.document_id == document
        assert rescuer.payload == crashed.payload
        assert document_state(scene.url, document)["status"] == "processing"

    def test_after_the_last_attempt_the_sweep_fails_the_document_as_interrupted(
        self, scene: Scene
    ) -> None:
        document, job_id = insert_pending(scene.url, scene.subject)
        for _ in range(MAX_ATTEMPTS):
            claim(scene.url)
            expire_lease(scene.url, job_id)

        result = sweep(scene.url)

        assert result.interrupted == 1
        state = document_state(scene.url, document)
        assert state["status"] == "failed"
        assert state["error_code"] == "PROCESSING_INTERRUPTED"
        assert (
            state["error_message"]
            == DOCUMENT_ERROR_MESSAGES[DocumentErrorCode.PROCESSING_INTERRUPTED]
        )
        assert job_state(scene.url, job_id)["has_payload"] is False

    def test_a_job_with_attempts_left_is_not_failed_by_the_sweep(self, scene: Scene) -> None:
        document, job_id = insert_pending(scene.url, scene.subject)
        for _ in range(MAX_ATTEMPTS - 1):
            claim(scene.url)
            expire_lease(scene.url, job_id)

        assert sweep(scene.url).interrupted == 0
        assert document_state(scene.url, document)["status"] == "processing"
        assert claim(scene.url) is not None

    def test_the_last_attempt_with_a_valid_lease_is_left_alone(self, scene: Scene) -> None:
        document, job_id = insert_pending(scene.url, scene.subject)
        for _ in range(MAX_ATTEMPTS - 1):
            claim(scene.url)
            expire_lease(scene.url, job_id)
        assert claim(scene.url) is not None  # third attempt, lease valid

        assert sweep(scene.url).interrupted == 0
        assert document_state(scene.url, document)["status"] == "processing"
        assert job_state(scene.url, job_id)["has_payload"] is True

    def test_a_restart_with_pending_documents_loses_nothing(self, scene: Scene) -> None:
        jobs = [insert_pending(scene.url, scene.subject)[1] for _ in range(3)]

        sweep(scene.url)  # the sweep that runs at worker start
        claimed = {claim(scene.url).job_id for _ in range(3)}  # type: ignore[union-attr]

        assert claimed == set(jobs)


class TestSweep:
    def test_a_job_older_than_the_maximum_age_expires(self, scene: Scene) -> None:
        document, job_id = insert_pending(scene.url, scene.subject)
        age_job(scene.url, job_id, MAX_AGE_HOURS + 1)

        result = sweep(scene.url)

        assert result.expired == 1
        state = document_state(scene.url, document)
        assert (state["status"], state["error_code"]) == ("failed", "JOB_EXPIRED")
        assert state["error_message"] == DOCUMENT_ERROR_MESSAGES[DocumentErrorCode.JOB_EXPIRED]
        assert job_state(scene.url, job_id)["has_payload"] is False

    def test_a_young_job_is_untouched(self, scene: Scene) -> None:
        document, job_id = insert_pending(scene.url, scene.subject)
        age_job(scene.url, job_id, MAX_AGE_HOURS - 1)

        result = sweep(scene.url)

        assert result == SweepResult(interrupted=0, expired=0, erased=0)
        assert document_state(scene.url, document)["status"] == "pending"
        assert job_state(scene.url, job_id)["has_payload"] is True

    def test_an_old_job_under_a_valid_lease_is_not_expired(self, scene: Scene) -> None:
        document, job_id = insert_pending(scene.url, scene.subject)
        age_job(scene.url, job_id, MAX_AGE_HOURS + 5)
        assert claim(scene.url) is not None

        assert sweep(scene.url).expired == 0
        assert document_state(scene.url, document)["status"] == "processing"

    def test_an_exhausted_old_job_is_reported_as_interrupted_not_expired(
        self, scene: Scene
    ) -> None:
        document, job_id = insert_pending(scene.url, scene.subject)
        for _ in range(MAX_ATTEMPTS):
            claim(scene.url)
            expire_lease(scene.url, job_id)
        age_job(scene.url, job_id, MAX_AGE_HOURS + 5)

        result = sweep(scene.url)

        assert (result.interrupted, result.expired) == (1, 0)
        assert document_state(scene.url, document)["error_code"] == "PROCESSING_INTERRUPTED"

    @pytest.mark.parametrize("status", ["ready", "failed"])
    def test_bytes_left_by_a_terminal_document_are_erased(self, scene: Scene, status: str) -> None:
        document, job_id = insert_pending(scene.url, scene.subject, status=status)

        result = sweep(scene.url)

        assert result.erased == 1
        assert job_state(scene.url, job_id)["has_payload"] is False
        assert document_state(scene.url, document)["status"] == status

    def test_the_sweep_never_changes_a_terminal_document(self, scene: Scene) -> None:
        document, job_id = insert_pending(scene.url, scene.subject, status="ready")
        age_job(scene.url, job_id, MAX_AGE_HOURS + 5)

        sweep(scene.url)

        state = document_state(scene.url, document)
        assert (state["status"], state["error_code"]) == ("ready", None)

    def test_running_the_sweep_twice_changes_nothing_more(self, scene: Scene) -> None:
        _, job_id = insert_pending(scene.url, scene.subject)
        age_job(scene.url, job_id, MAX_AGE_HOURS + 1)
        sweep(scene.url)

        assert sweep(scene.url) == SweepResult(interrupted=0, expired=0, erased=0)

    def test_a_processing_document_whose_bytes_are_gone_and_whose_lease_expired_is_failed(
        self, scene: Scene
    ) -> None:
        document, job_id = insert_pending(scene.url, scene.subject)
        job = claim(scene.url)
        assert job is not None
        with session_for(scene.url) as session:
            IngestionJobRepository(session).erase_payload(job.job_id, job.token)
            session.commit()
        run(
            scene.url,
            "UPDATE ingestion_jobs SET locked_by = 'gone', "
            "locked_until = clock_timestamp() - interval '5 seconds' WHERE id = :j",
            j=job_id,
        )

        result = sweep(scene.url)

        assert result.interrupted == 1
        assert document_state(scene.url, document)["error_code"] == "PROCESSING_INTERRUPTED"

    def test_the_sweep_does_not_wait_for_a_document_locked_by_another_session(
        self, scene: Scene
    ) -> None:
        locked_document, locked_job = insert_pending(scene.url, scene.subject)
        free_document, free_job = insert_pending(scene.url, scene.subject)
        for job_id in (locked_job, free_job):
            age_job(scene.url, job_id, MAX_AGE_HOURS + 1)
        with session_for(scene.url) as holder:
            holder.execute(
                text("SELECT id FROM documents WHERE id = :d FOR UPDATE"), {"d": locked_document}
            )
            started = time.monotonic()

            result = sweep(scene.url)

            elapsed = time.monotonic() - started
            holder.rollback()
        assert result.expired == 1
        assert document_state(scene.url, free_document)["error_code"] == "JOB_EXPIRED"
        assert document_state(scene.url, locked_document)["status"] == "pending"
        assert elapsed < 5

    def test_the_sweep_skips_rows_locked_by_another_transaction(self, scene: Scene) -> None:
        _, job_id = insert_pending(scene.url, scene.subject)
        age_job(scene.url, job_id, MAX_AGE_HOURS + 1)
        with session_for(scene.url) as holder:
            holder.execute(
                text("SELECT id FROM ingestion_jobs WHERE id = :j FOR UPDATE"), {"j": job_id}
            )

            result = sweep(scene.url)  # must not wait for the lock

            assert result.expired == 0
            holder.rollback()
        assert sweep(scene.url).expired == 1

    def test_the_sweep_does_not_rewrite_tables_or_take_exclusive_locks(self, scene: Scene) -> None:
        for _ in range(3):
            _, job_id = insert_pending(scene.url, scene.subject)
            age_job(scene.url, job_id, MAX_AGE_HOURS + 1)
        insert_pending(scene.url, scene.subject, status="ready")
        statements: list[str] = []
        with session_for(scene.url) as session:
            engine = session.get_bind()
            event.listen(
                engine,
                "before_cursor_execute",
                lambda conn, cursor, statement, params, context, many: statements.append(statement),
            )
            IngestionJobRepository(session).sweep(MAX_ATTEMPTS, MAX_AGE_HOURS)
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

        forbidden = ("VACUUM", "LOCK TABLE", "TRUNCATE", "ALTER ", "REINDEX", "CLUSTER", "DROP ")
        issued = " ".join(statements).upper()
        assert statements, "the sweep issued no statement"
        assert not [word for word in forbidden if word in issued]
        assert modes <= {"AccessShareLock", "RowShareLock", "RowExclusiveLock"}


class TestBytesAreErasedOnEveryTerminalPath:
    def test_failure_erases_the_bytes(self, scene: Scene) -> None:
        document, job_id = insert_pending(scene.url, scene.subject)
        job = claim(scene.url)
        assert job is not None

        with session_for(scene.url) as session:
            assert IngestionJobRepository(session).mark_failed(
                job.job_id, job.token, DocumentErrorCode.CORRUPT_FILE
            )
            session.commit()

        assert job_state(scene.url, job_id)["has_payload"] is False
        state = document_state(scene.url, document)
        assert (state["status"], state["error_code"]) == ("failed", "CORRUPT_FILE")
        assert state["error_message"] == DOCUMENT_ERROR_MESSAGES[DocumentErrorCode.CORRUPT_FILE]

    def test_a_failed_job_is_not_claimable_again(self, scene: Scene) -> None:
        insert_pending(scene.url, scene.subject)
        job = claim(scene.url)
        assert job is not None
        with session_for(scene.url) as session:
            IngestionJobRepository(session).mark_failed(
                job.job_id, job.token, DocumentErrorCode.PROCESSING_FAILED
            )
            session.commit()

        assert claim(scene.url) is None

    def test_erasing_the_bytes_of_an_owned_job(self, scene: Scene) -> None:
        _, job_id = insert_pending(scene.url, scene.subject, PDF_BYTES)
        job = claim(scene.url)
        assert job is not None

        with session_for(scene.url) as session:
            assert IngestionJobRepository(session).erase_payload(job.job_id, job.token)
            session.commit()

        assert job_state(scene.url, job_id)["has_payload"] is False

    def test_deletion_removes_the_job_with_its_bytes(self, scene: Scene) -> None:
        document, job_id = insert_pending(scene.url, scene.subject)
        run(scene.url, "DELETE FROM documents WHERE id = :d", d=document)

        assert job_state(scene.url, job_id) == {}


def test_claim_tokens_are_random(scene: Scene) -> None:
    from app.repositories.ingestion_job_repository import new_claim_token

    tokens = {new_claim_token() for _ in range(200)}

    assert len(tokens) == 200
    assert all(20 <= len(token) <= 64 for token in tokens)
    assert uuid.UUID(int=0).hex not in tokens
