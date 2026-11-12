# Group 3: migration `0005` and models

Date: 2026-11-09. Branch `feature/document-ingestion`. Tasks 3.1, 3.2 and 3.3. Scope kept to the migration, the models, the failure catalogue and their tests: no repository, service, endpoint, contract or documentation change (those belong to groups 4 and later).

## What was added
- `backend/alembic/versions/0005_create_ingestion_jobs.py` (revision `0005`, down revision `0004`, working `downgrade`).
  - `documents.error_code varchar(40)` NULL with `ck_documents_error_code_only_when_failed` (`error_code IS NULL OR status = 'failed'`). The reverse rule ("a failed document has a code") is deliberately left to the service so fixtures that insert failed documents without a code keep working (design, data model).
  - Table `ingestion_jobs`: `id uuid` (`gen_random_uuid()`), `document_id uuid` NOT NULL with `uq_ingestion_jobs_document_id` and `fk_ingestion_jobs_document_id_documents` (`ON DELETE CASCADE`), `payload bytea` NULL, `attempts integer` NOT NULL default 0 with `ck_ingestion_jobs_attempts_non_negative`, `locked_by varchar(64)` and `locked_until timestamptz` NULL with `ck_ingestion_jobs_lease_consistent` (`(locked_by IS NULL) = (locked_until IS NULL)`), `available_at`, `created_at`, `updated_at` (`timestamptz` NOT NULL default `now()`), and the partial index `ix_ingestion_jobs_claimable (available_at) WHERE payload IS NOT NULL`.
- `backend/app/models/ingestion.py`: `IngestionJob`, the enum `DocumentErrorCode` (the 12 codes of the spec) and `DOCUMENT_ERROR_MESSAGES` (one fixed English sentence per code, without placeholders). `Document.error_code` in `backend/app/models/document.py`; exports in `app/models/__init__.py`.
- Migration `0004` is unchanged: a test compares its SHA-256 (line endings normalised) with the blob published in `main` (`3960132`), `git diff main -- backend/alembic/versions/0004*` is empty.

## TDD evidence (tasks 3.1 and 3.3: tests first)
Tests written before any implementation:
- `tests/unit/test_failure_catalogue.py` (6 tests),
- `tests/integration/test_migrations_ingestion.py` (12 tests, catalog level, task 3.1),
- `tests/integration/test_ingestion_job_integrity.py` (19 tests, task 3.3: cascade, uniqueness, checks, lease, ORM mapping).

Failing run before the implementation (`uv run --frozen pytest ...`):
- `test_failure_catalogue.py` and `test_ingestion_job_integrity.py`: collection error, `ModuleNotFoundError: No module named 'app.models.ingestion'`.
- `test_migrations_ingestion.py`: **8 failed, 4 passed** (the failing ones: the revision chain, the job table columns, constraints and partial index, `documents.error_code` and its check, and the three data-preservation tests). The 4 that passed before the migration are vacuous or negative by nature and are covered by the mutations below: the `0004` hash, `alembic check` (the models still matched the database at `0004`), and the two downgrade round trips (a no-op at `0004`).

After the implementation: the three new files and `test_migrations_documents.py` pass (47 tests); full suite **832 passed** (795 before plus 37 new), 2 warnings.

Two test bugs of mine were corrected during the green step, not the implementation: PostgreSQL raises `DataError` (not `IntegrityError`) for an over-long value, and deleting a teacher who owns subjects is `RESTRICT` since change 3 (my first test assumed a cascade; the test now asserts the refusal and that nothing is lost).

### Mutation checks (compensate that the rules live in the migration)
The migration was edited temporarily, the two migration/integrity test files were run, and the file was restored byte-identical (verified). Every mutation was detected:

| Mutation | Result |
|---|---|
| drop the lease consistency check | 2 failed (`test_ingestion_jobs_constraints`, `test_a_lease_needs_both_owner_and_expiry`) |
| drop the attempts check | 2 failed |
| drop the unique `document_id` | 5 failed |
| remove `ON DELETE CASCADE` | 5 failed (including `alembic check`) |
| drop the `error_code` check | 9 failed |
| make the claim index total (no `WHERE`) | 1 failed (`test_claimable_jobs_have_a_partial_index`) |
| downgrade forgets to drop `error_code` | 2 failed (downgrade and round trip) |
| `error_code` width 30 instead of 40 | 3 failed |

## Changes to existing tests (justified)
`tests/integration/test_migrations_documents.py` (written for `0004`): two assertions listed the columns and CHECK constraints of `documents` exactly. They now also list `error_code` and `ck_documents_error_code_only_when_failed`, with a comment that migration `0005` adds them. Nothing else in the 712 existing tests changed; all pass. Group 11 will review the other existing tests formally.

## Quality gates
- `ruff check` and `ruff format --check`: clean (116 files). `mypy --strict app tests`: clean (114 files).
- Coverage of `app`: **98 %** (`models/ingestion.py` and `models/document.py` 100 %). `core/cpu_quota.py` 93 % (3 lines of the real affinity and Windows fallbacks, which are platform branches).
- `pip-audit`: no known vulnerabilities (dependencies unchanged in this group).
- OpenSpec: `openspec validate document-ingestion --strict` and `--all --strict` pass.
- Frontend: not run; the API contract and the generated types are untouched (task 4.1 changes them).
- Databases: no migration was applied to the development database `asistenteia`; it is still at revision `0004`, 0 rows, with the same column hash (`11ea5ce4039d0ae55a8f93ea48649395`) as in the group 0 baseline. `asistenteia_test` has no tables after the suite. Migration `0005` was exercised only on the isolated test database (upgrade, downgrade to `0004`, round trip, upgrade from `0004` with rows).
- Docker and dependencies: no change (images, lock and versions as in group 2: `pypdf` 7.0.0, `python-multipart` 0.0.33, `sentence-transformers` 6.2.0, `langchain-text-splitters` 1.1.3, `torch` 2.15.0; worker image 3.22 GB accepted; the temporary Compose `worker` profile stays until group 8).

## Deviations and notes
1. `docs/data-model.md` is not updated here; task 4.1 owns it. Until then the data model document does not describe `ingestion_jobs`.
2. `error_code` is a plain `varchar(40)` in the model and the database (as designed); `DocumentErrorCode` is a Python enum and a test checks that every member fits the column.
3. The partial-index predicate and the CHECK constraints are verified from the catalog because `alembic check` does not compare them (incident I1 of change 5).
4. A CRLF working copy on Windows gives the same `0004` hash because the test normalises line endings.
