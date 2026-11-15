# Tasks

Read `openspec/config.yaml` and `docs/openspec-tasks-mandatory-steps.md` first. Tests come first (TDD) in every implementation group. Task 1 was executed in the planning stage and group 2 on 2026-11-12 (reports in `reports/`). Groups 3 to 14 and tasks 15.1 and 15.2 are done and approved (15.2 under a limited authorisation of 2026-11-13), group 16 (rehearsal) was done on 2026-11-13 and group 17 (real run on the development database) on 2026-11-14 in the window 18:30-20:00, each stage under its own explicit owner authorisation; group 8 was implemented after the owner approved decision DD-9 of `design.md` (2026-11-12, option A). Groups 18 and 19 are **not started**: the owner authorises them one at a time. Task 3.3b stays unchecked in this reconciliation (see its line). Archive rule: the change is not archived until group 8 is done or the owner explicitly moves the `role-based-access` delta to a follow-up change. Gate (met): group 17 (switching the real `DATABASE_URL` to the application role) did not run before task 8.4, because registration cannot create a user under that role until then. TDD evidence: each implementation group records its failing run (command and failure summary) in its report under `reports/`.

## 0. Setup: Create Feature Branch (MANDATORY - FIRST STEP)

- [x] 0.1 Create feature branch `feature/database-least-privilege` from the `main` branch (done 2026-11-12 from `main` at `3b312e4`)
- [x] 0.2 Verify branch creation and current branch status (clean apart from the seven untracked reference documents)

## 1. Task 1: cold start of the planned Compose flow (H13), on a scratch project

- [x] 1.1 Run `reports/h13/run_h13.sh` (the real `docker-compose.yml` read-only plus `compose.h13.override.yml`, project `g27h13`, no published port, no real env file, temporary credentials outside the repository, at least 6 GB of free memory) and keep `reports/h13/h13-output.txt` (the valid full run; the repeated configuration-only round C is in `h13-output-roundC.txt`)
- [x] 1.2 Check from the output: dependencies `db` healthy -> `bootstrap` completed -> `migrate` completed -> API and worker healthy; the finished one-shots start again on a plain `up -d` and stay idempotent; the catalog/ACL fingerprint is equal after the second start; `restart` keeps the old environment and `up -d` applies a changed one; a rotated worker password works and the old one is refused; a failing `migrate` prevents the API and the worker from being created and the stack recovers once fixed; a one-shot in an inactive profile that others depend on makes the project invalid; the API writes a user under the application role and the row is stored; the worker polls without permission errors; no application container holds the administrator password or `TEST_DATABASE_URL`
- [x] 1.3 Write `reports/2026-11-12-task-1-h13-cold-start.md` (commands, results, limits: the bootstrap and migrate are stand-ins because the commands do not exist yet, and the deviations) and confirm that the scratch project left no container, volume or network and the evidence holds no secret value

## 2. Privilege inventory and matrix (TDD)

- [x] 2.1 Write the failing tests first: every table of the model has a decision in the matrix; the matrix grants nothing no statement uses; the inventory finds every statement of the API, CLI and worker; record the failing run in the change report (`tests/unit/test_db_privileges_matrix.py`, `test_db_privileges_inventory.py`; failing run in `reports/group-2/tdd-failing-run.txt`, taken with `app/db_privileges.py` absent; deviation: the inventory of 2.2 was written first because the tests need it, see the group 2 report)
- [x] 2.2 Write the inventory script that lists, per module, every ORM attribute mutation, `insert/update/delete`, `RETURNING`, row lock and raw `text()` statement (machine-derived, not remembered), and keep its output as evidence
- [x] 2.3 Implement the declarative matrix module with the rows of `design.md` DD-3 (including `SELECT (id)` on `document_chunks` for the worker and `UPDATE (consent_*)` on `users` for the application role)
- [x] 2.4 Make a new table or column without a decision fail the suite; mutation-check the matrix tests (remove a grant, add an extra one, drop a table from the matrix: each must fail a test)
- [x] 2.5 Decide with evidence whether an advisory lock keyed on the subject replaces `SELECT ... FOR UPDATE` on `subjects` (removing the only write grant on `subjects`); record the decision

## 3. Settings and environment files

