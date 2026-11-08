# Step 7 - unit tests and database state verification

Date: 2026-11-07. Branch `feature/documents-schema-pgvector`, HEAD `8cec4d6` at the start. Nothing was written to any database by the verification itself; the only writers are the test suite on `asistenteia_test`.

## Target identification
| Item | Value |
|---|---|
| Compose project / service | `asistenteia` / `db` |
| Container | `asistenteia-db-1` (image `pgvector/pgvector:0.8.7-pg15`, healthy) |
| Volume | `asistenteia_db_data` (named volume of this project) |
| Host and port | `127.0.0.1:5442` -> container `5432` |
| Databases | `asistenteia` (development, never touched by tests) and `asistenteia_test` (`TEST_DATABASE_URL`, name ends in `_test`, guarded) |
| Other containers on the machine (`asistenteia-postgres` on 5434, other projects) | not used and not written |

The pre-test and post-test snapshots were read-only `psql` queries (`snapshot.sh`: server version, extensions, `alembic_version`, tables, enum types, indexes, exact row counts). Migration `0004` on the development database is reserved for task 8.1 and was not applied.

## 7.1 Baseline before the tests
| Indicator | `asistenteia` | `asistenteia_test` |
|---|---|---|
| PostgreSQL | 15.19 | 15.19 |
| Extensions | `plpgsql 1.0`, `vector 0.8.7` | `plpgsql 1.0` only |
| `alembic_version` | `0003` | table absent |
| Tables | `alembic_version`, `enrollments`, `subjects`, `users` | none |
| Enum types | `user_role` (teacher, student) | none |
| Indexes | 8 (pk/uq/ix of the three tables and `alembic_version_pkc`) | none |
| Row counts | `alembic_version` 1; `enrollments`, `subjects`, `users` 0 | none |

The test database is empty by design: the session fixture `migrated_db` drops everything when it ends.

## 7.2 Tests
Targeted, one module at a time:
| Module | Result |
|---|---|
| `unit/test_vector_validation.py` | 45 passed |
| `unit/test_embedding_fixtures.py` | 16 passed |
| `integration/test_migrations.py` | 3 passed |
| `integration/test_migrations_subjects.py` | 4 passed |
| `integration/test_migrations_documents.py` | 10 passed |
| `integration/test_document_storage_integrity.py` | 45 passed |
| `integration/test_document_models.py` | 5 passed |
| `integration/test_error_text_exposure.py` | 8 passed |
| `integration/test_fixture_catalog.py` | 9 passed |
| `integration/test_chunk_retrieval.py` | 36 passed |

Full backend suite with coverage: **668 passed** (3 warnings, 2 min 12 s). Coverage of `app`: **98 %** (1,106 statements, 21 missed). `repositories/`: `chunk_repository` 100 %, `user_repository` 100 %, `enrollment_repository` 97 %, `subject_repository` 97 %. `services/`: 100 % in every module. Both exceed the 80 % target of `docs/base-standards.md` 9.2.

Other gates: `ruff check` and `ruff format --check` clean (106 files), `mypy --strict` clean (105 files), `pip-audit` no known vulnerabilities, `openspec validate --all --strict` 13 of 13.

## 7.3 State after the tests
The same read-only snapshots were taken again and compared with `diff`: **both databases are byte-for-byte identical to their baseline** (`asistenteia` still at `0003` with the same tables, indexes and row counts; `asistenteia_test` empty). No residue, so no restore was needed.

## Incidents and deviations
- No code, test or migration was changed in this group; the group has no new functionality, so there is no failing run to record.
- The integration tests block without an error message when the compose `db` service is stopped (seen in group 5). The service was running for this group. Not a defect of this change.
- Earlier in group 6 a read-only query was sent by mistake to `asistenteia-postgres` (another project's container); it is not used in this group.
