# Group 3 Report - Migration 0004 and Models (tasks 3.1 to 3.4)

- Date: 2026-10-28
- Change: documents-schema-pgvector
- Agent: Claude Code (Sonnet 5.5), main session
- Scope: migration `0004`, models `Document` and `DocumentChunk`, storage tests. `find_similar`, ingestion, fixtures helper (group 4) and documentation (group 10) were **not** started. No embedding or document text appears in this report.

## Preflight
Branch `feature/documents-schema-pgvector`, clean tree, HEAD `f61ce6d`; PR #7 open, `MERGEABLE`/`CLEAN`, CI green on that head; group 2 complete (7 tasks ticked) and documented; `openspec validate --strict` valid, 13 of 13.

## What was built
- `backend/alembic/versions/0004_create_documents_and_chunks.py` (hand-finished, incident I4): explicit `pgvector.sqlalchemy` import, `CREATE TYPE document_status` in `upgrade` and `DROP TYPE` in `downgrade`, tables, constraints, indexes. Migrations `0001` to `0003` are untouched (`git diff` on `alembic/versions` shows only the new file).
- `backend/app/models/document.py`: `DocumentStatus` (StrEnum), `Document`, `DocumentChunk`, `EMBEDDING_DIMENSIONS = 384`; relationship `Document.chunks`/`DocumentChunk.document` with `passive_deletes=True` (the database cascades). `app/models/__init__.py` exports them.
- Tests: `test_migrations_documents.py` (catalog), `test_document_storage_integrity.py` (SQL scenarios), `test_document_models.py` (ORM), `test_error_text_exposure.py` (incident I2), helpers `tests/sql_support.py` and `tests/leak_support.py`.

## Schema as created (catalog)
| Object | Result |
|---|---|
| Tables | `documents`, `document_chunks` (+ existing `alembic_version, enrollments, subjects, users`) |
| Enum `document_status` | `pending, processing, ready, failed` (order preserved) |
| Embedding column | `vector(384) NOT NULL` |
| Foreign keys | `fk_documents_subject_id_subjects` ON DELETE CASCADE; `fk_document_chunks_document_id_documents` composite `(document_id, subject_id) -> documents(id, subject_id)` ON DELETE CASCADE (the only FK of the chunk table) |
| Unique keys | `uq_documents_id (id, subject_id)`, `uq_document_chunks_document_id (document_id, chunk_index)` |
| CHECK (6) | `size_bytes >= 0`; `chunks_count >= 0`; `chunk_index >= 0`; `page_number IS NULL OR page_number >= 1`; `content ~ '\S'`; `vector_norm(embedding)` between `1e-6` and `1e6` |
| Indexes | `ix_document_chunks_embedding` **hnsw** `(embedding vector_cosine_ops) WITH (m='16', ef_construction='64')`; b-tree `ix_document_chunks_subject_id`, `ix_documents_subject_id` (+ pk/unique indexes) |

## Upgrade, downgrade, re-upgrade (CLI, throwaway database `g3_scratch` in the Compose db container, dropped afterwards)
1. `alembic upgrade 0003` on an empty database: 0001, 0002, 0003 applied; one teacher and one subject inserted.
2. `alembic upgrade head`: `0003 -> 0004`. **Existing rows unchanged** (md5 over `users` and `subjects` identical before and after).
3. `alembic current`: `0004 (head)`; `alembic check`: "No new upgrade operations detected."
4. `alembic downgrade -1`: tables `documents`, `document_chunks` gone, enum type gone (0 left), extension `vector` still installed, `users, subjects, enrollments` present. (`alembic check` at 0003 answers "Target database is not up to date", which is the expected CLI behaviour away from head, not drift.)
5. `alembic upgrade head` again and `alembic check`: no drift.
6. `alembic downgrade base`: `0004 -> 0003 -> 0002 -> 0001 -> base` all succeed; only `alembic_version` remains and the extension is removed by `0001`.
7. The scratch database was dropped (verified: 0 rows in `pg_database`).
The same sequence is covered in the test suite on the isolated test database (`test_downgrade_removes_tables_and_enum_but_keeps_the_extension`, `test_upgrade_from_0003_leaves_existing_rows_unchanged`, `test_alembic_check_reports_no_drift`, and the pre-existing `downgrade base` tests).

## Quality gates (backend)
- `ruff check` and `ruff format --check`: clean (97 files). `mypy --strict app tests`: no issues (96 files).
- `pytest`: **562 passed** (494 before; +68). Coverage of `app`: 98 % (repositories 97 to 100 %).
- `pip-audit` unchanged (no dependency added in this group).
- `openspec validate documents-schema-pgvector --strict` valid; `--all` 13 of 13.
- Frontend not touched.

## Integrity and security results
- Dimension 0/1/383/385, missing embedding, zero vector, `NaN`, `Infinity`, `-Infinity`: all rejected (`DataError`/`IntegrityError`). Norm `5e-7, 1e-7, 1e-30, 2e6, 1e7, 1e38`: rejected on insert and on update; `1.5e-6, 1e-3, 1, 15, 9e5`: accepted.
- Chunk with another subject than its document: rejected by the composite FK; chunk of a missing document: rejected; changing a document's subject while chunks exist: rejected.
- Cascades: deleting a document keeps the other documents' chunks; deleting a subject (300 chunks) removes its documents and chunks and leaves other subjects, their enrollments and all 4 users intact; a teacher with such a subject stays protected by `RESTRICT`.
- Error text and logs (incident I2): PostgreSQL's `DETAIL` was shown to carry the chunk text and embedding components (precondition test). With real violations (check, foreign key, unique, wrong dimension, blank content, bad parameter) raised inside a request, the response is the generic `INTERNAL_ERROR` and neither the response nor the captured root-logger text contains the text marker, the embedding marker or `Failing row contains`; the failure is still logged by exception type, method and path.
- The development database was **not** migrated: `alembic current` in the backend container is `0003 (head)` and its tables are `alembic_version, enrollments, subjects, users`.

## Deviations and decisions
1. `content` check strengthened to `content ~ '\S'` after a test found that `length(btrim(content)) > 0` accepts tabs and newlines; `design.md` updated. The spec wording ("empty or only whitespace") is unchanged.
2. Task 3.3 originally asked for `upgrade`/`downgrade` on the development database; by the user's instruction `0004` is not applied to shared databases in this group. The wording of task 3.3 was adjusted; the development database receives `0004` in task 8.1.
3. One existing test (`test_migrations_subjects.py`) targets `0002` explicitly instead of `-1`.
4. See `2026-10-28-tdd-evidence.md` for the failing run and the mutation checks.

## Residual risks
- Index parameters (`WITH` options, operator class) and CHECK constraints are not visible to `alembic check`; they are protected only by the catalog tests (incident I1), which a future migration author must keep in step.
- The unused-but-created hnsw index costs insert time and memory; accepted by the ticket and revisited in change 12.
- `Document.chunks` ordering uses `chunk_index`; write paths and `chunks_count` coherence belong to change 6.

## Outcome
- Tasks 3.1, 3.2, 3.2b, 3.3 and 3.4: PASS. Groups 4 to 12 not started.
