"""IngestionService against a real PostgreSQL with the fake embedder (change 6, task 8.1)."""

import uuid

import pytest
from sqlalchemy.exc import OperationalError

from app.models.ingestion import DOCUMENT_ERROR_MESSAGES, DocumentErrorCode
from app.rag.chunker import Page
from app.rag.embedder import EmbeddingError, FakeEmbedder
from app.rag.loaders import DocumentLoadError, UnsupportedPlatformError
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
    session_for,
)
from tests.service_support import (
    LONG_TEXT,
    SHORT_TEXT,
    HookEmbedder,
    activity,
    built_service,
    capture_logs,
    checked_out,
    log_text,
)
from tests.sql_support import run, scalar


@pytest.fixture
def scene(clean_db: str) -> Scene:
    return make_scene(clean_db)


def add_text(
    scene: Scene,
    payload: bytes = SHORT_TEXT,
    filename: str = "notes.txt",
    content_type: str = "text/plain",
) -> tuple[uuid.UUID, uuid.UUID]:
    return insert_pending(
        scene.url, scene.subject, payload=payload, filename=filename, content_type=content_type
    )


def add_pdf(scene: Scene) -> tuple[uuid.UUID, uuid.UUID]:
    return insert_pending(scene.url, scene.subject)  # application/pdf, bytes are irrelevant


class FakeClock:
    def __init__(self) -> None:
        self.now = 1000.0

    def __call__(self) -> float:
        return self.now


class TestSuccess:
    def test_a_text_document_becomes_ready_with_its_chunks_and_no_bytes(self, scene: Scene) -> None:
        document, job = add_text(scene, LONG_TEXT)

        with built_service(scene.url) as built:
            outcome = built.service.run_once()

        state = document_state(scene.url, document)
        assert outcome is Outcome.READY
        assert state["status"] == "ready"
        assert state["error_code"] is None
        assert state["chunks_count"] == chunk_count(scene.url, document) > 1
        after = job_state(scene.url, job)
        assert after["has_payload"] is False
        assert after["locked_by"] is None
        assert after["attempts"] == 1

    def test_chunk_indexes_are_consecutive_and_text_has_no_page_numbers(self, scene: Scene) -> None:
        document, _ = add_text(scene, LONG_TEXT)

        with built_service(scene.url) as built:
            built.service.run_once()

        rows = scalar(
            scene.url,
            "SELECT string_agg(chunk_index::text || ':' || coalesce(page_number::text, 'n'), ',' "
            "ORDER BY chunk_index) FROM document_chunks WHERE document_id = :d",
            d=document,
        )
        count = chunk_count(scene.url, document)
        assert rows == ",".join(f"{i}:n" for i in range(count))

    def test_markdown_is_loaded_as_markdown_data(self, scene: Scene) -> None:
        document, _ = add_text(
            scene, b"# Title\n\nSome *emphasis* here.", "notes.md", "text/markdown"
        )

        with built_service(scene.url) as built:
            outcome = built.service.run_once()

        assert outcome is Outcome.READY
        assert chunk_count(scene.url, document) >= 1

    def test_a_pdf_keeps_its_page_numbers(self, scene: Scene) -> None:
        document, _ = add_pdf(scene)
        pages = [Page(1, "first page text about limits"), Page(2, "second page about series")]
        seen: list[bytes] = []

        def loader(payload: bytes) -> list[Page]:
            seen.append(payload)
            return pages

        with built_service(scene.url, pdf_loader=loader) as built:
            outcome = built.service.run_once()

        numbers = scalar(
            scene.url,
            "SELECT string_agg(page_number::text, ',' ORDER BY chunk_index) "
            "FROM document_chunks WHERE document_id = :d",
            d=document,
        )
        assert outcome is Outcome.READY
        assert numbers == "1,2"
        assert len(seen) == 1

    def test_without_a_claimable_job_the_outcome_is_idle(self, clean_db: str) -> None:
        with built_service(clean_db) as built:
            assert built.service.run_once() is Outcome.IDLE