- [x] 3.1 Write the failing tests first (record the failing run in the group report): `MigrationSettings` needs only the migrator URL; Alembic starts without `JWT_SECRET` and `CORS_ORIGINS`; the API environment has no administrator, migrator or test variable; the worker has no API variable; each service receives only its own secrets (deployment-file tests)
- [x] 3.2 Implement `MigrationSettings` and make `alembic/env.py` use it; add the CLI subcommand skeletons and their settings (`RolesSettings` for the bootstrap; `CliSettings` stays in task 8.5)
- [x] 3.3 Split the environment files and examples: examples `.env.migrate.example`, `.env.roles.example` and `.env.test.example` created, `TEST_DATABASE_URL` removed from `backend/.env.example` (the API example holds no `POSTGRES_*`, test, migration or role variable); `.gitignore` and `.dockerignore` already cover `.env.*` and the examples (tests prove it). The real `backend/.env` was NOT edited (owner restriction); `.env.cli.example` belongs to task 8.5
- [ ] 3.3b Real files: remove `POSTGRES_*` and `TEST_DATABASE_URL` from the real `backend/.env` and create the real `.env.migrate`, `.env.roles` and `.env.test`; needs the owner's specific authorisation (group 6 or the rehearsal), not done in group 3; left unchecked on 2026-11-15 because closing it was not part of the reconciliation of group 17: the real files were created in 17B stage S21 (reports/2026-11-14-step-17b-window-closure.md) and the owner decides whether to close it
- [x] 3.4 Keep the test-database guard comparing with the application `DATABASE_URL` when the test variables come from the separate file; add the reserved role-name prefix guard and the sweep of leftover test roles; update the affected unit tests
- [x] 3.5 Update `docs/development_guide.md` setup instructions for the new files (documentation task 18 finalises it)

## 4. Bootstrap, adoption, grants and verify (TDD, real PostgreSQL)

- [x] 4.1 Write the failing tests first for the bootstrap (record the failing run in the group report): idempotent twice, SCRAM verifiers (stored prefix, no secret in output), `search_path = pg_catalog` and qualified names, `RESET ALL` before the role settings, `PUBLIC` closed on every database and on schema `public`, extension created, global default privileges for functions (done: `tests/unit/test_db_admin_sql.py`, `test_db_admin_connection.py`, `test_db_admin_commands.py`, `tests/integration/test_db_admin_bootstrap.py`; RED in `reports/group-4/tdd-red.txt`; GREEN on a disposable PostgreSQL in `run-integration-final.txt`)
- [x] 4.2 Implement `db-bootstrap` (role and database work from the `postgres` database, only grant/revoke/extension/default privileges inside the application database) (done: `app/db_admin/bootstrap.py`; the persistent `search_path` is per role, see DD-6)
- [x] 4.3 Write the failing tests first, then implement `db-adopt`: explicit one-time `ALTER TABLE/TYPE ... OWNER TO` with `lock_timeout`, refused while sessions of the API or the worker exist, catalog and rows unchanged; the bootstrap only reports ownership drift (done: `app/db_admin/adopt.py` with dry run by default, `--apply`, `--rollback` and `--remove-roles`; the evidence of the first spike run is now reproduced and kept)
- [x] 4.4 Write the failing tests first, then implement `db-migrate` and `db-grants`: Alembic then the grants, table-level revoke then grant in one transaction, a recreated table regains its privileges, a direct Alembic run is refused or hooked (done: `app/db_admin/grants.py`, `migrate.py`; `alembic/env.py` refuses a direct online run)
- [x] 4.5 Write the failing tests first, then implement `db-verify` (read-only, every check of the `database-roles` spec, login probe per role, no secret in the output, runs as the migrator) (done: `app/db_admin/verify.py`, 31 drift kinds each with its test; runs as the migrator in a read-only session)
- [x] 4.6 Mutation-check the commands (remove each step of the bootstrap, the transaction, the `RESET ALL`, the `pg_catalog` search path, a matrix row: each must fail a test); restore each edit and verify byte-identical (done: 29 mutations on scratch copies, all caught after one fix and the tests the second review asked for; `mutation-run.txt`, `mutation-run-rerun-20.txt`, `mutation-run-review-fixes.txt`)

## 5. Privilege tests (positive, negative, persisted state, concurrency, planting)

