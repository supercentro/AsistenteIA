# Compatibility Spike Report (group 1, tasks 1.1-1.5)

- Date: 2026-10-28
- Change: documents-schema-pgvector
- Agent: Claude Code (Sonnet 5.5), main session
- Scope: tasks 1.1 to 1.5 only. Nothing was installed in the project, no project file other than this report and `tasks.md` changed, and no migration of the product ran.
- Report rule: no vector values and no sensitive data. Only exception classes and the first line of database messages appear below.

## Isolation

| Resource | Created for the spike | Handling |
|---|---|---|
| Container `spike-pgvector-g1` | `docker run --rm`, data on `tmpfs` (no volume), database `spike` (+ `spike_noext`, `spike_alembic`), bound to `127.0.0.1:55439` (a port no project service uses) | Stopped; `--rm` removed it. `docker ps -a --filter name=spike-pgvector-g1` returns 0 rows |
| Python environment | Python 3.12 venv in a temporary directory outside the repository, with the **versions locked by the project** plus `pgvector` | Directory deleted |
| Image | `pgvector/pgvector:0.8.7-pg15` pulled (same image ID as the existing `pg15` tag) | Image kept locally as an extra tag of the same image; it is the tag D10 proposes to pin. Not a container or volume |
| Project resources | `asistenteia-db-1` was only queried read-only (`show server_version`, `extversion`); no connection to `asistenteia` or `asistenteia_test` data, no write | Containers and the `asistenteia_db_data` volume unchanged (db up and healthy, same as before) |

Cleanup verification: no container named `spike-*`, temp directories removed, nothing listening on 55439, `git status` clean apart from this report.

## Versions verified

