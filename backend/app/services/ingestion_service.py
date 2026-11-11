"""Processing of one ingestion job: load, chunk, embed, then one fenced final transaction.

Change 6, tasks 8.1 and 8.4; design D1, D9, A2, A3, A4, A9 and A10.

* **No database resource is held while working.** Every database step (claim, one renewal, the
  final write, the failure mark, the sweep) opens its own short session and closes it. Parsing and
  embedding run with no session, transaction, lock or pooled connection.
* **Lease.** A heartbeat thread renews the lease every `lease / 3` seconds in its own short
  transaction, and the main thread renews at every phase boundary and after every batch. A renewal
  that finds no row (lease expired, job claimed by another worker, document deleted) sets the
  *lost* flag; the worker then stops at the next checkpoint and writes nothing. Renewals that fail
  because the database cannot be reached count as lost once a whole lease passes without a
  successful one. Nothing is renewed after the job deadline.
* **Failures.** Every failure becomes one code of the closed catalogue and its fixed message; the
  text of an exception is never stored or logged (only its type).
* **Fencing.** Every write goes through `IngestionJobRepository`, conditioned on the claim token
  and an unexpired lease; a `False` result means "stop quietly".
"""

import logging
import threading
import time
from collections.abc import Callable, Sequence
from dataclasses import dataclass
from enum import StrEnum
from typing import TYPE_CHECKING

from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session, sessionmaker

from app.core.vector_validation import InvalidSearchInputError, validate_embedding
from app.models.ingestion import DocumentErrorCode
from app.rag.chunker import Chunk, ChunkingError, Page, TooManyChunksError, chunk_pages
from app.rag.embedder import Embedder, EmbeddingError
from app.rag.loaders import (
    DocumentLoadError,
    PdfLimits,
    UnsupportedPlatformError,
    load_markdown,
    load_pdf,
    load_text,
)
from app.repositories.ingestion_job_repository import (
    ClaimedJob,
    IngestionJobRepository,
    SweepResult,
)

if TYPE_CHECKING:
    from app.core.config import WorkerSettings

logger = logging.getLogger(__name__)

_PDF = "application/pdf"
_MARKDOWN = "text/markdown"
_TEXT = "text/plain"


@dataclass(frozen=True)
class IngestionLimits:
    """Every number the service needs (the worker builds it from `WorkerSettings`)."""

    lease_seconds: int
    deadline_seconds: int
    max_attempts: int
    batch_size: int
    max_chunks: int
    max_chars: int
    max_age_hours: int
    pdf: PdfLimits | None = None
    heartbeat_interval_seconds: float | None = None

    @property
    def heartbeat_interval(self) -> float:
        """Seconds between heartbeat renewals: a third of the lease unless set explicitly."""
        if self.heartbeat_interval_seconds is not None:
            return self.heartbeat_interval_seconds
        return self.lease_seconds / 3

    @classmethod
    def from_settings(cls, settings: "WorkerSettings") -> "IngestionLimits":
        return cls(
            lease_seconds=settings.ingestion_lease_seconds,
            deadline_seconds=settings.ingestion_job_deadline_seconds,
            max_attempts=settings.ingestion_max_attempts,
            batch_size=settings.ingestion_batch_size,
            max_chunks=settings.max_chunks_per_document,
            max_chars=settings.max_extracted_chars,
            max_age_hours=settings.ingestion_job_max_age_hours,
            pdf=PdfLimits.from_settings(settings),
        )


class Outcome(StrEnum):
    """What one `run_once` did."""

    IDLE = "idle"  # nothing to claim
    READY = "ready"
    FAILED = "failed"  # the document is `failed` with a code
    LOST = "lost"  # the worker lost the job (lease, deletion, another worker): nothing written
    ABANDONED = "abandoned"  # the database failed at the end: the lease expires and it is retried


class _LeaseLost(Exception):
    """The worker no longer owns the job; stop without writing."""


class _Failure(Exception):
    """The job failed with this code of the closed catalogue."""

    def __init__(self, code: DocumentErrorCode) -> None:
        super().__init__(code.value)
        self.code = code


