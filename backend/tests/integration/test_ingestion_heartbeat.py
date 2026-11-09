"""Lease renewal during slow work, lost leases and the job deadline (change 6, task 8.4).

These tests use real time: a 3 second lease and jobs of several seconds, a slow fake embedder and
a slow fake PDF child. The heartbeat renews every lease/3 seconds in its own short transaction.
"""

import threading
import time
import uuid

import pytest
from sqlalchemy.exc import OperationalError

from app.core.database import create_db_engine, create_session_factory
from app.rag.loaders import Page
from app.repositories.ingestion_job_repository import IngestionJobRepository
from app.services.ingestion_service import Outcome
from tests.ingestion_support import (
    Scene,
    chunk_count,
    document_state,
    expire_lease,
    insert_pending,
    job_state,
    make_scene,
)
from tests.service_support import LONG_TEXT, SHORT_TEXT, HookEmbedder, activity, built_service

LEASE = 3


@pytest.fixture
def scene(clean_db: str) -> Scene:
    return make_scene(clean_db)


def add_text(scene: Scene, payload: bytes) -> tuple[uuid.UUID, uuid.UUID]:
    return insert_pending(
        scene.url, scene.subject, payload=payload, filename="a.txt", content_type="text/plain"
    )


def sleeping(seconds: float) -> HookEmbedder:
    """An embedder that takes `seconds` per batch (no database access)."""
    return HookEmbedder(lambda call: time.sleep(seconds))


class Poller:
    """Tries to claim jobs from another session every 0.3 s while a job runs."""

    def __init__(self, url: str) -> None:
        self._engine = create_db_engine(url)
        self._factory = create_session_factory(self._engine)
        self._stop = threading.Event()
        self.claims: list[object] = []
        self._thread = threading.Thread(target=self._run, daemon=True)

    def _run(self) -> None:
        while not self._stop.wait(0.3):
            with self._factory() as session:
                job = IngestionJobRepository(session).claim(LEASE, 3)
                session.commit()
            if job is not None:
                self.claims.append(job)

    def __enter__(self) -> "Poller":
        self._thread.start()
        return self

    def __exit__(self, *exc: object) -> None:
        self._stop.set()
        self._thread.join(timeout=10)
        self._engine.dispose()


class TestHeartbeatKeepsTheLease:
    def test_a_job_that_outlives_the_lease_finishes_once_and_nobody_else_claims_it(
        self, scene: Scene
    ) -> None:
        document, job = insert_pending(scene.url, scene.subject)  # a PDF
        idle_samples: list[int] = []

        def slow_pdf_child(payload: bytes) -> list[Page]:
            # Longer than the lease; the main thread is blocked and only the heartbeat renews.
            deadline = time.monotonic() + 4.5
            while time.monotonic() < deadline:
                idle_samples.append(activity(scene.url).idle_in_transaction)
                time.sleep(0.25)
            return [Page(1, LONG_TEXT.decode())]

        with Poller(scene.url) as poller:
            with built_service(
                scene.url,
                sleeping(0.5),
                pdf_loader=slow_pdf_child,
                lease_seconds=LEASE,
                deadline_seconds=60,
                batch_size=2,
            ) as built:
                outcome = built.service.run_once()

        assert outcome is Outcome.READY
        assert poller.claims == []
        assert job_state(scene.url, job)["attempts"] == 1
        state = document_state(scene.url, document)
        assert state["status"] == "ready"
        assert state["chunks_count"] == chunk_count(scene.url, document) > 1
        assert idle_samples and max(idle_samples) == 0  # no transaction is ever left open

    def test_the_renewals_are_single_statements_that_leave_nothing_open(self, scene: Scene) -> None:
        add_text(scene, LONG_TEXT)
        samples: list[int] = []

        def hook(call: int) -> None:
            for _ in range(5):
                samples.append(activity(scene.url).idle_in_transaction)
                time.sleep(0.25)

        with built_service(
            scene.url, HookEmbedder(hook), lease_seconds=LEASE, deadline_seconds=60, batch_size=3
        ) as built:
            assert built.service.run_once() is Outcome.READY

        assert len(samples) >= 10 and max(samples) == 0


