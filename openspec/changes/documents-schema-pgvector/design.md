# Design

Implementation rules live in `docs/backend-standards.md` and `docs/base-standards.md`; this document records only the decisions of this change. The decisions D1-D9 were approved by the user for this change; D10 and D11 are proposed here for approval together with the artifacts. Items marked **verify in apply** are hypotheses that the first tasks must prove on a real PostgreSQL before dependent work continues; if one fails, the artifacts are revised with `/opsx:update` first.

## Context

Migrations `0001` (extension `vector`), `0002` (`users`) and `0003` (`subjects`, `enrollments`) exist. The development database runs pgvector 0.8.7 (`pgvector/pgvector:pg15`, an unpinned tag in Compose and CI). Repositories follow the project pattern: sync SQLAlchemy 2 with psycopg 3, owner or enrollment conditions inside the SQL, savepoints for constraint errors, `hide_parameters=True` on the engine. The Python package `pgvector` is **not** a dependency yet. The embedding model planned for change 6 is `paraphrase-multilingual-MiniLM-L12-v2` (384 dimensions).

## Data model

```
subjects 1 --- * documents 1 --- * document_chunks
                  |  unique (id, subject_id)          ^
                  +-----------------------------------+
                     FK (document_id, subject_id) -> documents (id, subject_id)  ON DELETE CASCADE
```

`documents`: `id` uuid pk (`gen_random_uuid()`), `subject_id` FK `subjects` CASCADE, `filename varchar(255)`, `content_type varchar(100)`, `size_bytes bigint`, `status document_status` default `pending`, `error_message text` null, `chunks_count integer` default 0, `created_at timestamptz` default `now()`; `UNIQUE (id, subject_id)`; index `ix_documents_subject_id`.

`document_chunks`: `id` uuid pk, `document_id`, `subject_id`, `chunk_index integer`, `page_number integer` null, `content text`, `embedding vector(384)` not null, `created_at timestamptz`; `UNIQUE (document_id, chunk_index)`; composite FK above; `ix_document_chunks_subject_id` (b-tree); `ix_document_chunks_embedding` (`hnsw`, `vector_cosine_ops`, `m=16`, `ef_construction=64`, the pgvector defaults).

Checks (names follow the `ck_` convention): `size_bytes >= 0`, `chunks_count >= 0`, `chunk_index >= 0`, `page_number >= 1`, `length(btrim(content)) > 0`, and the embedding norm check (D8). `status` is a native enum like `user_role`, created in `0004` and dropped in its `downgrade`. `content_type` is validated at upload (change 6, `docs/base-standards.md` 9.1) and gets no database check, so adding a supported type later does not need a migration.

## Decisions

### D1. Composite foreign key for subject consistency (approved)
`UNIQUE (id, subject_id)` on `documents` and the composite FK from the chunk make the database reject any chunk whose `subject_id` differs from its document's. Alternatives rejected: a simple FK plus a repository check (bypassable by any future writer), and a trigger (hidden logic, more migration surface). Cost: one extra unique index on `documents`. Because the composite FK has no `ON UPDATE CASCADE`, moving a document between subjects while chunks exist is rejected, which is the desired behaviour (documents never change subject in the MVP). `docs/data-model.md` currently leaves this to the repository and omits the `document_chunks.subject_id` row from the referential-action table; both are corrected in this change.

### D2. `find_similar` takes the actor and authorizes in SQL (approved)
Signature (names final in apply): `find_similar(actor, subject_id, query_embedding, top_k) -> list[ScoredChunk]`. The `actor` is the authenticated user's id and role, passed as a small immutable value (not the ORM object and not an API-layer type, to keep repositories independent of `api/`). The statement always contains the subject filter **and** an `EXISTS` on `enrollments` (student) or `subjects.teacher_id` (teacher); any other role yields an empty result. A non-authorized actor gets an empty list, never an error, so existence of a subject cannot be probed (same indistinguishability principle as the 404 policy of change 3). There is deliberately no unscoped variant for internal use: the ingestion write path (change 6) will have its own owner-scoped repository methods; background jobs never read chunks through this path. This closes the gap between the Ticket 3 signature (`find_similar(subject_id, query_embedding, top_k)`) and `docs/base-standards.md` 9.4, which requires scoping by subject and by authenticated user in the repository.