class _Lease:
    """Renews the lease from a heartbeat thread and from the main thread; tracks loss."""

    def __init__(
        self,
        factory: sessionmaker[Session],
        job: ClaimedJob,
        limits: IngestionLimits,
        deadline: float,
        clock: Callable[[], float],
    ) -> None:
        self._factory = factory
        self._job = job
        self._limits = limits
        self._deadline = deadline
        self._clock = clock
        self._renewing = threading.Lock()
        self._last_confirmed = clock()
        self._stopped = threading.Event()
        self.lost = threading.Event()
        self._thread = threading.Thread(target=self._beat, name="ingestion-heartbeat", daemon=True)

    def start(self) -> None:
        self._thread.start()

    def stop(self) -> None:
        self._stopped.set()
        self._thread.join()

    def _beat(self) -> None:
        while not self._stopped.wait(self._limits.heartbeat_interval):
            self.renew()

    def renew(self) -> None:
        """One fenced renewal in its own short transaction; never after the deadline."""
        with self._renewing:
            if self.lost.is_set() or self._clock() >= self._deadline:
                return
            try:
                with self._factory() as session:
                    renewed = IngestionJobRepository(session).renew(
                        self._job.job_id, self._job.token, self._limits.lease_seconds
                    )
                    session.commit()
            except Exception:  # noqa: BLE001 - the text of a database error is never kept
                if self._clock() - self._last_confirmed >= self._limits.lease_seconds:
                    self.lost.set()
                return
            if renewed:
                self._last_confirmed = self._clock()
            else:
                self.lost.set()

    def checkpoint(self) -> None:
        """Between phases and batches: stop if the job was lost or is out of time, else renew."""
        if self.lost.is_set():
            raise _LeaseLost
        if self._clock() >= self._deadline:
            raise _Failure(DocumentErrorCode.PROCESSING_TIMEOUT)
        self.renew()
        if self.lost.is_set():
            raise _LeaseLost


