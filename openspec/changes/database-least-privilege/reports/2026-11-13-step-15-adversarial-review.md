# Step 15: independent adversarial review of the accumulated change (2026-11-13)

Branch `feature/database-least-privilege`, code at `4686ca1`, compared with `main` (`3b312e4`): 295 files, 107 outside `reports/`. Authorised scope: task **15.1** only. Task **15.2** (fixes) is **not authorised and was not executed**; no functional code, test, spec, skill or agent was changed, nothing was pushed, no Docker service or database was started or touched, and the new workflow has not run on GitHub Actions. Evidence: this report and the verbatim summaries below.

## Method and independence

Three reviewers with a clean context (none implemented the change), read-only, run in parallel with the `adversarial-review` method (`ai-specs/skills/adversarial-review/SKILL.md`): PostgreSQL security; HTTP transactions (TD-039); CI, tests, contract and documentation. They read the OpenSpec artifacts first and the earlier reports only afterwards, and had to cite files and lines. They ran nothing that touches a database. A "verified" control below means a named test or gate proves it **and** the reviewer read both; none of the reviewers re-ran the suites (the runs are those of groups 9 to 12). "Inspected only" means read in code, no test or run proves it. The consolidation, the severity mapping and three spot checks (below) are mine and are not independent.

My spot checks of the items that matter most: `tests/unit/test_deployment_files.py:165-175` really asserts that the user of `DATABASE_URL` in the API and worker examples equals `POSTGRES_USER` (PG-01); `app/db_admin/migrate.py:27-28` runs `command.upgrade` before `apply_grants`, the only identity check (PG-02); neither `db_admin/verify.py` nor `alembic/env.py` looks at column defaults or `compare_server_default` (PG-04); no startup check of `is_superuser` exists outside `db_admin`.

## Result by severity (user scale; "major" in the skill's terms is noted)

**Critical: 0. High: 0.** No path to privilege escalation, secret exposure, or a 2xx sent without a stored write was found on any implemented route.

### Medium (10): to be treated before the real runs or before archive

