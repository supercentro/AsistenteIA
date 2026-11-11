# Group 17: final verification of the MUST quality gates and readiness

Date: 2026-11-11. Branch `feature/document-ingestion`, starting HEAD `9cb6c98`, PR #8 (open, not merged).
No code, migration, dependency, archived spec, skill or agent was changed in this group.

## 1. Preflight

Branch and HEAD as expected; PR #8 open, `CLEAN`, four checks green; the working tree only had the seven untracked reference documents (untouched); `openspec validate document-ingestion --strict` valid and `--all --strict` 15 of 15.

## 2. Results by task

| Task | Result | Evidence |
|---|---|---|
| 17.1 typing and validation | Passed | `mypy --strict app tests`: no issues in 174 files; `POST`, `GET` and `DELETE` of documents declare `response_model` (`Document`, `list[Document]`) or an empty 204; upload validated (extension, sniffed type, size) before processing by `upload_guard` and `upload_inspection` (tests in `test_documents_api.py`, `test_upload_guard.py`, `test_upload_inspection.py`, `test_upload_server.py`) |
| 17.2 testing | Passed | Full backend suite on Linux with real PostgreSQL and pgvector: 1,839 passed, 8 skipped, 23 deselected (`realmodel`), 0 failed, 10 min 39 s, coverage 99 % (`normalizer.py`, `chunker.py` 100 %, `ingestion_service.py` 99 %, `worker_health.py` 95 %); the 23 `realmodel` tests passed separately (20.9 s); real-server tests of group 10 are part of the suite; authorization negatives and isolation in `test_documents_api.py`, `test_documents_leaks.py` and `test_document_repository.py`; no external service is called (fakes only); TDD evidence in `2026-11-08-tdd-evidence.md` and the group reports |
| 17.3 security and isolation | **Open: Dependabot #1** | `pip-audit`: no known vulnerabilities; lock files committed (`backend/uv.lock`, `frontend/package-lock.json`); no secret in the diff against `main` (only a test fixture string); repository reads and deletes scoped by subject and teacher; `npm audit`: 7 moderate findings, all the chain of `minimatch` 10.2.6 (see section 4) |
| 17.4 lint and format | Passed | `ruff check --no-cache` clean, `ruff format --check` 174 files; frontend `eslint .` clean, `prettier --check` clean, `tsc -b --noEmit` clean, `vitest` 236 passed in 16 files, `vite build` ok, `check:api-types` up to date |
| 17.5 migrations | Passed, with one stated deviation | `0005` upgrade, downgrade and `alembic check` clean on a clean database are covered by `test_migrations_ingestion.py` (in the suite); the test database is at `0005` with `ingestion_jobs`; the development database `asistenteia` is at `0004` and has no `ingestion_jobs` (read-only query), as the user instructed (the `alembic check` of the task on the development database requires applying `0005`, which is not authorised); `0004` and earlier migrations are unchanged (`git diff` against `main` adds only `0005`); real `docker compose` project (disposable `g16c`): database and worker start, worker `healthy`, code mount read-only, worker killed mid-job restarts and recovers the job without duplicate chunks, stalled worker restarts, no container left |
| 17.6 documentation and traceability | Passed | Limits (10 MB, 50 documents per subject, 2,000 chunks, 100 jobs) and status codes (202, 204, 400, 409, 413, 415, 422, 429) agree across `docs/api-spec.yml`, the delta specs, `docs/data-model.md`, `docs/development_guide.md`, the settings and the tests; `test_api_contract.py` compares the OpenAPI of the application with `docs/api-spec.yml`; no archived spec, earlier migration, skill, agent, `prompts.md` or `readme.md` changed |
| 17.7 OpenSpec validation | Run; not ticked | `--strict` valid and `--all --strict` 15 of 15; it is ticked only when 17.3 closes |

Groups 0 to 16 are all ticked (49 tasks) and each has a report in `reports/`.

## 3. Playwright

The committed Playwright suite runs in the CI frontend job (green on `9cb6c98`). This change has no UI; the frontend regression was verified in group 14.

## 4. Dependabot #1 (TD-036): decision needed

Re-analysed on 2026-11-11: `minimatch` 10.2.6 (GHSA-g3hv-75wg-m249, `>=7.0.0 <11.0.1`, moderate) enters only through `typescript-eslint` 8.72.1 and `@typescript-eslint/typescript-estree` 8.72.1, a development dependency used when linting. The latest stable `typescript-eslint` is 8.72.2 and still depends on `minimatch ^10.2.2`; only the prerelease `8.72.3-alpha.x` (dist-tag `canary`) moves to `^11`. `npm audit fix --force` proposes an unrelated downgrade and is not used. Nothing was changed.

Options for the user: (a) wait for a stable `typescript-eslint` with `minimatch >= 11.0.1` (none exists today); (b) an `overrides` entry forcing `minimatch` 11.0.8 (the latest stable; Node `20 || >=22`, CI uses Node 24; `typescript-estree` only calls `minimatch(...)`), a major version under a package that declares `^10`, to be followed by `npm audit`, lint, typecheck, tests, build, `check:api-types`, Playwright and CI; (c) formal acceptance as a development-only residual risk (Low impact: runs only on the repository's own globs, never on user input, not in the production bundle; this is not a reason to dismiss the alert).

## 5. Residual risks

TD-030 (PDF isolation and privileges, open, partially mitigated), TD-034 (worker monopolisation residual and T-01, accepted provisionally for the controlled MVP only), TD-035 (in-memory upload limiter, planned), TD-036 (Dependabot, open) and TD-037 (timing sensitivity of tests, open) are all registered and none is reinterpreted as eliminated.

## 6. Readiness

**Not ready to merge** until the decision on Dependabot #1 (task 17.3) is made and, if option (b) is chosen, verified. Everything else passes.
Before any deployment: apply `0005` to the target database with the documented preflight; provide `backend/.env`, `backend/.env.worker` and `backend/.env.db` with real secrets; review TD-030, TD-034 and TD-035 before exposing the service to untrusted users; re-evaluate the embedding model in change 12.