FAILURES = [
    DocumentErrorCode.NO_EXTRACTABLE_TEXT,
    DocumentErrorCode.ENCRYPTED_PDF,
    DocumentErrorCode.CORRUPT_FILE,
    DocumentErrorCode.TOO_MANY_PAGES,
    DocumentErrorCode.TEXT_TOO_LARGE,
    DocumentErrorCode.PROCESSING_TIMEOUT,
    DocumentErrorCode.RESOURCE_LIMIT_EXCEEDED,
]


class TestFailures:
    def assert_failed(self, scene: Scene, document: uuid.UUID, job: uuid.UUID, code: str) -> None:
        state = document_state(scene.url, document)
        assert state["status"] == "failed"
        assert state["error_code"] == code
        assert state["error_message"] == DOCUMENT_ERROR_MESSAGES[DocumentErrorCode(code)]
        assert state["chunks_count"] == 0
        assert chunk_count(scene.url, document) == 0
        after = job_state(scene.url, job)
        assert after["has_payload"] is False
        assert after["locked_by"] is None

    @pytest.mark.parametrize("code", FAILURES, ids=lambda code: code.value)
    def test_a_loader_failure_stores_its_own_code(
        self, scene: Scene, code: DocumentErrorCode
    ) -> None:
        document, job = add_pdf(scene)

        def loader(payload: bytes) -> list[Page]:
            raise DocumentLoadError(code)

        with built_service(scene.url, pdf_loader=loader) as built:
            outcome = built.service.run_once()

        assert outcome is Outcome.FAILED
        self.assert_failed(scene, document, job, code.value)

    def test_too_many_chunks(self, scene: Scene) -> None:
        document, job = add_text(scene, LONG_TEXT)

        with built_service(scene.url, max_chunks=2) as built:
            outcome = built.service.run_once()

        assert outcome is Outcome.FAILED
        self.assert_failed(scene, document, job, "TOO_MANY_CHUNKS")

    def test_text_over_the_character_limit(self, scene: Scene) -> None:
        document, job = add_text(scene, LONG_TEXT)

        with built_service(scene.url, max_chars=100) as built:
            outcome = built.service.run_once()

        assert outcome is Outcome.FAILED
        self.assert_failed(scene, document, job, "TEXT_TOO_LARGE")

    def test_blank_text(self, scene: Scene) -> None:
        document, job = add_text(scene, b"   \n\t  ")

        with built_service(scene.url) as built:
            built.service.run_once()

        self.assert_failed(scene, document, job, "NO_EXTRACTABLE_TEXT")

    def test_invalid_utf8(self, scene: Scene) -> None:
        document, job = add_text(scene, b"\xff\xfe broken")

        with built_service(scene.url) as built:
            built.service.run_once()

        self.assert_failed(scene, document, job, "CORRUPT_FILE")

    def test_an_embedder_error(self, scene: Scene) -> None:
        document, job = add_text(scene)

        def hook(call: int) -> None:
            raise EmbeddingError("embedding failed")

        with built_service(scene.url, HookEmbedder(hook)) as built:
            outcome = built.service.run_once()

        assert outcome is Outcome.FAILED
        self.assert_failed(scene, document, job, "EMBEDDING_FAILED")

    def test_an_invalid_vector_fails_at_once_as_an_embedding_failure(self, scene: Scene) -> None:
        document, job = add_text(scene, LONG_TEXT)

        class Zeros(HookEmbedder):
            def embed(self, texts):  # type: ignore[no-untyped-def]
                self.calls += 1
                return [[0.0] * 384 for _ in texts]

        embedder = Zeros()
        with built_service(scene.url, embedder) as built:
            built.service.run_once()

        self.assert_failed(scene, document, job, "EMBEDDING_FAILED")
        assert embedder.calls == 1  # the first bad batch ends the job; no more batches run

    def test_a_missing_vector_fails_at_once_as_an_embedding_failure(self, scene: Scene) -> None:
        document, job = add_text(scene, LONG_TEXT)

        class Short(HookEmbedder):
            def embed(self, texts):  # type: ignore[no-untyped-def]
                return super().embed(texts)[:-1]

        embedder = Short()
        with built_service(scene.url, embedder) as built:
            built.service.run_once()

        self.assert_failed(scene, document, job, "EMBEDDING_FAILED")
        assert embedder.calls == 1

    def test_an_unexpected_exception_is_processing_failed(self, scene: Scene) -> None:
        document, job = add_text(scene)

        def hook(call: int) -> None:
            raise RuntimeError("anything at all")

        with built_service(scene.url, HookEmbedder(hook)) as built:
            outcome = built.service.run_once()

        assert outcome is Outcome.FAILED
        self.assert_failed(scene, document, job, "PROCESSING_FAILED")

    def test_a_fragment_that_cannot_fit_the_model_is_processing_failed(self, scene: Scene) -> None:
        document, job = add_text(scene)

        class Huge(FakeEmbedder):
            def count_tokens(self, text: str, *, include_special: bool = True) -> int:
                return 10_000

        with built_service(scene.url, Huge()) as built:
            built.service.run_once()

        self.assert_failed(scene, document, job, "PROCESSING_FAILED")

    def test_pdf_outside_linux_is_processing_failed(self, scene: Scene) -> None:
        document, job = add_pdf(scene)

        def loader(payload: bytes) -> list[Page]:
            raise UnsupportedPlatformError

        with built_service(scene.url, pdf_loader=loader) as built:
            built.service.run_once()

        self.assert_failed(scene, document, job, "PROCESSING_FAILED")

    def test_the_job_deadline_fails_the_document_with_a_timeout(self, scene: Scene) -> None:
        document, job = add_text(scene, LONG_TEXT)
        clock = FakeClock()

        def hook(call: int) -> None:
            clock.now += 601  # the first batch "takes" longer than the deadline

        with built_service(scene.url, HookEmbedder(hook), clock=clock) as built:
            outcome = built.service.run_once()

        assert outcome is Outcome.FAILED
        self.assert_failed(scene, document, job, "PROCESSING_TIMEOUT")

    def test_the_deadline_is_checked_before_any_work(self, scene: Scene) -> None:
        document, job = add_pdf(scene)
        clock = FakeClock()

        def loader(payload: bytes) -> list[Page]:
            clock.now += 601
            return [Page(1, "late text")]

        with built_service(scene.url, pdf_loader=loader, clock=clock) as built:
            built.service.run_once()

        self.assert_failed(scene, document, job, "PROCESSING_TIMEOUT")

    def test_the_sweep_codes_come_from_the_service(self, scene: Scene) -> None:
        interrupted_doc, interrupted_job = add_text(scene)
        expired_doc, expired_job = add_text(scene)
        run(scene.url, "UPDATE ingestion_jobs SET attempts = 3 WHERE id = :j", j=interrupted_job)
        run(
            scene.url,
            "UPDATE ingestion_jobs SET created_at = now() - interval '48 hours' WHERE id = :j",
            j=expired_job,
        )

        with built_service(scene.url) as built:
            result = built.service.sweep()

        assert result.interrupted == 1 and result.expired == 1
        assert document_state(scene.url, interrupted_doc)["error_code"] == "PROCESSING_INTERRUPTED"
        assert document_state(scene.url, expired_doc)["error_code"] == "JOB_EXPIRED"