### D3. Exact subject-filtered search first; HNSW evaluated, not assumed (approved)
HNSW applies the `WHERE` filter **after** the approximate scan (pgvector returns about `hnsw.ef_search` = 40 candidates by default), so a filtered query can silently return fewer than `top_k` rows when the subject is a minority of the table. The MVP search is therefore written as a filter-first exact search (subject, authorization and `ready` status are resolved before ordering by `embedding <=> :query`), which returns exactly `top_k` rows when the subject has that many. The exact search is the functional reference of the MVP: recall of any other plan is measured against it. The HNSW index is still created because Ticket 3 requires it, but the implementation does **not** force its use and does **not** change planner or pgvector settings (`enable_*`, `hnsw.ef_search`, `hnsw.iterative_scan`, `hnsw.max_scan_tuples`, cost parameters) unless `EXPLAIN` plans and recall tests on a mixed-subject dataset show that a change is needed and sufficient. In apply, the plans and the recall comparison go to the report; if the default planner choice returns incomplete results, that is presented to the user with alternatives (a statement-level exact plan, bounded `SET LOCAL hnsw.iterative_scan = strict_order`, or other) before any such setting is coded. The spec scenario "Complete results with many subjects" is the acceptance test. Rejected: relying on HNSW alone, forcing settings without evidence, and dropping the index (contradicts the ticket and removes the option for larger corpora).

### D4. Only the search repository (approved)
`ChunkRepository` has `find_similar` and nothing else. Tests insert documents and chunks with SQL fixtures (D5). `DocumentRepository`, `add_many`, status transitions and deletion belong to changes 6 and 7, which must write with ownership resolved inside the SQL (`INSERT ... SELECT`, lesson F6 of change 3).

### D5. Deterministic fixtures instead of a seed (approved)
Ticket 3 asks for a seed with sample chunks and `docs/backend-standards.md` says the seed creates "demo teacher, student, subject and sample chunks", but the decision approved in change 2 is that the seed creates only the demo teacher and student without subjects, and the seed spec says so. This change does not touch the seed. Test fixtures (a helper module under `backend/tests/`) create users, a subject, enrollments, documents and chunks by SQL with precomputed, hand-derivable embeddings (for example orthogonal basis vectors and combinations with known cosine similarity, generated by a pure function; no embedding model, no network). No production or demo data is created; demo data for the E2E flow is decided in change 12 or 13. Both source documents are corrected or reported, see "Reported divergences".

### D6. Native enum and CHECK constraints (approved)
As in the data model section. The enum follows the existing `user_role` pattern (explicit `CREATE TYPE` in the migration, `create_type=False` in the model, `DROP TYPE` in `downgrade`). The `chunks_count` column is a contract field: change 6 keeps it equal to the number of chunks; this change only guarantees `>= 0`.

### D7. pgvector for Python: documentary spike result and gate (approved; result below)
Spike method: documentation and source of `pgvector-python` (sources listed at the end), no installation, no migration run, as the approval requires. Findings:

| Question | Finding |
|---|---|
| Current release | 0.5.1 (2026-10-08); 0.5.2 unreleased. Python 3.10+, NumPy no longer required (0.5.0). Python 3.12 is fine. |
| SQLAlchemy 2 | `pgvector.sqlalchemy.VECTOR(dim)` (also importable as `Vector`) is supported; since 0.5.0 it returns plain `list[float]`. |
| psycopg 3 | The type serializes the value to text (`[1,2,3]`) in its bind processor and parses text on read, so **`register_vector` is not needed** for `VECTOR` columns. The package documents `register_vector` for the driver; it would fail on a database without the extension (a fresh database before `0001`). Decision: do **not** register the driver adapter; use only the SQLAlchemy type. |
| Operators | The comparator offers `cosine_distance` (`<=>`), `l2_distance`, `max_inner_product`, `l1_distance`. Cosine is the one used. |
| HNSW in SQLAlchemy | `Index(..., postgresql_using='hnsw', postgresql_with={'m': 16, 'ef_construction': 64}, postgresql_ops={'embedding': 'vector_cosine_ops'})`. |
| Input validation | **None** in the library: no dimension check, and `NaN`/`inf` are serialized as `nan`/`inf`. Validation therefore must be ours (D8). |
| Alembic | The package has no Alembic documentation. A known issue exists for **expression** indexes (halfvec cast, pgvector-python issue 118); our column index is a plain one on `embedding`, not that case. Not proven for `alembic check`. |

