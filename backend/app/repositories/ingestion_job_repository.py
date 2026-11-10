# ruff: noqa: S608 - the SQL fragments joined below are constants of this module, never input
"""The persistent ingestion queue (change 6, tasks 7.2, 7.3 and 7.4), design D1, A2, A3, A7.

Claim, lease, fencing and sweep. The caller owns the transaction: nothing here commits, so the
worker keeps every transaction short (claim, one renewal, the final write) and holds no database
resource while it parses or embeds.

Fencing rule: every write of a worker is conditioned on `locked_by = :token AND locked_until >
clock_timestamp()` and, for the multi-statement writes, is made holding row locks. A stale token,
a deleted job, an expired lease or a terminal document finds no row and writes nothing (the method
returns `False`). `clock_timestamp()` is used instead of `now()` so a long transaction cannot
extend a lease that has really expired.

Lock order is always **document row, then job row**, the same as `DELETE FROM documents` (which
locks the document and then cascades to the job), so a delete and a worker write cannot deadlock.
The fixed SQL fragments below are written here and never built from input; every value is bound.
"""

import secrets
import uuid
from collections.abc import Sequence
from dataclasses import dataclass
from typing import Any

from sqlalchemy import text
from sqlalchemy.orm import Session

from app.core.vector_validation import validate_embedding
from app.models.ingestion import DOCUMENT_ERROR_MESSAGES, DocumentErrorCode
from app.rag.chunker import Chunk
from app.repositories.document_repository import DocumentRepository

_SWEEP_BATCH = 100
_CLAIM_ATTEMPTS = 3
_TOKEN_BYTES = 32  # 43 URL-safe characters, well under the column width

# A lease that has not expired (or is absent): the job may be claimed or swept.
_LEASE_FREE = "(j.locked_until IS NULL OR j.locked_until <= clock_timestamp())"
_ACTIVE = "d.status IN ('pending', 'processing')"


def new_claim_token() -> str:
    """A fresh random claim token: the fencing token of one attempt."""
    return secrets.token_urlsafe(_TOKEN_BYTES)


@dataclass(frozen=True)
class ClaimedJob:
    """A job claimed by a worker, with the bytes to process and the fencing token."""

    job_id: uuid.UUID
    document_id: uuid.UUID
    subject_id: uuid.UUID
    token: str
    attempts: int
    payload: bytes
    filename: str
    content_type: str


@dataclass(frozen=True)
class SweepResult:
    """How many jobs the sweep failed as interrupted, failed as expired, and cleaned of bytes."""

    interrupted: int
    expired: int
    erased: int