| ID | Area | Finding | Evidence | Action |
|---|---|---|---|---|
| PG-01 | PostgreSQL | The examples put the **superuser** in the API and the worker: `backend/.env.example:12` and `.env.worker.example:13` use `POSTGRES_USER`; the unit test `test_deployment_files.py:165-175` and the next one pin that equality, the opposite of DD-1; `.env.roles.example` still says "the future CLI file"; `docs/development_guide.md` (about lines 79, 102-103, 202, 241) still tells to run Alembic with `DATABASE_URL`. No startup check refuses a superuser | files and lines in the row | code/tests/docs: examples to `asistente_app` and `asistente_worker`, replace the two tests, fix the guide, add a startup tripwire (`is_superuser`). **Before group 17 (real roll-out).** Skill class: major |
| PG-02 | PostgreSQL | `db-migrate`, `db-downgrade` and `db-verify` do not assert that they connect as the migrator. A wrong or pasted administrator URL (or a shell variable that overrides the file) runs Alembic as the administrator and leaves admin-owned objects before `apply_grants` refuses (`migrate.py:27-28`, `grants.py:93-96`, `verify.py:458-461`). Only `apply_grants` has a test for a foreign identity | inspected only | code/tests: assert `current_user` at the start of the three commands, one test each. Skill class: major |
| PG-03 | PostgreSQL | The API role reads `ingestion_jobs.payload` (the bytes of every queued upload) only to compute `SUM(octet_length(payload))` (`db_privileges.py:134-136`, `document_repository.py:92,120`). Accepted by DD-3 note 2, not in the debt register | | docs: debt entry now; better, a `payload_size` column so the API needs no SELECT on `payload` (future change) |
| F-3 | Transactions | TD-039 names six endpoints. `DELETE /users/me`, `DELETE /users/me/conversations`, `DELETE /conversations/{id}` and `POST /chat` are in the spec and **do not exist in code**; when built with the default `get_db` pattern they reproduce TD-039 (an erasure answered 204 before its commit). Nothing enforces the rule structurally (no test that every non-GET route commits explicitly) | `docs/api-spec.yml:136,178,418,454,473,489`; `app/api/deps.py:29-40` | tests/docs: a route-inventory test (every POST, PUT, PATCH and DELETE route is on an allow-list of committing handlers); a note in TD-039 and in the specs of the future changes |
| B-1 / F-1 | Contract, transactions | `DELETE /subjects/{id}/documents/{doc}` commits with a bare `db.commit()` (`documents.py:243`, not `commit_or_rollback`), has no forced-refused-commit test, and the contract documents no `500` for it or for the upload, contradicting `docs/backend-standards.md` ("every endpoint that commits this way") and the wording of L30 ("all six"). Behaviour is safe (the exception reaches `get_db`, which rolls back before any body) | `documents.py:243`, `docs/api-spec.yml:327-416` | code (one line), test, spec 500, regenerate types, correct the sentence |
| C-1 | CI | The gate has never run on GitHub and is a required check only after the owner applies branch protection; the timing, runner networking and the 40-minute limit are unproven; the readiness probe uses the socket and nothing retries the first connection | `ci.yml`, `privilege_gate.sh`, `docs/development_guide.md:372-390` | owner: branch protection; docs: debt entry until the first green run; run the eight steps once on a real PR before archive |
| C-2 | CI | Result floors: unit 60 against 149 (89 tests can vanish unseen), role-suites 400 against 410, roles-mode 480 against 484; `MIN_*` are environment-overridable and no test forbids it; the guide says 133 where the report says 149 | `privilege_gate.sh:204-206`, `development_guide.md:392` | tests/docs: raise the unit floor or count per file; fix 133 to 149 |
| C-3 | Tests | The roles-mode coverage is a hand-kept list of 23 modules (`conftest.py:21-47`); about 45 other integration modules run only as the owner or superuser; the guard `test_every_module_that_builds_a_cluster_is_role_bound` detects cluster users by two import spellings. Fails safe (the ordinary job would error), but nothing fails when a new API test is simply not listed | `tests/unit/test_ci_gate_scripts.py:177-185` | tests: every integration module is in the list, in the role-bound prefixes, or in an explicit exempt list with a reason |
| D-1 | Documentation | Accepted residual risks of this change are not yet in `docs/technical-debt.md` (required by base-standards 9.8; task 18.2 is open): R1 to R10 of DD-13, the split of TD-030, PG-03, the gate unrun on GitHub (C-1), mutable action tags (C-4), the allow-list coverage (C-3), the `gc.collect()` fixture that can mask connection leaks (group 9), the CLI role reading `password_hash`, and a failure after the commit giving a 500 with the data stored | | docs, with the owner's agreement, in 15.2 or 18.2 |
| D-2 | Documentation | `development_guide.md` section 3 lists `db-adopt --apply`, `--rollback --remove-roles` and `db-migrate --downgrade` without a verified-backup, stop-services and destructive-step box (it does say they need the owner's authorisation) | `development_guide.md` about lines 117-125 | docs, before the commands are used in groups 16 and 17 |

### Low and Info

- **PG-04 (Low-Medium):** `db-verify` and `alembic check` do not see the `users.role` default `'student'`, the load-bearing control of DD-9 (`verify.py` has no default check; `alembic/env.py` has no `compare_server_default`). Action: a verify check plus a drift case.
- **PG-05:** the grants are not in the Alembic transaction; a table whose grant is table-level (`grants.py:38-40`) exposes a new column between the migration and the grants. Action: always render column lists, or document.
- **PG-06:** a stranger's column-level ACL (`pg_attribute.attacl`) is not detected by `db-verify` (only table-level).
- **PG-07:** `db-adopt --rollback` validates `--database` and then ignores it (`adopt.py:344-377`); `bootstrap --database` accepts `postgres` or `template1` and does not require it to equal the migrator URL's database.
- **PG-08:** adoption counts rows of every table inside the exclusive-lock transaction (`adopt.py:205-216`: bounded by `lock_timeout` for the locks, not for the scans); rollback is per database and can stop half-way (idempotent on re-run); bootstrap closes PUBLIC on every database of the cluster (a side effect on shared clusters) and aborts on a database name with a quote; the single-grantor `REVOKE` would not remove memberships from another grantor on PG16 or later (the image is PG15).
- **F-2 (Low-Medium):** an `OperationalError` at the commit (a connection lost) is mapped by `core/handlers.py:60-69` to `503 SERVICE_UNAVAILABLE`, not to the documented `500`; the integration tests force a `RaiseException` (500) only, and the `InternalError` text "nothing was stored" is false if the connection dies after the server committed (a retry then gets 409). Action: reword or document the 503 and add a test through the real handlers. **B-2** is the same point seen from the contract.
- **F-4:** every `SQLAlchemyError` in the upload `_store` becomes `503 retry`, including a constraint violation that a retry never fixes.
- **C-4:** actions are pinned by mutable tags and `PG_ADMIN_PASSWORD` is job-wide (`ci.yml:105-106`), against the wording of the gate header and the guide ("only the commands that need it"); the static test checks a fixed list that omits `PG_ADMIN_*`.
- **C-5:** the disposable-cluster guard trusts the host in the URL (an empty local cluster with a superuser, PG15 and pgvector 0.8.7 passes); the Python-side guard re-implements a weaker check.
- **C-6:** the scripts in `.github/scripts` get no ruff, mypy or shellcheck.
- **D-3, D-4, D-5:** `tasks.md` header says groups are "not authorised" while 3 to 14 are ticked; the summary table of `lessons-learned.md` omits L28 and L29; `.env.example` lists the `SEED_*` variables under the API file while the guide says the CLI reads them; `test_least_privilege_mode.py` says 483 tests, the report says 484; the guide says Playwright is not run in CI while `ci.yml` runs it.
- **Info:** the secrets handling of the workflow (masking before `GITHUB_ENV`, `umask 077`, no `set -x`, no `secrets.*`, `contents: read`) is inspected, only the last three are proved by static tests; the migrator-as-owner can plant operators in `public` (R9, mitigated by the verify foreign-object check); PUBLIC EXECUTE on `pg_catalog` functions (R7); `trust` inside the db container (D4); role passwords have a 16-character minimum and no entropy check; the failure after the commit gives a 500 with the data stored (inherent to commit-then-respond; proved by `tests/unit/test_endpoint_commits.py:164`); the spec says `db-verify` "reports each check as passed" while it prints "no findings".

## Verified controls against pending ones

**Verified by a named test that the reviewer read (not re-run by them):**
- no path from the API role to create a teacher or change `users.role` (`test_db_roles_teacher.py`, `test_db_roles_denied.py::test_a_role_cannot_become_another_role`); a payload asking for `teacher` creates a student;
- effective privileges equal the matrix with no unexpected grant (`test_db_roles_effective.py`); 31 parametrised drifts are reported by `db-verify` (`test_db_admin_verify.py:55-122`);
- bootstrap is idempotent and leaks no secret (`test_db_admin_bootstrap.py`); a direct online Alembic run with the settings URL is refused (`test_db_admin_grants.py`); migration 0006 upgrade and downgrade keep every user (`test_migrations_user_role_default.py`);
- adoption is a dry run by default, atomic under a lock timeout, and refuses with foreign sessions or unexpected objects (`test_db_admin_adopt.py`);
- the six endpoints commit before they answer, with a forced refused COMMIT (`test_endpoint_commit_persistence.py`, `test_consent_persistence.py`), and upload maps a failed commit to 503 with nothing left (`test_documents_api.py:362`);
- the CI summary fails on a missing, failed, skipped or short report; the disposable guard refuses remote, wrong-version and foreign clusters; the generated types match the contract.

**Pending or only inspected:**
- everything on a real GitHub runner (C-1); the secret-masking order and the absence of `set -x`;
- `migrate`/`verify` with a foreign identity (PG-02), the `users.role` default (PG-04), a stranger's column ACL (PG-06);
- a refused commit on `DELETE` of a document (F-1) and an `OperationalError` at the commit through the real handlers (F-2);
- the real development stack under the roles (TD-040), the browser behaviour (TD-041), the rehearsal and roll-out (groups 16 to 18);
- the mutation quality of the CI gate: the 29 text mutations only prove that static tests notice an edit; the behaviour comes from nine local scenarios on a harness; the group-9 role-suite mutations (11) are a good selection but the other matrix rows, the repository scoping under the roles and the 403/404 guards were not mutated; mutation 0 changes two things at once.

## Status of the debt items

- **TD-039:** resolved in code and tests for the six endpoints it names; **not completely closed as a risk**: F-1, F-2 and F-3 widen or qualify it. Recommended: keep it `open` and extend its text (list the final set, the planned erase and chat endpoints, the structural guard).
- **TD-040:** unchanged and accurate (the development stack still runs as the owner; also, the real `backend/.env` and `.env.worker` still hold the superuser, expected before group 17; PG-01 is the same risk in the examples).
- **TD-041:** accurate; the browser rehearsal and the main-flow E2E remain open.

## Documentation coherence

TD-039, TD-040 and TD-041 match the evidence; the OpenSpec artifacts, the matrix and the code agree except PG-01 (examples and a test against DD-1), PG-10 (spec wording of `db-verify`) and the stale guide lines. The copies in `.claude` and `ai-specs` agree (the `openspec-*` skills exist only in `.claude`, as base-standards section 6 says); no agent or skill was modified.

## Incident of this review

One reviewer printed a password of the real development `.env` (`POSTGRES_*`) into its own tool output while checking which user the files use. It was not copied into any file or report, and nothing was changed. It stays in that subagent's transcript. It is a local development value that TD-038 already lists as not rotated; rotation belongs to group 17 and the owner may want to bring it forward.

## Verdict: PASS WITH GAPS

No critical or high finding. In the skill's terms, PG-01 and PG-02 are **major** (fix before group 17), and the other medium items are tracked minors or documentation to do before archive. Archiving is **not advisable yet**: groups 15.2 and 16 to 19 are open.

## Recommendation for group 16

**GO, conditional**, because there are no critical or high findings, and because group 15 is titled "required before any real run":
1. Authorise task **15.2** first, limited to the blocking items for the real runs: PG-01 and PG-02 (code and tests), F-1, B-1 and F-2 (code, test, spec, regenerated types), the debt entries for D-1 and the TD-039 widening, and the safety box of D-2 (docs); then a focused second review of what 15.2 touches, as the task requires.
2. The rest (F-3 guard, PG-03 column, PG-04 to PG-08, C-2 to C-6, D-3 to D-5) can follow in 15.2 or be recorded as debt with the owner's agreement.
3. Group 16 uses a restored copy and not the development database, but it exercises `db-adopt`; PG-07 and PG-08 should be known to whoever runs it.