Conclusion: adopt the `pgvector` package (exact version pinned in `pyproject.toml` and `uv.lock` at apply) and the SQLAlchemy type, with no driver registration. **Gate (first task of the apply, verify in apply):** in a throwaway virtual environment outside the repository first, then in the project once confirmed, prove: (1) insert and read of a `vector(384)` through SQLAlchemy and psycopg 3 without `register_vector`; (2) `alembic revision --autogenerate`/`alembic check` on the models reports no drift for the column and the hnsw index with `vector_cosine_ops` and `with` options; (3) the migration file renders `pgvector.sqlalchemy.VECTOR(384)` and the `downgrade` works. The experiments run only against a throwaway PostgreSQL container with a scratch database (never `asistenteia`, `asistenteia_test` or any production database) and a throwaway virtual environment; nothing is installed in the project and no migration runs on the development database until the gate passes. **If any experiment fails, no architecture, migration or standard is changed: the failure and the alternatives (for example a custom `UserDefinedType` for `vector(N)` plus an `include_object`/`compare_type` rule scoped to this one index in `alembic/env.py`, or moving the zero-norm rule to the repository only) are presented to the user for approval first.** `alembic check` is never turned into a manual exception. No dependency is added to the project before the gate passes.

### D8. Degenerate vectors rejected twice (approved)
In the repository (before any statement): exactly 384 components, all finite, norm greater than zero, `top_k` in 1 to 50, raising one controlled domain error (a `ValueError` subclass in `app/core/errors.py` style, message without values). In the database: `vector(384) NOT NULL` already rejects missing and wrongly sized vectors, pgvector itself rejects `NaN` and infinity on input, and a check `vector_norm(embedding) > 0` rejects the zero vector (cosine with a zero vector is undefined and such rows are not indexed by hnsw). **Verify in apply (isolated scratch database):** that `vector_norm` is usable in a `CHECK` (immutable) on the pinned pgvector version and that it rejects the zero vector on insert and update; if not, the alternatives are presented to the user first, and only with approval is the zero-vector rejection kept in the repository and the spec scenario "Zero vector" in `document-storage` narrowed through `/opsx:update`. Logging: nothing derived from the vector or the content is logged; `hide_parameters=True` is already set and the statement-level log tests extend to this change.

### D9. HNSW parameters stay at the defaults (approved)
`m=16`, `ef_construction=64`; no `ef_search` tuning. The MVP corpus is small; tuning needs real data and belongs to change 12 or later.

### D10. Pin the database image (proposed; user asked to pin after verification)
Replace the floating `pgvector/pgvector:pg15` with a version tag (the local image reports pgvector 0.8.7 and the registry lists `0.8.7-pg15`) in `docker-compose.yml` and `.github/workflows/ci.yml`. Compatibility conditions (approved): the image must exist, be PostgreSQL 15, and carry the same pgvector version as the current installation (0.8.7) so database and extension stay compatible with the existing volume; a different major or minor version is not adopted without the user's approval. **Verify in apply:** the tag exists and pulls, `SHOW server_version` reports 15.x, `SELECT extversion FROM pg_extension WHERE extname='vector'` returns the pinned version on a scratch container and on the existing volume, and the full test suite and `docker compose up` still work. The existing named volume holds a database created by the previous image; a pgvector patch change does not require `ALTER EXTENSION UPDATE` to run migrations, but the guide documents the command. A rebuild of the backend image is needed for the new migration (lesson L15).

### D11. Small additions to the ticket (proposed, to confirm)
(a) `ix_documents_subject_id`, used by subject cascades and by the listing of change 7; (b) `ready`-only filter in `find_similar`, so chunks of a document still being processed or failed cannot reach an answer; (c) `ScoredChunk` includes `document_filename` and `page_number`, the values later snapshotted by `message_sources`. None adds endpoints or behaviour outside the ticket's intent.

### Approval record
D1-D11 and these artifacts were approved by the user with conditions, incorporated through `/opsx:update`: `vector(384)` and SQL-level actor isolation unchanged; `documents.subject_id` b-tree index kept (D11a); only `ready` documents are searched (D11b); `ScoredChunk` carries `document_filename` and `page_number` (D11c); deterministic fixtures and an untouched seed; exact search as the functional reference; HNSW created but not forced and no planner settings changed without `EXPLAIN` and recall evidence (D3); experimental compatibility checks (pgvector-python with psycopg 3, SQLAlchemy and Alembic; the `vector_norm` CHECK; the image) run in isolation, and any failure is presented with alternatives before architecture, migrations or standards change (D7, D8, D10).