- [x] 5.1 Role attributes and memberships of the four roles; connection limits derived from the real pools and a test at the limit (done: `test_db_roles_lifecycle.py`, limit of each role refused at N+1 with `too many connections for role`, existing sessions and other roles unaffected, recovery after releasing one; the API pool 5+10 stays inside the application limit)
- [x] 5.2 SCRAM storage and absence of secrets in outputs and logs (done in group 4: `test_passwords_are_stored_as_scram_verifiers_and_work`, `test_no_secret_reaches_the_output_the_logs_or_an_error`; server logs are not read by the tests, the bootstrap silences statement logging)
- [x] 5.3 Ownership after migration and after adoption on a database with data; drift reported (done in group 4: `test_db_admin_adopt.py`)
- [x] 5.4 Matrix tests under the roles: the worker on a one-chunk and a multi-chunk document (with a mutation that removes `SELECT (id)` on `document_chunks` and shows the one-chunk document fails), cascades without `DELETE` on children, the ungranted columns (including `document_chunks.content`/`embedding` and `alembic_version`), the account columns the application role must not change (done: `test_db_roles_paths.py` with the real repositories under the roles, the `SELECT (id)` mutation live, cascades, the ungranted columns and operations; it refuted the group 2 ORM assumption and widened the matrix, see DD-3 note 2)
- [x] 5.5 The denied-operation suite for the application, worker and migrator roles (DDL, `TRUNCATE`, extensions, schemas, functions, `COPY` to/from program and file, server files, large-object import, `ALTER SYSTEM`, `CREATE ROLE`, `CREATE DATABASE`, `SET ROLE`, `pg_authid`, terminating sessions, other databases, temporary tables) (done: `test_db_roles_denied.py`, 4 roles x about 40 statements, connections to other databases, role switching, `GRANT` to `PUBLIC` as a no-op, session settings, terminating other sessions, prepared transactions disabled)
- [x] 5.6 Atomic grants with a concurrent reader; downgrade/upgrade round trip leaves `db-verify` clean; `downgrade base` is an administrator operation (done: `test_db_admin_grants.py::test_grants_are_atomic_for_a_concurrent_reader` and the round trip and `downgrade base` in `test_db_roles_lifecycle.py`; the deterministic guarantee of the atomic grants is mutation 10)
- [x] 5.7 Bootstrap hardening: planted `lower(varchar)` and `=(varchar, varchar)` in `public` do not run for the administrator; future functions closed to `PUBLIC` (done in group 4: `test_a_function_planted_in_public_does_not_change_what_the_bootstrap_does`, `test_schema_public_extension_and_default_privileges`)
- [x] 5.8 `db-verify` detects each drift kind listed in the spec (done in group 4: 31 drift kinds in `test_db_admin_verify.py`)
- [x] 5.9 Rollback on a database with data: reassign, verify owners, drop owned, re-grant, drop roles last; catalog and rows identical (done in group 4: `test_rollback_*` and the role removal tests, plus the second-database case of this group)
- [x] 5.10 Self-tampering: `ALTER ROLE self SET ...` and `ALTER ROLE self PASSWORD ...` are undone by the next bootstrap and detected by the login probe; `LOCK TABLE` and chunk-poisoning behaviours are asserted as the documented residuals (done: self-tampering of settings and password detected and healed; `LOCK TABLE` and chunk behaviour asserted as documented residuals; cross-subject chunks are rejected by the composite key)

## 6. Compose services, deployment-file tests and H13 with the real commands

- [x] 6.1 Write the failing deployment-file tests first (record the failing run in the group report): `bootstrap` and `migrate` in the default profile with the dependency conditions, no published port added, `restart` policies, per-service env files, no source bind mount for the one-shots, no service depends on a profiled service (done: `tests/unit/test_compose_database_flow.py` and updates in `test_deployment_files.py`; RED in `reports/group-6/tdd-red.txt` (13 failures before the Compose change); 10 mutations of `docker-compose.yml` caught, `mutation-compose.txt`)
- [x] 6.2 Add the `bootstrap` and `migrate` services to `docker-compose.yml`, update the API and worker dependencies and env files, and document `up --build` when `app/` or `alembic/` change (done: `bootstrap` and `migrate` in `docker-compose.yml`; the files `.env.roles` and `.env.migrate` are `required: false` so that `ps`, `logs`, `exec` and `down` keep working on a machine that does not have them yet; the real files are not created: task 3.3b)
- [x] 6.3 Update the `dev-environment` guidance: `restart` does not apply a changed environment, `up -d` does; the one-shots run on every `up` (done: section "Compose flow of the database roles" in `docs/development_guide.md`)
- [x] 6.4 Repeat the cold-start scenarios of task 1 with the real `db-bootstrap` and `db-migrate` on a scratch project (twice from nothing, second start, credential rotation, failing migrate, profiles) and attach the output to the change reports (done: `reports/group-6/run_h13_real.sh` and `h13-real-output.txt`: cold start twice from nothing, idempotent second start, `restart` versus `up -d`, credential rotation, failing bootstrap, failing migrate and recovery, secrets by variable name, no published port, other containers unchanged; image of the branch built as `asistenteia-backend:g6-branch`)

