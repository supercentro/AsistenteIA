# Step 8 - manual verification against the real database

Date: 2026-11-07. Branch `feature/documents-schema-pgvector`, HEAD `8866150` at the start. No credential or personal datum appears in this report; the throwaway password used for the login check was generated at run time and never stored.

## Target identification (before any write)
| Item | Value |
|---|---|
| Compose project / service | `asistenteia` / `db` |
| Container | `asistenteia-db-1`, image `pgvector/pgvector:0.8.7-pg15`, healthy |
| Volume | `asistenteia_db_data` (named volume of this project) |
| Host and port | `127.0.0.1:5442` -> `5432`; inside Compose `db:5432` |
| Database | `asistenteia` (development); size 8 MB |
| Target as seen by the backend container | `db`, `5432`, `asistenteia` (printed from `DATABASE_URL` without credentials) |
| Alembic revision before | `0003` (container and host agree) |
| Production / other PostgreSQL | none involved. Other containers on the machine (`asistenteia-postgres` on 5434, other projects) were not touched |

Pre-state of `asistenteia`: extensions `plpgsql 1.0`, `vector 0.8.7`; tables `alembic_version`, `enrollments`, `subjects`, `users`; enum `user_role`; 8 indexes; row counts `alembic_version` 1, `users` 0, `subjects` 0, `enrollments` 0.

## Backup and restore test (before migrating)
1. `pg_dump -Fc` of `asistenteia` inside the container (`/tmp/asistenteia_pre_0004.dump`), copied to the session scratch directory outside the repository (8,261 bytes, sha256 starts `f1bf54e5dc15a567`, 37 archive entries listed by `pg_restore -l`). It holds schema only: the three data tables were empty.
2. Restored with `pg_restore --no-owner` into a throwaway database `asistenteia_restore_check` in the same container.
3. Comparison of the restored copy with the source (server version, extensions, revision, tables, enum types, indexes, row counts): **identical** apart from the database name. The restore is valid.
4. On the restored copy (isolated, no application connected): `alembic upgrade head` (0003 to 0004), `alembic downgrade -1` (back to 0003), `alembic upgrade head` (0004), `alembic check`: "No new upgrade operations detected". The copy was dropped afterwards (`DROP DATABASE`); the database list is again `asistenteia`, `asistenteia_test`, `postgres`.

## 8.1 Migration on the development database
- `docker compose build backend` (image rebuilt so that it contains `0004_create_documents_and_chunks.py`; checked with `ls alembic/versions` in the container).
- `docker compose run --rm --no-deps backend alembic upgrade head` -> `Running upgrade 0003 -> 0004`; `alembic current` -> `0004 (head)`; `alembic check` -> `No new upgrade operations detected`.
- Snapshot diff against the pre-state: only additions: tables `documents` and `document_chunks` (0 rows), enum `document_status` (pending, processing, ready, failed), indexes `ix_document_chunks_embedding`, `ix_document_chunks_subject_id`, `ix_documents_subject_id`, `pk_documents`, `pk_document_chunks`, `uq_documents_id`, `uq_document_chunks_document_id`, revision `0004`. `users`, `subjects`, `enrollments` unchanged (0 rows each; the development database had no user data to lose).
- Catalog read with `psql` (`pg_constraint`, `pg_indexes`, `pg_class`/`pg_am`, `information_schema`):
  - `documents`: `pk_documents`, `uq_documents_id UNIQUE (id, subject_id)`, `fk_documents_subject_id_subjects ... ON DELETE CASCADE`, checks `size_bytes >= 0` and `chunks_count >= 0`; `status` default `'pending'`, `chunks_count` default 0.
  - `document_chunks`: `pk`, `uq_document_chunks_document_id UNIQUE (document_id, chunk_index)`, `fk_document_chunks_document_id_documents FOREIGN KEY (document_id, subject_id) REFERENCES documents(id, subject_id) ON DELETE CASCADE`, checks `chunk_index >= 0`, `page_number IS NULL OR >= 1`, `content ~ '\S'`, `vector_norm(embedding)` between `1e-6` and `1e6`; `embedding` is `vector(384) NOT NULL`.
  - Indexes: `ix_document_chunks_embedding USING hnsw (embedding vector_cosine_ops) WITH (m='16', ef_construction='64')` (access method `hnsw`, reloptions `{m=16,ef_construction=64}`), b-tree `ix_document_chunks_subject_id` and `ix_documents_subject_id`.