## Reported divergences (not silently fixed)

1. Ticket 3 and `docs/backend-standards.md` (seed with sample chunks) vs the approved seed decision of change 2: resolved by D5; `docs/backend-standards.md` is corrected in this change, `readme.md` Ticket 3 is **not** edited without approval.
2. Ticket 3 states "Dependencias: ninguna", but the tables need `subjects` (change 3, already merged). Informational only; no document is changed.
3. Ticket 3 signature of `find_similar` vs `docs/base-standards.md` 9.4: resolved by D2.
4. `docs/data-model.md`: status "proposed design" for these tables, subject consistency left to the repository, missing referential row for `document_chunks.subject_id`: corrected here (D1).
5. `docs/api-spec.yml` `Document` schema has no `required` list: not changed here; corrected with evidence in change 6 (same policy as change 4).

## Dependencies with later changes

| Change | Uses from this change | Constraint it inherits |
|---|---|---|
| 6 `document-ingestion` | tables, enum, `vector(384)`, composite FK | writes must resolve ownership in SQL; chunk dimension must be 384; keep `chunks_count` and `status` coherent; becomes `ready` only after chunks are stored |
| 7 `teacher-material-ui` | `documents`, `ix_documents_subject_id`, cascades | list and delete scoped by owner |
| 9 `rag-chat` | `find_similar`, `ScoredChunk` | applies `MIN_SIMILARITY` and the no-material answer; maps the controlled errors; may revisit D3 with real data |
| 11 `personal-data-erasure` | cascades | no chunk or document holds student personal data; verifies no orphan rows |
| 12 / 13 | fixtures, pinned image | demo data and E2E data decided there; image pin documented for delivery |

## Risks and mitigations

- **Filtered ANN loses results** (D3): exact filter-first search, recall test against an exact search, `EXPLAIN` evidence.
- **Wrong or degenerate vectors** (D8): validated in the repository and in the database; extreme-input tests (383/385/0 components, NaN, infinity, zero, huge magnitudes, `top_k` out of range, strings and `None`).
- **Library drift or false `alembic check` drift** (D7): gated spike with a defined fallback.
- **Floating image tag** (D10): pinned after verification; the guide documents how to move to a newer pgvector.
- **Embedding model change** (dimension is in the schema): changing the model needs a new migration and reindex; recorded in `docs/technical-debt.md`.
- **Storage and index growth** (about 1.5 KB per chunk plus the index in memory) and no quota per subject: accepted for the MVP, registered in `docs/technical-debt.md` as a new TD.
- **Cascade deletes of many chunks in one statement**: acceptable at MVP volume; test with a few hundred rows.
- **Data leakage**: chunk text and embeddings never enter logs or error bodies; log tests cover the new code. Chunk text is untrusted content (prompt-injection defences belong to change 9) but is stored verbatim here.
- **Authorization regression**: negative tests for every actor type plus mutation checks that remove each condition (subject, enrollment, ownership, `ready`) and must make a test fail.

## Test strategy (summary; tasks.md has the order)

TDD with the failing run recorded per group (`docs/lessons-learned.md` L01). Migration tests upgrade and downgrade on a clean database and from `0003`, inspect constraints, indexes and the enum, and cover the cascade and integrity scenarios with SQL (`backend/tests/integration`, real PostgreSQL with pgvector). Repository tests use the deterministic fixtures. Concurrency tests run parallel searches by different actors. An independent adversarial review (separate subagent, clean context) is mandatory because the change implements data isolation. Real verification runs against the Docker Compose database: `alembic upgrade`/`downgrade`, `EXPLAIN`, a script calling `find_similar` on fixtures, and `alembic check` on the development and test databases. No endpoint is added, so curl and Playwright steps are replaced by those database verifications and a frontend/e2e regression run, stated in the reports.

## Sources of the compatibility spike

pgvector-python README and `CHANGELOG.md` (master), `pgvector/sqlalchemy/vector.py` and `pgvector/vector.py` (master), pgvector-python issue 118 (expression index and Alembic), pgvector 0.8 documentation on iterative index scans, and Docker Hub tag list for `pgvector/pgvector` (tag `0.8.7-pg15` listed; local image created 2026-10-01 reports extension 0.8.7). Nothing was installed or executed against the project database.
