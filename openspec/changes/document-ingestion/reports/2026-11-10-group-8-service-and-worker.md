# Group 8: ingestion service, heartbeat and worker

Branch `feature/document-ingestion`. Tasks 8.1, 8.2, 8.3 and 8.4 (the heartbeat of 8.4 is part of the service of 8.1 and was built with it). No endpoint (group 9), no change to the API contract, no migration applied to the development database.

## What was added
- `app/services/ingestion_service.py` (tasks 8.1 and 8.4)
  - `IngestionService.run_once()`: claims one job (own short session, committed), then `process`. `sweep()`: the repository sweep in its own session.
  - `process`: starts a heartbeat thread, runs the phases (checkpoint, load, checkpoint, chunk, embed in batches with a checkpoint before each batch, checkpoint, final transaction) and always stops and joins the thread. Parsing and embedding run with **no session, transaction, lock or pooled connection**.
  - Every database step (claim, one renewal, final write, failure mark, sweep) opens and closes its own session.
  - Outcomes: `READY`, `FAILED` (document `failed` with a code and its fixed message), `LOST` (the worker no longer owns the job: nothing written), `ABANDONED` (the database failed at the end: nothing is marked, the lease expires and the job is retried or swept), `IDLE`.
  - **Lease** (`_Lease`): the heartbeat renews every `lease / 3` seconds (one fenced `UPDATE`, own session, committed at once); the main thread renews at every checkpoint. A renewal that finds no row sets the lost flag. A renewal that raises (database unreachable) sets it once a whole lease has passed without a confirmed renewal. Nothing is renewed after the job deadline or after the loss. A lease that really expired cannot be revived (the repository fence).
  - **Deadline**: `INGESTION_JOB_DEADLINE_SECONDS` per attempt, checked at every checkpoint (the monotonic clock is injectable); past it the document fails with `PROCESSING_TIMEOUT`.
  - **Failure mapping** (by type, never by text): `DocumentLoadError` keeps its code; `TooManyChunksError` -> `TOO_MANY_CHUNKS`; embedder errors, a wrong number of vectors and invalid vectors -> `EMBEDDING_FAILED` (checked per batch, so the first bad batch ends the job); no chunks -> `NO_EXTRACTABLE_TEXT`; chunk that cannot fit, unsupported platform, unknown content type, a `ValueError` of the repository and any other exception -> `PROCESSING_FAILED`. The log has the job id, document id, attempt and outcome or code; exception text, file names and content are never logged.
  - `IngestionLimits.from_settings` (lease, deadline, attempts, batch, chunk cap, character cap, job age, PDF limits).
- `app/worker.py` (task 8.2): `python -m app.worker`.
  - Start-up refuses (exit code 2, a fixed reason in the log, no paths) outside Linux, with an embedder configuration that is not allowed, or when the embedder start-up probe fails (missing model, wrong dimension). There is no fallback.
  - `WorkerLoop`: sweep at start and every 60 s; claim and process; no pause between jobs; idle back-off 0.5 s doubling to 5 s; an unexpected error is logged by type only and the loop goes on; SIGINT and SIGTERM stop it after the current job and the previous handlers are restored.
  - The worker engine sets `statement_timeout` (60 s) and `idle_in_transaction_session_timeout` (30 s) as connection options (`create_db_engine` takes two optional keyword arguments; the API engine is untouched until group 9).