## 7. Consent endpoint: explicit commit (separate functional commit)

- [x] 7.1 Write the failing tests first (record the failing run in the group report): a separate session reads the consent evidence after a 200; a refused write (missing privilege) is an error response and stores nothing (reports/group-7/tdd-red-unit.txt, run-integration-red.txt) (reports/group-7: tdd-red-unit.txt, run-integration-red.txt)
- [x] 7.2 Add the explicit `commit()` before the response in the consent endpoint and handle the database error as the other endpoints do (HTTP 500 with the standard error body); verify the consent responses in `docs/api-spec.yml` (users.py; api-spec 500 added) (users.py; api-spec 500)
- [x] 7.3 Add the rule "an endpoint that promises persistence commits explicitly" to `docs/backend-standards.md` and an audit of the other endpoints (subjects, enrollments and registration flush inside the handler; documents commit explicitly) (backend-standards section 7; TD-039) (backend-standards section 7; TD-039)

## 8. Teacher provisioning separated at database level (design approved 2026-11-12, option A; implemented in group 8)

- [x] 8.1 Obtain the owner's decision on the option of DD-9 and record it in `design.md` (done in the group 2 stage at the owner's instruction: option A, five identities)
- [x] 8.2 Write the failing tests first (option A): the application role cannot insert or update `users.role` (42501); public registration still stores `student`; the administrative command creates a teacher with its own identity; the API container holds no credential of that identity; `seed` follows the same path (reports/group-8: tdd-red-*.txt, test_db_roles_teacher.py)
- [x] 8.3 Migration `0006` (reversible): server default `'student'` on `users.role`, with migration tests (and `alembic check`); `0004` and `0005` are not edited (0006_users_role_server_default.py; test_migrations_user_role_default.py)
- [x] 8.4 Registration path omits the role column; model default updated; matrix: `INSERT` on `users` without `role` for the application role (auth_service, model, KNOWN_GAPS emptied)
- [x] 8.5 New CLI identity, its environment file, `CliSettings` (no JWT secret) and a one-shot Compose service; matrix row for the CLI role (CliSettings, .env.cli.example, cli Compose service)
- [x] 8.6 Update `docs/data-model.md`, `docs/development_guide.md` and the technical-debt entry for the runtime role capability (data-model, development_guide, TD-040)
- [x] 8.7 Mutation-check: restore the broad `INSERT` and show a test fails (reports/group-8/mutation-run.txt, mutation-compose-cli.txt: 15 of 15 caught)

## 8A. Prerequisites of group 9 (owner authorisation of 2026-11-13; they must be done before group 9 runs)

- [x] 8A.1 Pair 1, `ingestion_jobs.locked_by` and `locked_until` (priority 1, the fencing token): tests that inspect the SQL the ORM emits (single and batch insert, `RETURNING`) fail first; then `server_default=FetchedValue()` on both columns and `eager_defaults=False` on the mapper; then the matrix drops the two columns from the application `INSERT`; the upload path works under the application role; refused-insert negative test; own commit (commit b549357)
- [x] 8A.2 Pair 2, `documents.error_message` and `error_code`: same procedure (`FetchedValue()`, the application keeps `SELECT` on `documents`, so `RETURNING` needs nothing new); own commit (commit 8128430)
- [x] 8A.3 Pair 3, `users.consent_version` and `consent_accepted_at`: same procedure for the application role (registration) and the CLI role (create-teacher, seed); the consent `UPDATE` keeps its column grant; own commit (commit ee393b5)
- [x] 8A.4 The inventory (`tests/privilege_inventory.py`) models `FetchedValue()` columns as not inserted and `eager_defaults=False` as `RETURNING` of the key only, and the assumption text is restored; the matrix returns to the narrow `INSERT` lists; stop and present an alternative if `FetchedValue()` changes a semantic or needs an extra `SELECT` (privilege_inventory.py, db_privileges.py)
- [x] 8A.5 TD-039, `POST /auth/register`: test that reads the user from another session after the 201 and shows a refused write is an error with nothing stored; explicit `commit()` with rollback in the handler; no duplicate commit with `get_db` (commit 4577d7a)
- [x] 8A.6 TD-039, `POST /subjects` and `DELETE /subjects/{id}`: same procedure (commit 4577d7a)
- [x] 8A.7 TD-039, `POST /subjects/{id}/enrollments` and `DELETE`: same procedure; idempotency of the duplicate case and no partial change (commit 4577d7a)
- [x] 8A.8 Mutation checks of both prerequisites, regression of authentication, users, subjects, enrollments and ingestion, independent adversarial review, and the update of `docs/data-model.md`, `docs/backend-standards.md` and `docs/technical-debt.md` (TD-039 is updated with the evidence and not closed before the owner confirms) (reports/group-9-prerequisites: 27 of 27 mutations caught, review PASS WITH GAPS closed; TD-039 left open)

