# Step 12: Unit tests and database verification

**Change**: chat-rag-endpoint
**Updated**: 2026-11-17 (supersedes the 2026-11-16 draft, which overstated its evidence)
**Environment**: Windows 11, Python 3.12, PostgreSQL 15 + pgvector. All database work ran against `asistenteia_test` on `127.0.0.1:5442` (name checked in every script). The persistent database `asistenteia` and the compose containers were not touched; their uptimes were identical before and after.

## 12.1 / 12.4 Database state (isolated test database)

`asistenteia_test` has no tables at rest: the session fixture drops everything and migrates, and every test truncates. Row counts captured with `scratchpad/counts.py` around a run of the nine chat integration modules (68 tests):

| Moment | alembic_version | users / subjects / enrollments / documents / chunks / conversations / messages / message_sources |
|---|---|---|
| Before | none | all tables absent |
| After | none | all tables absent |

After the last manual migration and `alembic check` run the database was dropped again (counts: all absent). There was nothing to restore. Not measured: the persistent database (no credentials were read, no connection made).

## 12.2 / 12.3 Test results (after the last code change, 2026-11-17)

| Suite | Result |
|---|---|
| Unit (`tests/unit`) | 1435 passed, 110 skipped (Linux-only), 4 failed (environmental, below) |
| Chat integration modules + auth, consent, health, transaction, migration-head, real-server hardening | 133 passed |
| Full `tests/integration` (run before the last two test fixes) | 902 passed, 37 skipped, 2 failed, 445 errors, 11 min |
| Gates | `ruff check --no-cache` clean, `ruff format --check` 261 files clean, `mypy --strict app` 92 files clean, `alembic check` no drift, 0007 downgrade then upgrade OK |

Full integration run, classified:

- **443 errors, not run**: `MissingTestDatabaseError: TEST_CLUSTER_IS_DISPOSABLE=true is required`. The role-bound tests (`test_db_roles_*`, `test_db_admin_*`, and the `*_persistence`/`orm_insert` tests) bootstrap roles on the cluster and close `PUBLIC` on every database, so they must only run on a disposable cluster. The cluster here hosts the persistent database, so the flag was deliberately not set. These tests are unverified in this session.
- **2 errors, regressions fixed**: `test_review_hardening` started the real API without embedder/LLM settings; the change makes the API build both at startup. Added `EMBEDDER_BACKEND=fake`, `LLM_BACKEND=fake` (20 passed).
- **1 failure, fixed**: `test_migrations_user_role_default` pinned the head to 0006; now asserts 0006 follows 0005 and 0007 is the head.
- **1 failure, OPEN (MUST gap)**: `test_least_privilege_coverage::test_every_api_operation_has_a_role_bound_scenario` fails because the five new operations (`POST /chat`, `GET /conversations`, `GET /conversations/{id}/messages`, `DELETE /conversations/{id}`, `DELETE /users/me/conversations`) have no scenario in `test_db_roles_api_routes.SCENARIOS`. Writing and verifying those scenarios needs a disposable cluster. Not done, not claimed.

## The four unit failures: reproduction and comparison with clean `main`

`git archive main` (commit b9ddaa6) extracted to a scratch directory (the working repository was not changed) and run with the same virtualenv:

| Test | Branch | Clean `main` | Cause |
|---|---|---|---|
| `test_worker_health::test_the_defaults_leave_room_for_the_beat_interval` | fails | fails | asserts a POSIX path (`/tmp/...`); Windows gives `\tmp\...` |
| `test_worker_settings::test_a_fresh_worker_process_loads_its_settings_without_any_api_variable` | fails | fails | subprocess started with a stripped environment: `OSError: [WinError 10106]` while importing `asyncio` (no `SYSTEMROOT`) |
| `test_worker_settings::test_importing_the_worker_does_not_pull_in_the_api` | fails | fails | same WinError 10106 |
| `test_migration_settings::test_alembic_refuses_to_use_the_application_url` | fails | passes in a bare extract; **fails when the local, git-ignored `backend/.env.migrate` (dated 2026-11-14) is copied in** | the test assumes no `.env.migrate` exists |

None is a regression of this change. They would pass on Linux/CI without a local `.env.migrate`.

## Production bugs found by the tests (fixed)

1. Migration 0007 created the `message_role` enum twice (`create_type=False`).
2. Model index name differed from the migration (alembic drift).
3. The RAG service passed a string to `embed(Sequence[str])` (one vector per character).
4. A null byte in a message produced a 500 (stripped; blank messages now rejected).
5. The chat rate limiter was configured but never wired.
6. From the adversarial review: conversation not bound to the subject, history never loaded, delimiter neutralisation bypasses, same-instant message ordering (see the review report).

## TDD deviations and compensations

Tests for groups 7-9 and 13 were written after the implementation. Compensation (mutation checks, each reverted): snippet cap removed, search error mapping removed, consent gate, enrolment gate, conversation ownership, subject binding, history loading, role tie-break and NFKC step removed. Every mutation made at least one test fail. For the review fixes, the failing run was recorded first (17 failures) before implementing.

> **Update (round 4, 2026-11-17):** the counts above are historical. Current results, including the full Linux suite, are in `2026-11-17-round4-m2-linux-suite-compose.md`.