class IngestionJobRepository:
    """Claim, renew, finish and sweep ingestion jobs."""

    def __init__(self, session: Session) -> None:
        self._session = session

    # --- claim -----------------------------------------------------------------------------

    def claim(self, lease_seconds: int, max_attempts: int) -> ClaimedJob | None:
        """Claim the oldest claimable job with a new token and lease, or return `None`.

        Claimable: it holds bytes, its document is `pending` or `processing`, it is available, its
        lease is empty or expired and it has attempts left. The document becomes `processing`
        in the same transaction. Two workers never get the same job (`SKIP LOCKED`).
        """
        token = new_claim_token()
        for _ in range(_CLAIM_ATTEMPTS):
            candidate = self._session.execute(
                text(
                    "SELECT d.id AS document_id, j.id AS job_id "
                    "FROM documents d JOIN ingestion_jobs j ON j.document_id = d.id "
                    f"WHERE {_ACTIVE} AND j.payload IS NOT NULL "
                    "AND j.available_at <= clock_timestamp() "
                    f"AND {_LEASE_FREE} AND j.attempts < :max_attempts "
                    "ORDER BY j.available_at, j.created_at, j.id "
                    "LIMIT 1 FOR UPDATE OF d SKIP LOCKED"
                ),
                {"max_attempts": max_attempts},
            ).first()
            if candidate is None:
                return None
            # The conditions are checked again on the job row: another worker may have claimed it
            # between the snapshot of the first statement and the document lock.
            claimed = self._session.execute(
                text(
                    "UPDATE ingestion_jobs j SET locked_by = :token, "
                    "locked_until = clock_timestamp() + make_interval(secs => :lease), "
                    "attempts = j.attempts + 1, updated_at = clock_timestamp() "
                    "WHERE j.id = :job AND j.payload IS NOT NULL "
                    f"AND {_LEASE_FREE} AND j.attempts < :max_attempts "
                    "RETURNING j.id, j.document_id, j.payload, j.attempts"
                ),
                {
                    "token": token,
                    "lease": lease_seconds,
                    "job": candidate.job_id,
                    "max_attempts": max_attempts,
                },
            ).first()
            if claimed is None:
                continue
            document = self._session.execute(
                text(
                    "UPDATE documents SET status = 'processing' "
                    "WHERE id = :doc AND status IN ('pending', 'processing') "
                    "RETURNING subject_id, filename, content_type"
                ),
                {"doc": claimed.document_id},
            ).first()
            if document is None:  # pragma: no cover - cannot happen: the document row is locked
                return None
            return ClaimedJob(
                job_id=claimed.id,
                document_id=claimed.document_id,
                subject_id=document.subject_id,
                token=token,
                attempts=claimed.attempts,
                payload=bytes(claimed.payload),
                filename=document.filename,
                content_type=document.content_type,
            )
        return None

    # --- fenced writes ---------------------------------------------------------------------

    def renew(self, job_id: uuid.UUID, token: str, lease_seconds: int) -> bool:
        """Extend the lease of a job still owned with a valid lease; one statement, no lock kept."""
        row = self._session.execute(
            text(
                "UPDATE ingestion_jobs SET "
                "locked_until = clock_timestamp() + make_interval(secs => :lease), "
                "updated_at = clock_timestamp() "
                "WHERE id = :job AND locked_by = :token AND locked_until > clock_timestamp() "
                "AND payload IS NOT NULL RETURNING id"
            ),
            {"job": job_id, "token": token, "lease": lease_seconds},
        ).first()
        return row is not None

    def mark_failed(self, job_id: uuid.UUID, token: str, code: DocumentErrorCode) -> bool:
        """Fail the document with `code` and its fixed message and erase the bytes (fenced)."""
        owned = self._lock_owned(job_id, token)
        if owned is None:
            return False
        self._session.execute(
            text(
                "UPDATE documents SET status = 'failed', error_code = :code, "
                "error_message = :message, chunks_count = 0 WHERE id = :doc"
            ),
            {
                "doc": owned.document_id,
                "code": code.value,
                "message": DOCUMENT_ERROR_MESSAGES[code],
            },
        )
        self._release(job_id)
        return True

    def complete(
        self,
        job_id: uuid.UUID,
        token: str,
        chunks: Sequence[Chunk],
        embeddings: Sequence[Sequence[float]],
    ) -> bool:
        """The final transaction: chunks, count, `ready` and erased bytes, all or nothing.

        Validation of the input happens before any statement. Returns `False`, having written
        nothing, when the fence rejects the worker (stale token, expired lease, deleted job or
        terminal document). A database error propagates and the caller's rollback undoes
        every statement of this method.
        """
        if not chunks:
            raise ValueError("a document without chunks cannot become ready")
        if len(chunks) != len(embeddings):
            raise ValueError("every chunk needs exactly one embedding")
        if [chunk.index for chunk in chunks] != list(range(len(chunks))):
            raise ValueError("chunk indexes must be consecutive from zero")
        validated = [validate_embedding(embedding) for embedding in embeddings]
        owned = self._lock_owned(job_id, token)
        if owned is None:
            return False
        self._session.execute(
            text(
                "UPDATE documents SET status = 'ready', chunks_count = :count, "
                "error_code = NULL, error_message = NULL WHERE id = :doc"
            ),
            {"doc": owned.document_id, "count": len(chunks)},
        )
        DocumentRepository(self._session).add_chunks(
            owned.document_id, owned.subject_id, chunks, validated
        )
        self._release(job_id)
        return True

    def erase_payload(self, job_id: uuid.UUID, token: str) -> bool:
        """Erase the bytes of an owned job (fenced); the lease is cleared with them."""
        if self._lock_owned(job_id, token) is None:
            return False
        self._release(job_id)
        return True

    # --- sweep -----------------------------------------------------------------------------

    def sweep(self, max_attempts: int, max_age_hours: int) -> SweepResult:
        """Fail interrupted and expired jobs and erase bytes of terminal documents.

        Ordinary short statements only: no rewrite, no exclusive table lock, rows locked by a
        worker are skipped (`SKIP LOCKED`). Reclaiming file space is left to autovacuum.
        """
        interrupted = self._fail_where(
            "(j.attempts >= :max_attempts OR j.payload IS NULL)",
            f"{_LEASE_FREE}",
            DocumentErrorCode.PROCESSING_INTERRUPTED,
            {"max_attempts": max_attempts},
        )
        expired = self._fail_where(
            "j.created_at <= clock_timestamp() - make_interval(hours => :max_age)",
            f"{_LEASE_FREE}",
            DocumentErrorCode.JOB_EXPIRED,
            {"max_age": max_age_hours},
        )
        erased = self._session.execute(
            text(
                "WITH stale AS (SELECT j.id FROM ingestion_jobs j "
                "JOIN documents d ON d.id = j.document_id "
                "WHERE d.status IN ('ready', 'failed') AND j.payload IS NOT NULL "
                "ORDER BY j.created_at LIMIT :batch FOR UPDATE OF j SKIP LOCKED) "
                "UPDATE ingestion_jobs j SET payload = NULL, locked_by = NULL, "
                "locked_until = NULL, updated_at = clock_timestamp() "
                "FROM stale WHERE j.id = stale.id RETURNING j.id"
            ),
            {"batch": _SWEEP_BATCH},
        ).all()
        return SweepResult(interrupted=interrupted, expired=expired, erased=len(erased))

    def _fail_where(
        self, reason: str, lease: str, code: DocumentErrorCode, parameters: dict[str, Any]
    ) -> int:
        """Fail up to a batch of active documents whose job matches `reason` and `lease`."""
        victims = self._session.execute(
            text(
                "SELECT d.id AS document_id, j.id AS job_id "
                "FROM documents d JOIN ingestion_jobs j ON j.document_id = d.id "
                f"WHERE {_ACTIVE} AND {reason} AND {lease} "
                "ORDER BY j.created_at LIMIT :batch FOR UPDATE OF d SKIP LOCKED"
            ),
            {**parameters, "batch": _SWEEP_BATCH},
        ).all()
        failed = 0
        for victim in victims:
            # Checked again under the job row lock: a worker may have claimed it meanwhile.
            locked = self._session.execute(
                text(
                    "SELECT j.id FROM ingestion_jobs j JOIN documents d ON d.id = j.document_id "
                    f"WHERE j.id = :job AND {reason} AND {lease} FOR UPDATE OF j SKIP LOCKED"
                ),
                {**parameters, "job": victim.job_id},
            ).first()
            if locked is None:
                continue
            self._session.execute(
                text(
                    "UPDATE documents SET status = 'failed', error_code = :code, "
                    "error_message = :message, chunks_count = 0 WHERE id = :doc"
                ),
                {
                    "doc": victim.document_id,
                    "code": code.value,
                    "message": DOCUMENT_ERROR_MESSAGES[code],
                },
            )
            self._release(victim.job_id)
            failed += 1
        return failed

    # --- helpers ---------------------------------------------------------------------------

    def _lock_owned(self, job_id: uuid.UUID, token: str) -> "_Owned | None":
        """Lock the document row, then the job row, proving the fence; `None` if it fails."""
        job = self._session.execute(
            text(
                "SELECT document_id FROM ingestion_jobs "
                "WHERE id = :job AND locked_by = :token AND locked_until > clock_timestamp()"
            ),
            {"job": job_id, "token": token},
        ).first()
        if job is None:
            return None
        document = self._session.execute(
            text(
                f"SELECT d.subject_id FROM documents d WHERE d.id = :doc AND {_ACTIVE} FOR UPDATE"
            ),
            {"doc": job.document_id},
        ).first()
        if document is None:
            return None
        confirmed = self._session.execute(
            text(
                "SELECT id FROM ingestion_jobs "
                "WHERE id = :job AND locked_by = :token AND locked_until > clock_timestamp() "
                "FOR UPDATE"
            ),
            {"job": job_id, "token": token},
        ).first()
        if confirmed is None:
            return None
        return _Owned(document_id=job.document_id, subject_id=document.subject_id)

    def _release(self, job_id: uuid.UUID) -> None:
        """Erase the bytes and clear the lease of a job (terminal path)."""
        self._session.execute(
            text(
                "UPDATE ingestion_jobs SET payload = NULL, locked_by = NULL, locked_until = NULL, "
                "updated_at = clock_timestamp() WHERE id = :job"
            ),
            {"job": job_id},
        )


@dataclass(frozen=True)
class _Owned:
    document_id: uuid.UUID
    subject_id: uuid.UUID