class TestNoLeaks:
    SECRET_EXCEPTION = "SECRET-EXCEPTION-MARKER"
    SECRET_FILE = "SECRET-FILENAME-MARKER.txt"
    SECRET_CONTENT = "SECRETCONTENTMARKER"

    def test_no_exception_text_is_stored_or_logged(
        self, scene: Scene, caplog: pytest.LogCaptureFixture
    ) -> None:
        capture_logs(caplog)
        document, job = add_text(
            scene, f"{self.SECRET_CONTENT} body".encode(), filename=self.SECRET_FILE
        )

        def hook(call: int) -> None:
            raise RuntimeError(self.SECRET_EXCEPTION)

        with built_service(scene.url, HookEmbedder(hook)) as built:
            built.service.run_once()

        logs = log_text(caplog)
        stored = str(document_state(scene.url, document))
        for marker in (self.SECRET_EXCEPTION, self.SECRET_FILE, self.SECRET_CONTENT):
            assert marker not in logs
            assert marker not in stored
        assert "Traceback" not in logs
        assert str(document) in logs  # identifiers are logged

    def test_a_successful_job_logs_no_filename_or_content(
        self, scene: Scene, caplog: pytest.LogCaptureFixture
    ) -> None:
        capture_logs(caplog)
        add_text(scene, f"{self.SECRET_CONTENT} body".encode(), filename=self.SECRET_FILE)

        with built_service(scene.url) as built:
            built.service.run_once()

        logs = log_text(caplog)
        assert self.SECRET_FILE not in logs and self.SECRET_CONTENT not in logs

    def test_a_database_error_text_is_not_logged(
        self, scene: Scene, caplog: pytest.LogCaptureFixture, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        capture_logs(caplog)
        add_text(scene)

        marker = "SECRET-DB-ERROR-MARKER"

        def broken(self, *args, **kwargs):  # type: ignore[no-untyped-def]
            raise OperationalError("stmt", {"p": 1}, Exception(marker))

        monkeypatch.setattr(IngestionJobRepository, "complete", broken)

        with built_service(scene.url) as built:
            built.service.run_once()

        assert marker not in log_text(caplog)


class TestCancellationAndLease:
    def test_a_database_failure_at_the_end_abandons_the_job_without_failing_it(
        self, scene: Scene, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        document, job = add_text(scene)

        def broken(self, *args, **kwargs):  # type: ignore[no-untyped-def]
            raise OperationalError("stmt", {}, Exception("connection lost"))

        monkeypatch.setattr(IngestionJobRepository, "complete", broken)

        with built_service(scene.url) as built:
            outcome = built.service.run_once()

        assert outcome is Outcome.ABANDONED
        assert document_state(scene.url, document)["status"] == "processing"
        assert job_state(scene.url, job)["has_payload"] is True

    def test_deleting_the_document_between_phases_stops_without_writing(self, scene: Scene) -> None:
        document, _ = add_text(scene, LONG_TEXT)

        def hook(call: int) -> None:
            if call == 1:
                run(scene.url, "DELETE FROM documents WHERE id = :d", d=document)

        embedder = HookEmbedder(hook)
        with built_service(scene.url, embedder) as built:
            outcome = built.service.run_once()

        assert outcome is Outcome.LOST
        assert document_state(scene.url, document) == {}
        assert chunk_count(scene.url, document) == 0
        assert embedder.calls == 1  # it stopped at the next batch boundary

    def test_deleting_the_document_during_the_last_batch_is_quiet(self, scene: Scene) -> None:
        document, job = add_text(scene)

        def hook(call: int) -> None:
            run(scene.url, "DELETE FROM documents WHERE id = :d", d=document)

        with built_service(scene.url, HookEmbedder(hook)) as built:
            outcome = built.service.run_once()

        assert outcome is Outcome.LOST
        assert job_state(scene.url, job) == {}
        assert chunk_count(scene.url, document) == 0

    def test_a_lost_lease_stops_the_worker_and_leaves_the_job_untouched(self, scene: Scene) -> None:
        document, job = add_text(scene, LONG_TEXT)

        def hook(call: int) -> None:
            if call == 1:
                expire_lease(scene.url, job)

        embedder = HookEmbedder(hook)
        with built_service(scene.url, embedder) as built:
            outcome = built.service.run_once()

        assert outcome is Outcome.LOST
        assert embedder.calls == 1
        assert document_state(scene.url, document)["status"] == "processing"
        assert chunk_count(scene.url, document) == 0
        assert job_state(scene.url, job)["has_payload"] is True  # not its job any more

    def test_a_job_claimed_by_someone_else_cannot_be_confirmed(self, scene: Scene) -> None:
        document, job = add_text(scene)

        def hook(call: int) -> None:
            run(scene.url, "UPDATE ingestion_jobs SET locked_by = 'other' WHERE id = :j", j=job)

        with built_service(scene.url, HookEmbedder(hook)) as built:
            outcome = built.service.run_once()

        assert outcome is Outcome.LOST
        assert chunk_count(scene.url, document) == 0
        assert document_state(scene.url, document)["status"] == "processing"


class TestTerminalWritesAreFenced:
    def test_a_final_transaction_the_fence_refuses_is_a_lost_job(
        self, scene: Scene, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        document, _ = add_text(scene)
        monkeypatch.setattr(IngestionJobRepository, "complete", lambda *args, **kwargs: False)

        with built_service(scene.url) as built:
            outcome = built.service.run_once()

        assert outcome is Outcome.LOST
        assert document_state(scene.url, document)["status"] == "processing"

    def test_a_failure_mark_the_fence_refuses_is_a_lost_job(
        self, scene: Scene, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        document, job = add_pdf(scene)
        monkeypatch.setattr(IngestionJobRepository, "mark_failed", lambda *args, **kwargs: False)

        def loader(payload: bytes) -> list[Page]:
            raise DocumentLoadError(DocumentErrorCode.CORRUPT_FILE)

        with built_service(scene.url, pdf_loader=loader) as built:
            outcome = built.service.run_once()

        assert outcome is Outcome.LOST
        assert document_state(scene.url, document)["status"] == "processing"
        assert job_state(scene.url, job)["has_payload"] is True

    def test_a_database_error_while_failing_the_job_abandons_it(
        self, scene: Scene, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        document, _ = add_pdf(scene)

        def broken(self, *args, **kwargs):  # type: ignore[no-untyped-def]
            raise OperationalError("stmt", {}, Exception("connection lost"))

        monkeypatch.setattr(IngestionJobRepository, "mark_failed", broken)

        def loader(payload: bytes) -> list[Page]:
            raise DocumentLoadError(DocumentErrorCode.CORRUPT_FILE)

        with built_service(scene.url, pdf_loader=loader) as built:
            outcome = built.service.run_once()

        assert outcome is Outcome.ABANDONED
        assert document_state(scene.url, document)["status"] == "processing"


class TestOddInputs:
    def test_a_refusal_of_the_repository_is_processing_failed(
        self, scene: Scene, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        document, _ = add_text(scene)

        def refuse(self, *args, **kwargs):  # type: ignore[no-untyped-def]
            raise ValueError("refused before any statement")

        monkeypatch.setattr(IngestionJobRepository, "complete", refuse)

        with built_service(scene.url) as built:
            outcome = built.service.run_once()

        assert outcome is Outcome.FAILED
        assert document_state(scene.url, document)["error_code"] == "PROCESSING_FAILED"

    def test_the_lease_is_renewed_at_every_phase_boundary(
        self, scene: Scene, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        add_text(scene)
        renewals: list[int] = []
        original = IngestionJobRepository.renew

        def counting(self, job_id, token, lease_seconds):  # type: ignore[no-untyped-def]
            renewals.append(1)
            return original(self, job_id, token, lease_seconds)

        monkeypatch.setattr(IngestionJobRepository, "renew", counting)

        with built_service(scene.url, batch_size=16) as built:  # one batch
            built.service.run_once()

        # before loading, after loading, before the batch and before the final write
        assert len(renewals) == 4

    def test_pages_that_produce_no_chunk_have_no_extractable_text(self, scene: Scene) -> None:
        document, _ = add_pdf(scene)

        with built_service(scene.url, pdf_loader=lambda payload: [Page(1, "   ")]) as built:
            outcome = built.service.run_once()

        assert outcome is Outcome.FAILED
        assert document_state(scene.url, document)["error_code"] == "NO_EXTRACTABLE_TEXT"

    def test_an_unknown_content_type_is_processing_failed(self, scene: Scene) -> None:
        document, _ = insert_pending(
            scene.url, scene.subject, payload=SHORT_TEXT, content_type="image/png"
        )

        with built_service(scene.url) as built:
            outcome = built.service.run_once()

        assert outcome is Outcome.FAILED
        assert document_state(scene.url, document)["error_code"] == "PROCESSING_FAILED"

    def test_a_pdf_without_a_loader_or_limits_is_processing_failed(self, scene: Scene) -> None:
        document, _ = add_pdf(scene)

        with built_service(scene.url) as built:  # no loader and no PDF limits configured
            built.service.run_once()

        assert document_state(scene.url, document)["error_code"] == "PROCESSING_FAILED"

    @pytest.mark.parametrize("outcome_case", ["ready", "failed", "lost"])
    def test_the_heartbeat_thread_never_outlives_the_job(
        self, scene: Scene, outcome_case: str
    ) -> None:
        import threading

        document, job = add_text(scene, b"   " if outcome_case == "failed" else SHORT_TEXT)

        def hook(call: int) -> None:
            if outcome_case == "lost":
                expire_lease(scene.url, job)

        with built_service(scene.url, HookEmbedder(hook), batch_size=1) as built:
            built.service.run_once()

        assert [t for t in threading.enumerate() if t.name == "ingestion-heartbeat"] == []
        assert document_state(scene.url, document)


class TestRetries:
    def test_a_job_whose_worker_died_is_claimed_again_and_finishes_once(self, scene: Scene) -> None:
        document, job = add_text(scene, LONG_TEXT)
        with session_for(scene.url) as session:  # a worker that claims and then dies
            assert IngestionJobRepository(session).claim(120, 3) is not None
            session.commit()
        with built_service(scene.url) as built:
            assert built.service.run_once() is Outcome.IDLE  # lease still valid
            expire_lease(scene.url, job)
            outcome = built.service.run_once()

        assert outcome is Outcome.READY
        assert job_state(scene.url, job)["attempts"] == 2
        count = chunk_count(scene.url, document)
        assert count > 1
        assert count == document_state(scene.url, document)["chunks_count"]

    def test_a_job_with_no_attempts_left_is_not_claimed_and_the_sweep_fails_it(
        self, scene: Scene
    ) -> None:
        document, job = add_text(scene)
        run(scene.url, "UPDATE ingestion_jobs SET attempts = 3 WHERE id = :j", j=job)

        with built_service(scene.url) as built:
            assert built.service.run_once() is Outcome.IDLE
            built.service.sweep()

        state = document_state(scene.url, document)
        assert state["status"] == "failed" and state["error_code"] == "PROCESSING_INTERRUPTED"
        assert job_state(scene.url, job)["has_payload"] is False

    def test_the_third_attempt_is_still_allowed(self, scene: Scene) -> None:
        document, job = add_text(scene)
        run(scene.url, "UPDATE ingestion_jobs SET attempts = 2 WHERE id = :j", j=job)

        with built_service(scene.url) as built:
            outcome = built.service.run_once()

        assert outcome is Outcome.READY
        assert job_state(scene.url, job)["attempts"] == 3


class TestNothingIsHeldWhileWorking:
    def test_no_transaction_lock_or_connection_while_the_embedder_runs(self, scene: Scene) -> None:
        add_text(scene, LONG_TEXT)
        samples: list[tuple[int, int, int, int]] = []

        def probe() -> None:
            seen = activity(scene.url)
            samples.append(
                (
                    seen.idle_in_transaction,
                    seen.open_transactions,
                    seen.locks,
                    checked_out(built.engine),
                )
            )

        embedder = HookEmbedder(lambda call: probe())
        with built_service(scene.url, embedder) as built:
            outcome = built.service.run_once()

        assert outcome is Outcome.READY
        assert len(samples) >= 3
        assert all(sample == (0, 0, 0, 0) for sample in samples)

    def test_no_transaction_lock_or_connection_while_the_pdf_child_runs(self, scene: Scene) -> None:
        add_pdf(scene)
        samples: list[tuple[int, int, int, int]] = []

        def loader(payload: bytes) -> list[Page]:
            seen = activity(scene.url)
            samples.append(
                (
                    seen.idle_in_transaction,
                    seen.open_transactions,
                    seen.locks,
                    checked_out(built.engine),
                )
            )
            return [Page(1, "page text")]

        with built_service(scene.url, pdf_loader=loader) as built:
            built.service.run_once()

        assert samples == [(0, 0, 0, 0)]


class TestConcurrentWorkers:
    def test_several_workers_process_every_document_exactly_once(self, scene: Scene) -> None:
        from tests.ingestion_support import run_together

        documents = [add_text(scene, LONG_TEXT, filename=f"f{i}.txt") for i in range(8)]

        def worker(index: int) -> list[Outcome]:
            seen: list[Outcome] = []
            with built_service(scene.url) as built:
                while True:
                    outcome = built.service.run_once()
                    if outcome is Outcome.IDLE:
                        return seen
                    seen.append(outcome)

        results = run_together(4, worker)

        outcomes = [item for result in results for item in result]  # type: ignore[union-attr]
        assert all(isinstance(result, list) for result in results)
        assert outcomes == [Outcome.READY] * 8
        counts = {chunk_count(scene.url, doc) for doc, _ in documents}
        assert len(counts) == 1 and counts.pop() > 1  # every document has one full set
        for doc, job in documents:
            assert document_state(scene.url, doc)["status"] == "ready"
            assert job_state(scene.url, job)["attempts"] == 1