class TestLostLease:
    @pytest.mark.parametrize("payload", [LONG_TEXT, SHORT_TEXT], ids=["many-batches", "one-batch"])
    def test_a_stale_worker_stops_and_cannot_confirm_results(
        self, scene: Scene, payload: bytes
    ) -> None:
        document, job = add_text(scene, payload)
        started, release = threading.Event(), threading.Event()
        stale_result: list[Outcome] = []

        def hold(call: int) -> None:
            if call == 1:
                started.set()
                release.wait(timeout=30)

        stale_embedder = HookEmbedder(hold)

        def stale_worker() -> None:
            with built_service(
                scene.url, stale_embedder, lease_seconds=LEASE, deadline_seconds=60, batch_size=4
            ) as built:
                stale_result.append(built.service.run_once())

        thread = threading.Thread(target=stale_worker)
        thread.start()
        assert started.wait(timeout=20)
        expire_lease(scene.url, job)  # the stale worker is slow: its lease is gone
        time.sleep(2.5)  # its heartbeat finds no valid lease and sets the lost flag
        with built_service(scene.url, lease_seconds=LEASE, deadline_seconds=60) as fresh:
            fresh_outcome = fresh.service.run_once()  # another worker takes over
        release.set()
        thread.join(timeout=30)

        assert fresh_outcome is Outcome.READY
        assert stale_result == [Outcome.LOST]
        assert stale_embedder.calls == 1  # it stopped at the next batch, or before confirming
        state = document_state(scene.url, document)
        assert state["status"] == "ready"
        assert state["chunks_count"] == chunk_count(scene.url, document)
        assert job_state(scene.url, job)["attempts"] == 2

    def test_a_deleted_job_is_noticed_by_the_heartbeat(self, scene: Scene) -> None:
        from tests.sql_support import run

        document, _ = add_text(scene, LONG_TEXT)
        started, release = threading.Event(), threading.Event()
        result: list[Outcome] = []

        def hold(call: int) -> None:
            if call == 1:
                started.set()
                release.wait(timeout=30)

        embedder = HookEmbedder(hold)

        def worker() -> None:
            with built_service(
                scene.url, embedder, lease_seconds=LEASE, deadline_seconds=60, batch_size=4
            ) as built:
                result.append(built.service.run_once())

        thread = threading.Thread(target=worker)
        thread.start()
        assert started.wait(timeout=20)
        run(scene.url, "DELETE FROM documents WHERE id = :d", d=document)
        time.sleep(2.5)
        release.set()
        thread.join(timeout=30)

        assert result == [Outcome.LOST]
        assert embedder.calls == 1
        assert chunk_count(scene.url, document) == 0

    def test_a_database_that_cannot_be_reached_ends_as_a_lost_lease(
        self, scene: Scene, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        document, job = add_text(scene, LONG_TEXT)

        def unreachable(self, *args, **kwargs):  # type: ignore[no-untyped-def]
            raise OperationalError("stmt", {}, Exception("connection refused"))

        monkeypatch.setattr(IngestionJobRepository, "renew", unreachable)
        embedder = sleeping(1.0)

        with built_service(
            scene.url, embedder, lease_seconds=LEASE, deadline_seconds=60, batch_size=2
        ) as built:
            outcome = built.service.run_once()

        # Renewals fail for a whole lease: the worker cannot prove it still owns the job.
        assert outcome is Outcome.LOST
        assert embedder.calls < 6
        assert chunk_count(scene.url, document) == 0
        assert job_state(scene.url, job)["has_payload"] is True


class TestDeadline:
    def test_the_heartbeat_stops_renewing_after_the_deadline_and_the_job_times_out(
        self, scene: Scene, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        document, job = add_text(scene, LONG_TEXT)
        renewals: list[float] = []
        original = IngestionJobRepository.renew

        def recording(self, job_id, token, lease_seconds):  # type: ignore[no-untyped-def]
            renewals.append(time.monotonic())
            return original(self, job_id, token, lease_seconds)

        monkeypatch.setattr(IngestionJobRepository, "renew", recording)

        with built_service(
            scene.url, sleeping(1.0), lease_seconds=LEASE, deadline_seconds=4, batch_size=1
        ) as built:
            started = time.monotonic()
            outcome = built.service.run_once()
            elapsed = time.monotonic() - started

        state = document_state(scene.url, document)
        assert outcome is Outcome.FAILED
        assert state["status"] == "failed" and state["error_code"] == "PROCESSING_TIMEOUT"
        assert renewals, "the lease was renewed while the job was inside its deadline"
        assert max(renewals) - started < 4.5  # nothing is renewed after the deadline
        assert elapsed < 7  # it did not run to the end of the nine batches
        assert chunk_count(scene.url, document) == 0
        assert job_state(scene.url, job)["has_payload"] is False
