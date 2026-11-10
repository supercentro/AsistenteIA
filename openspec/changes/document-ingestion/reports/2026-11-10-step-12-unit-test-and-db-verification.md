# Group 12: unit tests and database state

Branch `feature/document-ingestion`. Task 12.1. No later group; migration `0005` was not applied to the development database.

## Environment
- The host virtual environment is blocked by Windows Application Control (see group 8), so every run used the Linux worker image (`asistenteia-worker:latest`, Python 3.12, locked environment with the `ingestion` group), the repository mounted read-only, and the guarded test database `asistenteia_test` of the project's PostgreSQL 15 + pgvector container, reached through `host.docker.internal`. `DATABASE_URL` is set only to satisfy the guard (the development database name); no test connects to it.
- Targeted tests first (the files of this group, then the groups 7 to 11 files), then the full backend suite with coverage.

## Coverage review and what was added
Target: 98 % for `app`, 100 % for the new security-relevant modules. First full run of the group: 98 % overall (44 lines missed); 14 lines were in new security-relevant modules. Each one was examined:

| Module and line | What it is | Treatment |
|---|---|---|
| `core/upload_guard.py:100` | deadline already passed when `receive` is about to be awaited | test with an injected clock: the second read never reaches the client |
| `services/ingestion_service.py:77` | explicit `heartbeat_interval_seconds` | test of the property |
| `repositories/ingestion_job_repository.py:326` | the lease expires *after* the first fence check, while the document lock is awaited | **race test with two real transactions**: another transaction holds the document row, the lease (2 s) expires while the worker waits, the second check refuses and nothing is erased |
| `repositories/ingestion_job_repository.py:130` | "cannot happen": the document row is locked and active when the claim reads it | `# pragma: no cover` with the reason |
| `rag/loaders.py:146-147` | a child that closes its output but does not exit | test with a scripted child, answered `PROCESSING_TIMEOUT` |
| `rag/loaders.py:170` | the child reports a code that is not a string | test, `PROCESSING_FAILED` |
| `rag/embedder.py:163` | the model returns fewer vectors than texts | test, fixed `EmbeddingError` |
| `rag/chunker.py:113` | a fragment made only of invisible characters after splitting | test with zero-width spaces |
| `rag/pdf_child.py:50-57` | `apply_limits` runs only in the child process (coverage does not follow it) | test that records the five `setrlimit` calls and their values (the real enforcement is proved by the child tests) |
| `rag/pdf_child.py:88-89` | failure while reporting a code | test, exit status `1` |
| `app/main.py:72` | `app_factory` | test that builds the application from the environment |
| `worker.py:173`, `rag/pdf_child.py:111` | `if __name__ == "__main__"` guards, run only by the real-process tests | excluded through `[tool.coverage.report] exclude_also` in `pyproject.toml` (no source change) |

Result: every module that this change created is now at **100 %**. The modules still below 100 % hold older code (`core/config.py` was extended by this change, but its one missed line, the CORS check in production, is older code) and are outside the scope of the group: `cli.py` 89 %, `core/config.py` 99 % (line 109, CORS in production), `core/cpu_quota.py` 93 %, `core/db_safety.py` 90 %, `core/error_middleware.py` 96 %, `repositories/enrollment_repository.py` 97 %, `repositories/subject_repository.py` 97 %. They are recorded here and not changed.

## Mutations (8, all killed)
Second fence check removed from the repository; no deadline check before waiting in the guard; the file-size limit not applied by the child; the memory limit doubled; the vector count not checked; the invisible fragment kept; a lingering child not treated as a timeout; the explicit heartbeat interval ignored.

## TDD
These tests close coverage gaps of behaviour that already existed, so they were green on the first run (no red run applies); their value is shown by the mutations above.

## Results
- Full backend suite in the Linux image against PostgreSQL: **1712 passed, 1 skipped (AES), 16 deselected (`realmodel`)**; coverage of `app` **99 %** (2,509 statements, 22 missed, all in the older modules listed above).
- `ruff check --no-cache`, `ruff format --check`, `mypy --strict app tests` (169 files) clean; `pip-audit`: no known vulnerabilities (no dependency changed); `openspec validate --strict` valid. Everything was repeated after the last change.

## Database state
| | Before the runs | After the runs |
|---|---|---|
| `asistenteia_test` | no tables (the session fixture drops the schema at the end) | **0 tables** |
| `asistenteia` (development) | revision `0004`; tables `alembic_version, document_chunks, documents, enrollments, subjects, users`; 0 users, 0 subjects, 0 documents, 0 chunks | identical: revision `0004`, same tables, same counts; `ingestion_jobs` and `documents.error_code` do not exist there |

The development database was never connected to by the tests; the statements above were run with `psql` against the project's container for verification only.

## Risks and deviations
- Coverage of the older modules (listed) is below 100 %; they were not part of this change.
- The race test depends on two timings (0.5 s and 2.0 s around a 2 s lease); the margins are wide, and removing the second check makes it fail.
- Seven untracked reference documents are present in the repository root (the owner mentioned six; the seventh, `Guia_SDD_OpenSpec_SpecBoot_Validada.md`, appeared during this group). None was touched or committed.
- Dependabot alert #1 remains open (planned in 15.1 and 17.3).