## 9. Role-bound integration suite

- [x] 9.1 Write the failing role-bound tests first (record the failing run in the group report), then the fixtures that prepare a `*_test` database (connection rights, schema ACL, extension), run Alembic as the migrator, apply the grants and give each test the application, worker and CLI connections; reserved role prefix and sweep (reports/group-9: red-coverage.txt, tests/least_privilege.py)
- [x] 9.2 Run every API route, every CLI subcommand and the claim, renew, complete, fail and sweep paths of the worker under the roles, with single-chunk and multi-chunk documents, asserting the **persisted state** of every write (test_db_roles_api_routes.py, test_least_privilege_coverage.py, test_db_roles_paths.py, test_db_roles_teacher.py)
- [x] 9.3 Parametrise the existing API and ingestion integration tests so they also run under the roles (marker `least_privilege`) without weakening any assertion (pytest --least-privilege -m least_privilege: 484 tests; final-1-least-privilege-mode.txt)
- [x] 9.4 Prove by mutation that removing a privilege makes a test fail while the endpoint still answers 200 (the persisted-state assertion catches it) (reports/group-9/mutation-run.txt: 11 of 11 caught; mutation-cause-0.txt; limit stated in group-9-report.md)

## 10. CI gate (decision D5)

- [x] 10.1 Write the failing workflow test first (record the failing run in the group report), then add the privilege job to `.github/workflows/ci.yml` (bootstrap, migrate with grants, `db-verify`, privilege tests, role-bound suite) against the database service container (commits d391f56, 72293f7; reports/group-10: red-workflow.txt, gate-happy.txt)
- [x] 10.2 Make a missing prerequisite fail the job, never skip; report the number of privilege tests executed (check_results.py; gate-missing-prerequisite.txt, gate-skipped-test.txt, gate-too-few-tests.txt)
- [x] 10.3 Add the workflow test and prove that a table without a matrix decision fails the job (test_ci_workflow.py, mutation-gate.txt 29 of 29; gate-new-table.txt)

## 11. Review and Update Existing Unit Tests (MANDATORY)

- [x] 11.1 List the existing tests that read the environment files, the guard, `alembic/env.py`, the Compose file or the settings, and update them with their justification; keep every assertion at least as strong (reports/2026-11-13-regression-review.md; reports/group-11: inventory, assertion counts, mutation-regression.txt 10 of 10, mutation-cli-process.txt)
- [x] 11.2 Record the list and the reasons in `reports/YYYY-MM-DD-regression-review.md` (reports/2026-11-13-regression-review.md)

## 12. Run Unit Tests and Verify Database State (MANDATORY)

- [x] 12.1 Capture the pre-test database baseline (development database untouched; test database state) (reports/group-12/snapshot-before.txt)
- [x] 12.2 Run the targeted tests first, then the full backend suite on Linux with PostgreSQL, ruff (`--no-cache`), `ruff format --check`, `mypy --strict`, `pip-audit` (reports/2026-11-13-step-12-unit-test-and-db-verification.md; Linux: 1309 unit, 864 + 410 + 484 integration, 34 migrations; ruff, format, mypy, pip-audit clean)
- [x] 12.3 Verify the post-test state and restore it if needed (snapshot-after.txt, snapshot-diff.txt: identical)
- [x] 12.4 Create `reports/YYYY-MM-DD-step-12-unit-test-and-db-verification.md` and mark the step only after the tests pass and the report exists (reports/2026-11-13-step-12-unit-test-and-db-verification.md)