class IngestionService:
    """Claims jobs from the queue and turns their files into searchable chunks."""

    def __init__(
        self,
        session_factory: sessionmaker[Session],
        embedder: Embedder,
        limits: IngestionLimits,
        *,
        pdf_loader: Callable[[bytes], list[Page]] | None = None,
        clock: Callable[[], float] = time.monotonic,
    ) -> None:
        self._factory = session_factory
        self._embedder = embedder
        self._limits = limits
        self._pdf_loader = pdf_loader
        self._clock = clock

    # --- queue ------------------------------------------------------------------------------

    def run_once(self) -> Outcome:
        """Claim one job and process it; `IDLE` when nothing can be claimed."""
        with self._factory() as session:
            job = IngestionJobRepository(session).claim(
                self._limits.lease_seconds, self._limits.max_attempts
            )
            session.commit()
        if job is None:
            return Outcome.IDLE
        return self.process(job)

    def sweep(self) -> SweepResult:
        """Fail interrupted and expired jobs and erase the bytes of terminal documents."""
        with self._factory() as session:
            result = IngestionJobRepository(session).sweep(
                self._limits.max_attempts, self._limits.max_age_hours
            )
            session.commit()
        if result.interrupted or result.expired or result.erased:
            logger.info(
                "ingestion sweep: interrupted=%d expired=%d erased=%d",
                result.interrupted,
                result.expired,
                result.erased,
            )
        return result

    # --- one job ----------------------------------------------------------------------------

    def process(self, job: ClaimedJob) -> Outcome:
        """Run every phase of a claimed job; never raises for a processing problem."""
        lease = _Lease(
            self._factory,
            job,
            self._limits,
            self._clock() + self._limits.deadline_seconds,
            self._clock,
        )
        lease.start()
        try:
            outcome = self._run(job, lease)
        finally:
            lease.stop()
        logger.info(
            "ingestion job %s of document %s attempt %d: %s",
            job.job_id,
            job.document_id,
            job.attempts,
            outcome.value,
        )
        return outcome

    def _run(self, job: ClaimedJob, lease: _Lease) -> Outcome:
        try:
            try:
                lease.checkpoint()
                pages = self._load(job)
                lease.checkpoint()
                chunks = chunk_pages(pages, self._embedder, max_chunks=self._limits.max_chunks)
                if not chunks:
                    raise _Failure(DocumentErrorCode.NO_EXTRACTABLE_TEXT)
                vectors = self._embed(chunks, lease)
                lease.checkpoint()
            except (_LeaseLost, _Failure):
                raise
            except DocumentLoadError as error:
                raise _Failure(error.code) from None
            except TooManyChunksError:
                raise _Failure(DocumentErrorCode.TOO_MANY_CHUNKS) from None
            except (ChunkingError, UnsupportedPlatformError):
                raise _Failure(DocumentErrorCode.PROCESSING_FAILED) from None
            except Exception as error:  # noqa: BLE001 - mapped by type; the text is never kept
                logger.warning("ingestion job %s: unexpected %s", job.job_id, type(error).__name__)
                raise _Failure(DocumentErrorCode.PROCESSING_FAILED) from None
            return self._finish(job, chunks, vectors)
        except _LeaseLost:
            return Outcome.LOST
        except _Failure as failure:
            return self._fail(job, failure.code)
        except ValueError:  # the repository refused the input before any statement (a bug)
            return self._fail(job, DocumentErrorCode.PROCESSING_FAILED)
        except SQLAlchemyError as error:
            logger.warning("ingestion job %s: database error %s", job.job_id, type(error).__name__)
            return Outcome.ABANDONED

    def _load(self, job: ClaimedJob) -> list[Page]:
        if job.content_type == _PDF:
            if self._pdf_loader is not None:
                return self._pdf_loader(job.payload)
            if self._limits.pdf is None:
                raise UnsupportedPlatformError
            return load_pdf(job.payload, self._limits.pdf)
        if job.content_type == _MARKDOWN:
            return load_markdown(job.payload, max_chars=self._limits.max_chars)
        if job.content_type == _TEXT:
            return load_text(job.payload, max_chars=self._limits.max_chars)
        raise _Failure(DocumentErrorCode.PROCESSING_FAILED)

    def _embed(self, chunks: Sequence[Chunk], lease: _Lease) -> list[list[float]]:
        vectors: list[list[float]] = []
        size = self._limits.batch_size
        for start in range(0, len(chunks), size):
            lease.checkpoint()
            batch = chunks[start : start + size]
            try:
                produced = self._embedder.embed([chunk.text for chunk in batch])
                if len(produced) != len(batch):
                    raise _Failure(DocumentErrorCode.EMBEDDING_FAILED)
                vectors.extend(validate_embedding(vector) for vector in produced)
            except (EmbeddingError, InvalidSearchInputError):
                raise _Failure(DocumentErrorCode.EMBEDDING_FAILED) from None
        return vectors

    # --- the two terminal writes ------------------------------------------------------------

    def _finish(
        self, job: ClaimedJob, chunks: Sequence[Chunk], vectors: Sequence[Sequence[float]]
    ) -> Outcome:
        """The final transaction: `ready`, chunks and erased bytes, or nothing at all."""
        with self._factory() as session:
            confirmed = IngestionJobRepository(session).complete(
                job.job_id, job.token, chunks, vectors
            )
            if not confirmed:
                session.rollback()
                return Outcome.LOST
            session.commit()
        return Outcome.READY

    def _fail(self, job: ClaimedJob, code: DocumentErrorCode) -> Outcome:
        """Mark the document `failed` with `code` and erase the bytes (fenced)."""
        try:
            with self._factory() as session:
                marked = IngestionJobRepository(session).mark_failed(job.job_id, job.token, code)
                if not marked:
                    session.rollback()
                    return Outcome.LOST
                session.commit()
        except SQLAlchemyError as error:
            logger.warning("ingestion job %s: database error %s", job.job_id, type(error).__name__)
            return Outcome.ABANDONED
        logger.info("ingestion job %s of document %s failed: %s", job.job_id, job.document_id, code)
        return Outcome.FAILED