- `docker-compose.yml`: the `profiles: ["worker"]` line was removed, so a plain `docker compose up` starts the worker (task 8.2). I did not start the stack; `docker compose config --services` lists `db backend frontend worker`.
- Tests: `tests/service_support.py` (builders, a hook embedder, a probe of other sessions' activity), `test_ingestion_service.py` (50), `test_ingestion_heartbeat.py` (8), `test_ingestion_end_to_end.py` (3), `test_worker_process.py` (2, Linux only), `test_engine_timeouts.py` (3), `tests/unit/test_worker_loop.py` (19).

## TDD evidence
- Failing run before the implementation (commit `ca3673e`): 5 collection errors, `ModuleNotFoundError: No module named 'app.services.ingestion_service'`.
- Engine options, failing first: `TypeError: unexpected keyword argument 'statement_timeout_seconds'` (2 failed, 1 passed), then 3 passed.
- After: 85 tests of the group pass in the Linux worker image against PostgreSQL (50 + 8 + 3 + 2 + 3 + 19); on the Windows host the 2 process tests and the PDF end-to-end test are skipped with a reason (the worker needs Linux).

## Critical controls and how they are proved
| Control | Test |
|---|---|
| Concurrent claim by several workers | 4 services in threads release 8 documents: 8 `READY`, every document has one full set of chunks, `attempts = 1` for all |
| Lease renewal during slow inference | 3 s lease, a PDF child that blocks 4.5 s and a 0.5 s per batch embedder: the heartbeat keeps the lease, a poller trying to claim every 0.3 s never gets the job, `attempts = 1`, one set of chunks, no transaction stuck for more than one second |
| Lost lease, no writes | the lease is expired by SQL while the worker is blocked; another worker completes the job; the stale worker ends `LOST` at the next checkpoint (many batches or one), nothing of it is written |
| Interrupted worker and recovery | a real `python -m app.worker` process is killed (SIGKILL) in the middle of a job; another real worker completes it: `attempts = 2`, consecutive chunk indexes, no duplicates |
| Retries and exhaustion | a dead worker's job is claimed again and finishes (attempts 2); the third attempt is allowed; a job with 3 attempts is not claimed and the sweep fails it as `PROCESSING_INTERRUPTED` |
| `DELETE` while processing | between phases and during the last batch: `LOST`, no chunks, no rows, no error |
| Extraction or embedding failure | every code of the catalogue that a worker can set, with its fixed message, the bytes erased and no chunks; `PROCESSING_INTERRUPTED` and `JOB_EXPIRED` come from the service sweep |
| Atomic final transaction | `ready`, count, chunks and erased bytes in one repository transaction (group 7); here a refused confirmation is `LOST` and a database error is `ABANDONED` with the document untouched |
| Payload erased at the end | every terminal outcome leaves `payload IS NULL` and no lease |
| Nothing held while working | `pg_stat_activity`, `pg_locks` and the pool are inspected from a separate connection while a slow embedder and a slow PDF child run: no open transaction, no lock, no checked-out connection |
| No sensitive text in logs or rows | markers in the exception, file name, content, a database error and a loop error never appear in the log (captured at DEBUG, with `exc_info`) nor in `error_message`; identifiers do appear |
| Task 8.3 without HTTP | a text file and (on Linux) a generated PDF are ingested with the fake embedder; `find_similar` returns the chunks with page numbers to the enrolled student and to the owner; failed and pending documents, even with matching chunks, are never returned |

## Mutation checks
45 mutations (30 in the service, 13 in the worker, 2 in the engine options), each run against the test files of its area; the Windows host lost the ability to launch the virtual environment half-way (see below), so the second pass ran in the Linux image.
- Killed: heartbeat never started, renewal refused does not set the lost flag, deadline not checked, renewal after the deadline, unreachable database never (or too late) detected, heartbeat interval equal to the lease, thread not joined, no checkpoint before loading, after loading, per batch or before the final write, empty chunks, vector count and vector validation, embedder error mapping, too-many-chunks mapping, loader code, chunk cap, text limit, unknown content type, unconfirmed final write or failure mark reported as success, database error at the end, claim with one attempt, sweep age; in the worker: back-off growth, cap and reset, sweep at start and interval, errors end the loop, error text logged, start outside Linux, signals, handlers restored, start-up probe, exit code of a refusal, idle without back-off; engine timeouts in the wrong unit (both).
- First pass left 12 survivors; closed by new tests: stricter bound on the unreachable-database test, a test where the worker is blocked past the deadline and must not be renewed, a count of renewals at the four phase boundaries, fail-fast checks on many batches for invalid and missing vectors, a repository refusal test (the former `EMBEDDING_FAILED` mapping was unreachable; it is now `PROCESSING_FAILED` and tested), and refusal tests that cannot hang because the stop event is already set.
- Accepted as equivalent (2): renewing although the lost flag is already set (the repository answers "no row" again) and not checking the lost flag before the deadline check at a checkpoint (the next statement of the same method checks it).

## Quality gates
The host's virtual environment became unrunnable during the group (see "Deviations"), so the gates ran in the Linux worker image with the locked environment (`uv sync --frozen --extra ingestion`), the repository mounted read-only:
- `ruff check --no-cache`, `ruff format --no-cache --check`, `mypy --strict app tests` (149 files) clean; `pip-audit` of the exported lock: no known vulnerabilities (no dependency changed).
- Full backend suite in the Linux image with PostgreSQL: see "Full run".
- `openspec validate document-ingestion --strict` valid, `--all --strict` 15 of 15. Strict xfail of the real-application contract test still `xfailed` (routes arrive in group 9).
- Frontend: not run (contract and types untouched).

## Full run
Linux worker image with PostgreSQL (repository mounted read-only): **1400 passed, 1 skipped (AES), 16 deselected (`realmodel`), 1 xfailed**, coverage of `app` **98 %** (`ingestion_service.py` 99 %, `worker.py` 99 %, `repositories/` 98 to 99 %). The earlier Windows figures (1209 passed, 107 skipped) are not comparable: the Linux-only PDF tests run here. The development database `asistenteia` stays at revision `0004`; migration `0005` was not applied to it. The test database ends without tables.

## Deviations and notes
1. **Host environment.** Midway, Windows Application Control began to block every executable of the project's virtual environment (`os error 4551`). I did not try to get around the policy: tests, mutations and gates moved to the Linux image (`asistenteia-worker`) with the test database reached through `host.docker.internal`. The first mutation pass ran on the host; the survivors and the invalidated entries (spawn failures that looked like kills) were rerun in Linux.
2. **Heartbeat timing.** A task 8.4 heartbeat is inside the service (task 8.1); both were built and tested together.
3. **Engine timeouts.** `create_db_engine` got two optional parameters; only the worker uses them. Applying the API timeouts (15 s and 30 s) is left to group 9 with the endpoints.
4. **`ABANDONED`.** A database failure at the final write or at the failure mark does not mark the document failed (the database is not trustworthy); the lease expires and the job is retried, or swept after the last attempt.
5. **Process tests.** The worker refuses to start outside Linux, so the two process tests and the PDF end-to-end test are skipped on Windows with a reason and run in CI and in the worker image.
6. **Unrelated untracked files.** Two untracked files appeared in the repository root during the group (`AsistenteIA_Flujo_SDD_OpenSpec_SpecBoot.md` and `.docx`); I did not touch them.