## 13. Manual Endpoint Testing with curl (MANDATORY - AGENT MUST EXECUTE)

- [x] 13.1 Start the stack on a scratch project with the roles (or the rehearsal copy), never on the real development database before group 17 (reports/group-13: run_g13.sh, compose.g13.override.yml; project g13scratch)
- [x] 13.2 With curl: register, login, consent (200 and the stored evidence), subjects, enrollments, document upload/list/delete, health; and the denied cases (wrong role, other teacher, unauthenticated) (reports/2026-11-13-step-13-manual-endpoint-testing.md; 101 of 101 checks)
- [x] 13.3 Verify the database state after each write and restore it; document every command and response in the report (reports/group-13/g13-output.txt; scratch database destroyed, development database unchanged)

## 14. E2E Verification (no browser E2E required: no interface or logic change; the only frontend file changed is the generated API types)

- [x] 14.1 Record that the only frontend file changed is the generated API types (`frontend/src/types/api.generated.ts`, regenerated after the documented `500` responses; no component, logic or dependency change), that the steps of the CI job `frontend` are unchanged and pass locally except Playwright, and that the mocked Playwright suite was NOT run in this group (it runs in CI; no browser E2E was executed here) (finding F-14-1 in reports/2026-11-13-step-14-e2e-applicability.md, correction in reports/2026-11-13-step-14-closure.md)

## 15. Independent adversarial review of code and tests (required before any real run)

- [x] 15.1 Run the `adversarial-review` skill with a separate read-only subagent on the implemented code, tests, Compose changes and procedures; classify the findings in a report (reports/2026-11-13-step-15-adversarial-review.md: three read-only clean-context reviewers, verdict PASS WITH GAPS, 0 critical, 0 high, 10 medium; 15.2 is not authorised and stays open)
- [x] 15.2 Fix every blocking or major finding with tests first, re-run the affected gates and ask for a focused second review when the fix touches security; record accepted residual risks in `docs/technical-debt.md` with the owner's agreement (done within the owner's limited authorisation of 2026-11-13; accepted residual risks are TD-039 and TD-042 to TD-048 in `docs/technical-debt.md`, to be confirmed by the owner)
  - [x] 15.2.1 (PG-01) Tests first, then code: the API and the worker refuse to start as a superuser (effective identity, fail closed, test-only exception); examples and their tests use the restricted identities; stale guide lines corrected (reports/2026-11-13-step-15-2-corrections.md; commit 4798ed0)
  - [x] 15.2.2 (PG-02) Tests first, then code: `db-migrate`, `db-downgrade` and `db-verify` check the migrator identity before any change; errors of identity, connection and permission (commit ce8258b)
  - [x] 15.2.3 (F-1, B-1, F-2) Tests first, then code: `DELETE` of a document commits with the shared helper; refused commit keeps the data (another session); a lost connection at commit is 503; contract and generated types updated; frontend gates (commit 71a0a73)
  - [x] 15.2.4 (PG-07, PG-08) Tests first, then code: system databases refused; the rollback respects `--database`; the rest recorded as accepted limits (commit b85d90d; PG-08 limits documented, not changed)
  - [x] 15.2.5 (D-1, D-2, F-3, other findings) Technical debt (TD-039 widened and new entries), the safety box of the dangerous operations, a classification of every other finding, corrected documentary inconsistencies (TD-039 widened, TD-040 updated, TD-042 to TD-047; every other finding classified in the report)
  - [x] 15.2.6 Incident of the exposed credential: record without the value, affected service and credential, copies checked, coordinated rotation procedure prepared, nothing rotated (reports/2026-11-13-credential-exposure-incident.md; nothing rotated)
  - [x] 15.2.7 Gates on the final code (ruff, format, mypy strict, unit, role-bound and roles-mode integration, migrations, administrative commands, mutations of the critical controls, frontend gates, `openspec validate`) and the focused second adversarial review (reports/2026-11-13-step-15-2-corrections.md: gates on the final code, 22 mutations caught, second review PASS WITH GAPS with no critical or high finding, its findings handled)

## 16. Rehearsal on a restored copy of the real backup (done 2026-11-13 under a separate authorisation)

