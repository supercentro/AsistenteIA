# Group 7: repositories and queue

Branch `feature/document-ingestion`. Tasks 7.1, 7.2, 7.3 and 7.4 (the file lists 7.4 before 7.3). Two repositories and two domain errors; no endpoint, service or worker code (groups 8 and 9).

## What was added
- `app/core/errors.py`: `DocumentQuotaExceededError` (`409`, `DOCUMENT_QUOTA_EXCEEDED`) and `IngestionQueueFullError` (`503`, `INGESTION_QUEUE_FULL`, `Retry-After`), fixed messages.
- `app/repositories/document_repository.py` (task 7.1)
  - `add_with_job`: one transaction, the caller commits. Order of locks (design A5): the subject row `FOR UPDATE` filtered by teacher (this is also the `404`: `NotFoundError`, identical for unknown, other teacher's and student), count of the subject's documents of any status (`>= max` gives the quota error), then the global `pg_advisory_xact_lock(ADMISSION_LOCK_KEY)`, then count and sum of the bytes of unfinished jobs (`payload IS NOT NULL`); `>= queue_max` or `bytes + new > max` gives the queue error. Then the document (`pending`, `size_bytes`) and the job with the bytes.
  - `list_for_teacher` (`None` when the subject is not owned, newest first), `get_for_teacher`, `delete_for_teacher`: every one needs the teacher and the subject; there is no unscoped read. `AdmissionLimits.from_settings`.
  - `add_chunks`: the only chunk writer, called from the fenced final transaction.
- `app/repositories/ingestion_job_repository.py` (tasks 7.2, 7.3, 7.4)
  - `claim(lease, max_attempts)`: picks the oldest job that holds bytes, has an active document, is available, has a free or expired lease and has attempts left (`FOR UPDATE OF d SKIP LOCKED`), then updates the job with those conditions checked **again**, sets the token, the lease and `attempts + 1`, and the document becomes `processing`.
  - `renew`: one fenced `UPDATE`; `mark_failed`; `complete` (final transaction); `erase_payload`; `sweep` (interrupted, expired, bytes of terminal documents; batches of 100, `SKIP LOCKED`, ordinary statements). `new_claim_token`.
  - Fence: token and `locked_until > clock_timestamp()` (not `now()`: a long transaction cannot extend an expired lease). For multi-statement writes the document row is locked first, then the job row, and both are checked again under the lock. Terminal documents are never updated.
  - **Lock order document then job**, the same as `DELETE FROM documents` (which locks the document and cascades to the job). The first design of the fenced write locked the job first; I changed it before writing code because a delete and a worker write could have deadlocked (the worker holding the job row and wanting the document, the delete holding the document and wanting the job). Renewals touch only the job row and cannot form that cycle.
  - `complete` validates before any statement (no chunks, embeddings not equal to chunks, indexes not consecutive from zero, `validate_embedding` for every vector) and binds the validated single-precision values; `ready`, `chunks_count`, the chunks and the erased bytes are one transaction of the caller.

## TDD evidence
Tests written and committed before the code (`8723900`): `test_document_repository.py`, `test_ingestion_job_repository.py`, `test_ingestion_lease_fencing.py`, `test_ingestion_final_transaction.py`, helper `tests/ingestion_support.py`.
- **Failing run before the implementation**: 4 collection errors, `ModuleNotFoundError: No module named 'app.repositories.ingestion_job_repository'` (and `document_repository`).
- **After**: 139 passed in these four files.
- The tests run against the isolated PostgreSQL test database, with real concurrency (threads with their own connections released at the same instant): 49 documents plus 12 uploads leave exactly 50; 10 subjects competing for the last queue slot and for the last bytes accept exactly one; 72 uploads from 6 subjects over 4 rounds and mixed uploads and deletions produce no deadlock; a lock on the subject row delays only uploads to that subject; the global lock is the advisory one (a held advisory lock blocks any upload).

## Mutation checks (per statement and per limit)
About 50 mutations of the two repositories, each run against the four test files:
- Killed: subject lock, teacher scope in admission, quota (off by one and removed), global lock, queue (off by one and removed), bytes (off by one, new file not counted), finished jobs counted as queued, list/get/delete scopes, ordering, stored size and bytes, claim filters (bytes, availability, order, attempts, lease, recheck), `SKIP LOCKED` in claim and sweep (a mutation that waits for a lock hangs the test and is stopped by the harness), attempts counter, document status, renew without token or without lease, fence accepting terminal documents, input checks of `complete`, chunk count, bytes and lease kept on the terminal path, sweep expiry reversed, attempts off by one, valid lease ignored, bytes of failed documents.
- First pass left 15 survivors; resolved by new tests: an orphaned job without bytes, a locked document and an exhausted job must not hide a claimable one; availability order checked on six shuffled jobs; a deterministic test that relaxes the candidate query (through a cursor event) and proves the update refuses a leased or exhausted job; the sweep does not wait for a locked document; invalid input issues no statement.
- Accepted as equivalent: removing the token or the lease condition from **only one** of the two checks of the fence (the pre-check before the document lock and the check under the job lock). Each alone is covered by the other by design; removing **both** is detected (tested). The pre-check exists so a stale worker does not take a document lock.
- Found while mutating: a redundant filter in `delete_for_teacher` (the subject was filtered twice); removed.

## Quality gates
`ruff check --no-cache`, `ruff format --check`, `mypy --strict app tests` clean; `pip-audit` no known vulnerabilities (no dependency change); frontend gates not run (contract and types untouched); `openspec validate document-ingestion --strict` valid, `--all --strict` 15 of 15. Strict xfail of the real-application contract test still `xfailed` (routes arrive in group 9).

## Full run
Backend suite on the isolated test database: **1209 passed, 107 skipped (Linux-only PDF tests, AES), 16 deselected (`realmodel`), 1 xfailed**; coverage of `app` 92 % on this Windows host (the skipped PDF tests lower it; CI on Linux runs them); `repositories/` 99 %, `document_repository.py` 98 %, `ingestion_job_repository.py` 98 %, `core/errors.py` 100 %. `asistenteia_test` has no tables afterwards; the development database `asistenteia` is at revision `0004`; migration `0005` was not applied to it.

## Deviations and notes
1. Task order in `tasks.md` lists 7.4 before 7.3; both were done together.
2. The repositories never commit; the caller (service and worker, groups 8 and 9) owns each short transaction. The heartbeat must call `renew` in its own session and commit at once; a test proves a renewal is one write statement that leaves no lock or open transaction.
3. `erase_payload` alone leaves a `processing` document without bytes if a worker called it outside a terminal path; the sweep fails such a document as `PROCESSING_INTERRUPTED` once its lease expires (tested).
4. `claim` can lose a race inside the narrow window between its two statements; the second statement re-checks and the method returns `None` or tries again (three times). This is tested by relaxing the first statement.
5. A cancelled worker has no special path: every fenced method returns `False`, which the worker treats as "stop quietly".
6. The mutation harness stopped hung test processes on Windows with `taskkill`; one stray `pytest` process of an earlier run had to be stopped by hand (no file was left mutated).