| Component | Version |
|---|---|
| Image | `pgvector/pgvector:0.8.7-pg15`, digest `sha256:47af0b65960b14f1c6945aa4ccae37836c632e9a6fe0eea9160936e616e5b2e9` (identical to the current `pg15`) |
| PostgreSQL (spike) | 15.19 (Debian 15.19-1.pgdg12+2) |
| pgvector extension (spike and development database) | 0.8.7 / 0.8.7, PostgreSQL 15.19 on both |
| Python | 3.12 (project requires `>=3.12,<3.13`) |
| SQLAlchemy / psycopg / psycopg-binary / Alembic | 2.1.6 / 3.3.6 / 3.3.6 / 1.20.1 (exactly the project's `uv.lock`) |
| pgvector (Python) | 0.5.1 (latest release on the day) |

## Task results

### 1.1 Image (D10): PASS
`0.8.7-pg15` exists and pulls; the container is PostgreSQL 15.19 with `vector` 0.8.7 (`CREATE EXTENSION` works). The development database reports the same server version (15.19) and extension version (0.8.7), checked with read-only queries. Pinning `pgvector/pgvector:0.8.7-pg15` keeps database and extension identical to the current installation. Volume compatibility is a consequence of the identical image digest; the pin itself is task 2.2 (not executed).

### 1.2 pgvector-python with SQLAlchemy 2 and psycopg 3: PASS (with findings)
Without `register_vector`, using only `pgvector.sqlalchemy.VECTOR(384)`:
- insert and read of `vector(384)` works; reads return a plain `list` of 384 floats;
- ordering and score with `1 - cosine_distance(query)` returned `1.0`, `0.6`, `0.0` for the known fixtures;
- a connection on a database **without** the extension works (`select 1`), which would fail if the driver adapter were registered at connect; creating the table there fails with `UndefinedObject: type "vector" does not exist`, as expected.

Exact behaviour on invalid input (exception class, first line of the message):

| Input | Result |
|---|---|
| 383 or 385 components | `sqlalchemy.exc.DataError` / `psycopg.errors.DataException: expected 384 dimensions, not N` |
| empty list | `DataError` / `vector must have at least 1 dimension` |
| `NaN` | `DataError` / `NaN not allowed in vector` |
| `+inf`, `-inf` | `DataError` / `infinite value not allowed in vector` |
| non-numeric item | `StatementError` / `builtins.ValueError: could not convert string to float` (raised by the library, before the database) |
| a string instead of a list | `StatementError` / `ValueError: expected list or ndarray` |
| `None` on a NOT NULL column | `IntegrityError` / `NotNullViolation` |
| **all-zero vector** | **accepted by the column** (rejected only by the CHECK of 1.4) |

Findings:
1. As the source analysis predicted, the library validates nothing; PostgreSQL rejects wrong size, `NaN` and infinity, and the controlled error must be ours (D8).
2. A **zero query vector does not raise**: `<=>` returns `NaN` for every row, so the query "succeeds" with meaningless ordering. The repository must reject it (already in the spec).
3. A wrong-size or `NaN` **query** raises `DataError` at execution (`different vector dimensions 384 and 383`, `NaN not allowed in vector`).
4. Library errors for non-numeric items are wrapped by SQLAlchemy as `StatementError` (with `hide_parameters=True` the parameters are hidden, but the original `ValueError` message contains the offending item).
5. `pgvector` 0.5.1 exposes no `__version__`; the version must come from the lock file / `importlib.metadata`.

Conclusion for D7: the SQLAlchemy type works with psycopg 3 without driver registration. Confirmed.

### 1.3 Alembic autogenerate, reversibility, `alembic check`: PASS (with findings)
Scratch project mirroring `docs/data-model.md` for `documents` and `document_chunks` (native enum, composite FK, unique keys, checks, `VECTOR(384)`, hnsw index with `m=16`, `ef_construction=64`, `vector_cosine_ops`, the project's naming convention and default `env.py` options).
- Autogenerate renders every table, constraint, the b-tree indexes and the hnsw index with `postgresql_using`, `postgresql_with` and `postgresql_ops`. Catalog definition after `upgrade`: `USING hnsw (embedding vector_cosine_ops) WITH (m='16', ef_construction='64')`.
- `alembic check` after `upgrade`: **"No new upgrade operations detected"**. After `downgrade -1` (extension kept, enum type removed, only `subjects` left) and a second `upgrade`: again no drift.
- Sensitivity of `alembic check` (temporary model mutations on the scratch project, restored afterwards): `VECTOR(384)` to `VECTOR(385)` **is detected** (`modify_type`); changing the operator class `vector_cosine_ops` to `vector_l2_ops` **is not detected**; changing hnsw `m` from 16 to 24 **is not detected**.

Findings:
1. No false drift for `VECTOR` or the plain hnsw index. The fallback type is not needed.
2. The generated file is not usable as is: it references `pgvector.sqlalchemy.vector.VECTOR` **without importing** it, and with `create_type=False` it neither creates nor drops the `document_status` enum. The product migration must be hand-finished (explicit `import pgvector.sqlalchemy.vector`, `CREATE TYPE` in `upgrade`, `DROP TYPE` in `downgrade`), which is the project's existing pattern for `user_role`.
3. `alembic check` does **not** compare index operator classes or `WITH` options (and does not compare CHECK constraints). The migration tests of task 3.1 must therefore assert the catalog definition of the hnsw index (`pg_indexes`/`pg_get_indexdef`) and the CHECK constraints; `alembic check` alone would not catch a wrong operator class.

Conclusion for D7: Alembic works with the standard `VECTOR` column and hnsw index; the gate passes with the two procedural notes above.

### 1.4 `vector_norm` CHECK (D8): PASS (with findings)
`CHECK (vector_norm(embedding) > 0)` on `vector(384)` with the hnsw index present:
- accepted at table creation; `pg_proc.provolatile = 'i'` (immutable);
- normal vector: insert accepted; all-zero vector: **insert rejected** (`violates check constraint "ck_document_chunks_embedding_non_zero"`); **update to zero rejected**;
- a wrong-size vector through SQL: `expected 384 dimensions, not 383`;
- the composite FK rejects a chunk whose `(document_id, subject_id)` does not exist in `documents` (`fk_document_chunks_document_id_documents`);
- an `EXPLAIN` with `enable_seqscan=off` shows the planner can use `ix_document_chunks_embedding` for `ORDER BY embedding <=> ... LIMIT` (smoke check only; no planner setting is proposed for code, per D3).

Findings:
1. **Database error DETAIL leaks row data.** The constraint-violation message carries `DETAIL: Failing row contains (..., content, [first 32 embedding components]...)`. Any code or handler that logs `exc.orig` or the exception text would write chunk content and embedding values to logs. The repository error handling and the log tests (specs "Logs and errors never expose chunk text or embeddings") must cover this explicitly: never log or return `str(exc.orig)` for chunk statements, and assert it with a captured-log test.
2. **Extreme magnitudes produce `NaN` distances although the norm is positive.** Components around `1e-30` or `1e38` pass the CHECK and the library, but `<=>` returns `NaN` (float32 accumulation underflow/overflow) for them, as a stored vector or as a query. With a `NaN` distance the ordering is undefined. The "norm greater than zero" rule is therefore not sufficient on its own.

Conclusion for D8: the CHECK works as designed and the zero-vector rejection can live in the database.

### 1.5 Report and teardown: PASS
This report; resources destroyed and verified (see Isolation). No hypothesis failed, so no work was stopped; the incidents below need decisions but do not block the plan.

## Incidents and alternatives (for the user's decision; nothing was changed automatically)

| # | Incident | Impact | Alternatives |
|---|---|---|---|
| I1 | `alembic check` does not see operator class / `WITH` changes of the hnsw index, nor CHECK constraints | A wrong index definition could pass the gate | **(A, recommended)** keep `alembic check` and add catalog assertions to the migration tests (task 3.1 already inspects indexes; make the operator class, `m`, `ef_construction` and the CHECK definitions explicit); (B) add a custom Alembic comparator (more code, more drift risk) |
| I2 | PostgreSQL DETAIL contains the failing row (content and part of the embedding) | Log leakage if exception text is logged | **(A, recommended)** treat as a log-test requirement: repository maps chunk errors to generic domain errors and the handlers never log `exc.orig`; test with forced constraint violations; (B) suppress DETAIL server-side (`log_error_verbosity`) which does not affect the client message, so it is insufficient alone |
| I3 | Magnitude extremes give `NaN` distances although the norm is positive | Undefined ordering, possible silent bad retrieval | **(A, recommended)** add to the repository's validation (D8) a finite, bounded magnitude rule (for example every component finite and the squared norm within float32 range, computed in Python double precision) plus a test with `1e-30` and `1e38`; the model produces normalised vectors in practice; (B) normalise the query vector before searching (changes the vector, more behaviour); (C) also bound the stored vectors with a second CHECK (extra constraint; to decide with I3-A) |
| I4 | The autogenerated migration lacks the `pgvector` import and the enum create/drop | Migration would fail or leave the type behind | Hand-finish the migration following the `user_role` pattern; covered by the upgrade, downgrade and re-upgrade tests of task 3.1 |
| I5 | The zero query vector does not raise in SQL (all distances `NaN`) | A bug in validation would not fail loudly | Already specified (rejection before the database); keep the extreme-input unit tests |
| I6 | The Windows path length of the scratch directory broke a SQLAlchemy extension import | Spike tooling only | Use a short temporary path; no product impact |

Spec/design impact if the user approves the recommendations: `document-storage` gains no new requirement (I1 is a test change), `chunk-retrieval` "Invalid query vectors" gains a scenario for out-of-range magnitudes (I3), and the logging requirements already cover I2; these are artifact updates to make with `/opsx:update` before group 5, not before group 2.

## Outcome
- Group 1 status: PASS for tasks 1.1, 1.2, 1.3, 1.4 and 1.5.
- Hypotheses: D7 (pgvector-python, psycopg 3, SQLAlchemy, Alembic) confirmed; D8 (`vector_norm` CHECK) confirmed; D10 (image `0.8.7-pg15`, PostgreSQL 15, identical extension version) confirmed.
- Blocking issues: none. Decisions needed from the user: I1, I2, I3 (recommendations above) before group 2 or at the latest before groups 3 and 5.