- [x] 16.1 Verify the backup (checksum, `pg_restore --list`) and restore it into a disposable server (reports/2026-11-13-step-16-rehearsal.md: SHA-256 verified in four places, `pg_restore --list` readable, restored twice; the only backup is of revision 0004, 0005 was reconstructed in the copy)
- [x] 16.2 Rehearse bootstrap, adoption, grants, `db-verify`, the functional checks of the 2026-11-12 validation (45 + 17) with the roles, and the rollback across every database (reports/group-16/g16-output.txt: 209 of 209 checks; the 45 + 17 checks of 2026-11-12 are not a stored script, the 101 curl checks of group 13 were rerun on the adopted copy)
- [x] 16.3 Record the report and the timings; stop if any check differs (report and timings recorded; the first run had 9 failures of the script itself, kept as superseded, the final run has none)

## 17. Real run on the development database (done 2026-11-14, window 18:30-20:00, one stage per explicit owner authorisation; the preparation 17A, with the runbook, the tested rollback and the GO/NO-GO checklist, was done on 2026-11-13 in reports/group-17a; closure in reports/2026-11-14-step-17b-window-closure.md)

- [x] 17.1 Preflight (backup verified and second copy, free memory, services state), stop the API and the worker (done 2026-11-14: stages S10-S13 of the window, two copies of the verified dump with independent manifests, the 8 GB memory gate closed in reports/2026-11-14-step-17c-blockers-closure.md and enforced by the script, services state recorded; S20 stopped the API and the worker; reports/2026-11-14-step-17b-window-closure.md sections 1 and 2)
- [x] 17.2 Bootstrap, adoption, grants and `db-verify`; switch the two `DATABASE_URL` values; `up -d --force-recreate`; prove the role of each process with `SELECT current_user` (done 2026-11-14: S22 `db-bootstrap`, S23-S24 adoption of the nine objects, S25 migration 0005 to 0006 and grants, S26 `db-verify` with no findings, S21 the two `DATABASE_URL` values, S30 recreation of the backend and the worker; **deviation recorded for the owner's confirmation**: the role of each process was proved by the session user in `pg_stat_activity` (one session of `asistente_app` and one of `asistente_worker`, none of the administrator, S31 and 17B.5) together with the start-up identity check that refuses a superuser, not by a literal `SELECT current_user`; reports/2026-11-14-step-17b-window-closure.md and reports/2026-11-14-step-17b5-functional-closure.md)
- [x] 17.3 Functional validation and cleanup of synthetic data; rollback instructions at hand; record the report (done 2026-11-14: 17B.5, 25 of 25 functional checks and the denied cases at database level, synthetic data removed and counts back to 0/0/0/0/0/0 with the catalog snapshot identical; runbook and recovery matrix at hand in reports/group-17a/runbook-17b.md and reports/group-17b/recovery-matrix.md, never needed; report reports/2026-11-14-step-17b5-functional-closure.md)

## 18. Update Technical Documentation (MANDATORY)

- [ ] 18.1 Use the `update-docs` skill: `docs/data-model.md` (privileges), `docs/development_guide.md` (files, commands, procedures, state), `docs/backend-standards.md` (least privilege, persisted-state tests, explicit commit), and `docs/api-spec.yml` only if a status code changes
- [ ] 18.2 `docs/technical-debt.md`: split `TD-030` (database part resolved, the rest stays with change 13) and add the residual-risk entries R1 to R10 of `design.md` DD-13
- [ ] 18.3 `docs/lessons-learned.md`: add the lessons that are not duplicates (a missing privilege behind a successful status, privileges derived from tests of real paths, one-shot services rerun on every `up`)
- [ ] 18.4 Ask the owner whether to record the notable AI usage in `prompts.md`; do not edit it without approval

## 19. Final verification of MUST quality gates (`docs/base-standards.md` section 9)

- [ ] 19.1 Typing, tests, security and isolation, lint and format, migrations (`alembic check`, round trip), documentation and traceability gates, re-run after the last change
- [ ] 19.2 `openspec validate database-least-privilege --strict` and `openspec validate --all --strict`
- [ ] 19.3 Review the full diff against `main`; conventional commits per responsibility; open the Pull Request only when the owner requests it and confirm the CI is green
- [ ] 19.4 After the review and the merge, with the owner's approval, archive the change with `/opsx:archive` (see the archive rule at the top)
