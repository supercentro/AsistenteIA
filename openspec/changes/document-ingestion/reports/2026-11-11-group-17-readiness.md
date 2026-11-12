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
| 17.3 security and isolation | **Ticked** as a technically validated correction (user approval of 2026-11-11); the GitHub alert is still open and closes only after the merge; mandatory post-merge check recorded in `tasks.md` and TD-036 (see section 4) | `pip-audit`: no known vulnerabilities; lock files committed (`backend/uv.lock`, `frontend/package-lock.json`); no secret in the diff against `main` (only a test fixture string); repository reads and deletes scoped by subject and teacher; `npm audit` after the override: 0 vulnerabilities (7 moderate findings, all the chain of `minimatch` 10.2.6, before) |
| 17.4 lint and format | Passed | `ruff check --no-cache` clean, `ruff format --check` 174 files; frontend `eslint .` clean, `prettier --check` clean, `tsc -b --noEmit` clean, `vitest` 236 passed in 16 files, `vite build` ok, `check:api-types` up to date |
| 17.5 migrations | **Ticked against the revised criterion** (user approval of 2026-11-11, `/opsx:update`): isolated PostgreSQL 15 + pgvector verification replaces `alembic check` on development, which was not run and is not claimed; `asistenteia` stays at `0004`; applying `0005` to development is a future independent operation (revision record in `tasks.md`) | `0005` upgrade, downgrade and `alembic check` clean on a clean database are covered by `test_migrations_ingestion.py` (in the suite); the test database is at `0005` with `ingestion_jobs`; the development database `asistenteia` is at `0004` and has no `ingestion_jobs` (read-only query), as the user instructed (the `alembic check` of the task on the development database requires applying `0005`, which is not authorised); `0004` and earlier migrations are unchanged (`git diff` against `main` adds only `0005`); real `docker compose` project (disposable `g16c`): database and worker start, worker `healthy`, code mount read-only, worker killed mid-job restarts and recovers the job without duplicate chunks, stalled worker restarts, no container left |
| 17.6 documentation and traceability | Passed | Limits (10 MB, 50 documents per subject, 2,000 chunks, 100 jobs) and status codes (202, 204, 400, 409, 413, 415, 422, 429) agree across `docs/api-spec.yml`, the delta specs, `docs/data-model.md`, `docs/development_guide.md`, the settings and the tests; `test_api_contract.py` compares the OpenAPI of the application with `docs/api-spec.yml`; no archived spec, earlier migration, skill, agent, `prompts.md` or `readme.md` changed |
| 17.7 OpenSpec validation | **Ticked** | `openspec validate document-ingestion --strict` valid and `--all --strict` 15 of 15, run after the last change; all 17 groups and 56 tasks are ticked |

Groups 0 to 16 are all ticked (49 tasks) and each has a report in `reports/`.

## 3. Playwright

The committed Playwright suite runs in the CI frontend job (green on `9cb6c98`). This change has no UI; the frontend regression was verified in group 14.

## 4. Dependabot #1 (TD-036): alternative B applied (commit `7da9be9`)

Approved by the user on 2026-11-11 (alternative B, evaluated and kept only because it proved compatible). Diagnosis before the change: `npm ls minimatch` showed 10.2.6 only under `typescript-eslint` 8.72.1 > `@typescript-eslint/typescript-estree` 8.72.1, while `eslint`, `@eslint/config-array`, `@eslint/eslintrc` and `eslint-plugin-jsx-a11y` use 3.1.5 and `@redocly/openapi-core` (through `openapi-typescript`) uses 5.1.9, both outside the advisory range (`>= 7.0.0, < 11.0.1`, patched 11.0.1; `npm audit` and the Dependabot API agree); `typescript-eslint` latest stable is 8.72.2 and still asks for `minimatch ^10.2.2`.

Override (`frontend/package.json`, scoped to the affected consumer, no global override):

```json
"overrides": { "@typescript-eslint/typescript-estree": { "minimatch": "11.0.8" } }
```

`package-lock.json` changes: `minimatch` 10.2.6 to 11.0.8 (engines `20 || >=22`; the repository requires Node `>=20.19` and CI uses Node 24), `brace-expansion` range `^5.0.12` (the installed 5.0.12 already satisfies it) and the new dependency `@isaacs/nonrecursive-glob-match` 1.1.0 (same maintainer as `minimatch`). npm 11 also tried to add six optional bundled `@tailwindcss/oxide-wasm32-wasi` entries that are unrelated (a plain `npm install --package-lock-only` on the old files does the same); they were removed so the lock diff is only the three items above. The previous `package.json` and lock are saved in the scratchpad (`dep_backup`) and in git.

Results: `npm ci` ok; `npm ls minimatch` shows `minimatch@11.0.8 overridden` under `typescript-estree` and the other consumers unchanged; `npm audit` 0 vulnerabilities (not taken as proof: the checks below were also run); `eslint .` clean, `prettier --check` clean, `tsc -b --noEmit` clean, `check:api-types` up to date, Vitest 236 passed in 16 files, `vite build` ok, Playwright with mocks 11 passed and 6 skipped (the local port 5173 is occupied by another project's Vite server, so the suite ran against our own server on port 5199, stopped afterwards; CI runs it on its own runner), and a type-aware ESLint run (`recommendedTypeChecked`, `projectService.allowDefaultProject` with globs) that applied `no-floating-promises`, `require-await` and `no-explicit-any` to a probe file, so the globs go through `minimatch` 11.0.8, and linted four repository files with no fatal error.

Status of the alert: GitHub evaluates the default branch, so alert #1 stays open until this branch is merged to `main`; it is to be confirmed closed after the merge. The risk left is that the override forces a major version under a package that declares `^10`; it is removed when a stable `typescript-eslint` depends on `minimatch >= 11.0.1`.

## 5. Residual risks

TD-030 (PDF isolation and privileges, open, partially mitigated), TD-034 (worker monopolisation residual and T-01, accepted provisionally for the controlled MVP only), TD-035 (in-memory upload limiter, planned), TD-036 (Dependabot, open) and TD-037 (timing sensitivity of tests, open) are all registered and none is reinterpreted as eliminated.

## 6. Readiness

**Ready for merge**, subject to the user's explicit approval. No functional blocker remains; the two OpenSpec decisions (17.3 and 17.5) were approved on 2026-11-11 and are recorded in `tasks.md`. After the merge: confirm that Dependabot alert #1 is closed (otherwise investigate and correct before declaring TD-036 resolved) and apply `0005` to the development or deployment database only under its own authorisation, after a backup.
Before any deployment: apply `0005` to the target database with the documented preflight; provide `backend/.env`, `backend/.env.worker` and `backend/.env.db` with real secrets; review TD-030, TD-034 and TD-035 before exposing the service to untrusted users; re-evaluate the embedding model in change 12.