- **Deviation (decided with the user's restriction "no destructive downgrade on the development database"):** the `downgrade -1` / `upgrade head` round trip required by the task text was **not** run on `asistenteia`. It was run on the restored copy above (same state as the development database before the migration) and is also covered by `test_migrations_documents.py` on the isolated test database. The development database stays at `0004`.

## 8.2 Fixtures and `find_similar` on the development database
A one-off script (not committed, kept in the session scratch directory) ran in the backend container (`PYTHONPATH=/app`, read-only mount of the script and a copy of `tests/embeddings.py`). The committed fixture catalog could not be used directly because its helpers refuse, by design, any database whose name does not end in `_test`; that guard was not bypassed. The script reproduces the same layout with SQL: 2 teachers, 3 students, 3 subjects, 3 enrollments, 6 documents (Algebra ready plus pending/processing/failed, Physics, Chemistry) and 12 chunks, e-mails under `@fixtures.example.com`.

| Caller | Subject | Result |
|---|---|---|
| Enrolled student | Algebra | 6 chunks of `algebra-ready.pdf`, in order, similarities 0.984808, 0.866025, 0.707107, 0.5, 0.0, -1.0 (all within 1e-6 of the exact values) |
| Owning teacher | Algebra | the same 6 chunks and scores |
| Student not enrolled | Algebra | empty, no error |
| Another teacher | Algebra | empty, no error |
| Student enrolled only in Algebra | Physics | empty, no error |

Chunks of the pending, processing and failed documents (which lie exactly on the query) and of Physics and Chemistry (nearer than any ready Algebra chunk) never appeared.

Application checks with the rebuilt image, started with `docker compose run -d --no-deps` on host port 18000: `GET /api/v1/health` -> 200 `{"status":"ok"}`; `POST /api/v1/auth/login` with a fixture student -> 200; with a wrong password -> 401; health still 200 afterwards. (The contract path is `/api/v1/health`; `/health` alone gives 404.)

## 8.3 Cascade and clean-up
- Before clean-up: users 5, subjects 3, enrollments 3, documents 6, chunks 12.
- Deleting the Algebra subject: subjects 2, enrollments 1, documents 2, chunks 3; **Algebra documents 0 and Algebra chunks 0** (the 4 documents and 9 chunks went with it by `ON DELETE CASCADE`), Physics and Chemistry intact.
- Remaining fixture subjects and the 5 fixture users deleted by exact e-mail domain: users 0, subjects 0, enrollments 0, documents 0, chunks 0.
- Snapshot of `asistenteia` compared with the snapshot taken right after `0004`: **identical**. A query for fixture e-mails returns 0.
- The temporary backend container (`asistenteia-step8-backend`) was removed. The throwaway database `asistenteia_restore_check` was dropped.

## Quality gates after the manual verification
`alembic current` in the container `0004 (head)`; `alembic check` clean; full backend suite **668 passed**, coverage of `app` 98 %; `ruff`, `ruff format --check`, `mypy --strict` (105 files), `pip-audit` clean; `openspec validate --all --strict` 13 of 13. After the suite the development database snapshot is unchanged and `asistenteia_test` is empty as at the group 7 baseline.

## Incidents
1. Host port 8000 is occupied by another application (its `/health` answered, so `docker compose up -d backend` failed to bind). That process was not touched; the project backend was run on port 18000 instead. The failed container was removed.
2. The first two runs of the fixture script failed before inserting anything (missing `PYTHONPATH`, then a wrong name of the settings loader); the database was checked to be empty of users each time.
3. The pre-existing `asistenteia-backend` and `asistenteia-frontend` containers were stopped before this group and were left stopped.
