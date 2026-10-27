# Final Review Report - project-scaffold

- Date: 2026-10-27
- Agent: Claude Code (Sonnet 5.5)
- Branch: `feature/project-scaffold` (no commits, pushes, PR or archive performed)

## Process deviation: TDD on `GET /api/v1/health`

Tasks 4.1 (failing tests) and 4.2 (implementation) require the health tests first. In practice the
implementation of `health.py`, the `get_db` dependency, the exception handlers and `create_app` was written in a
single step together with the error-handling code (task 3.4), **before** the health integration tests of task 4.1
existed. The health tests were written afterwards and passed on first run, so they were never observed failing
for the endpoint itself. Everything else followed test-first: settings (`test_config.py` failed on missing
module), error handling (`test_api_errors.py` failed on missing module), isolation guard (`test_db_safety.py`
failed on missing module) and the migration test (could not pass without `alembic.ini`).
Mitigation: no code was changed because of this deviation. The health behaviour is additionally covered by the
curl checks (step 11, including the real 503 with the database stopped) and by the 503 integration test against
an unreachable port. Recommendation: in the next changes write and run the failing integration test before the
router.

## Review of the diff against `main`

- Inventory: 2 modified tracked files (`docs/api-spec.yml`, `docs/development_guide.md`); new: `backend/`,
  `frontend/`, `docker-compose.yml`, `docker/db-init/`, `.github/workflows/ci.yml`, `.gitattributes`,
  `openspec/changes/project-scaffold/`. `readme.md` and `prompts.md` untouched.
- Secrets: pattern scan (password/secret/token/api key assignments, 32-hex strings) over all non-ignored new
  files found nothing; the generated local database password is not present in any non-ignored file. Real
  `backend/.env` and `frontend/.env` exist locally and are git-ignored. `.env.example` files contain
  `CHANGE_ME` placeholders only. The only literal credential is the throwaway CI service-container password
  `ci_password_not_a_secret` (ephemeral container, no external exposure).
- Not versioned (ignored): `.venv`, `node_modules`, `dist`, caches, `__pycache__`, `.coverage`,
  `.playwright-mcp`, `test-results`. Lock files `backend/uv.lock` and `frontend/package-lock.json` are included.
- Cleanups found by the review: removed the unused template file `frontend/.oxlintrc.json`; reduced
  `.gitattributes` to `*.sh text eol=lf` (a repo-wide `* text=auto` was out of scope); bound the published
  ports of `backend` and `frontend` to `127.0.0.1` like the database.
- Dependencies: runtime backend = fastapi, uvicorn, pydantic-settings, sqlalchemy, alembic, psycopg; no LangChain,
  Gemini, sentence-transformers or torch. `pip-audit` and `npm audit`: no known vulnerabilities.

## Scope check (60 tasks)

All 60 tasks belong to the approved plan (groups 0-14 of `tasks.md`). No business feature was added: no users,
auth, tables, endpoints other than `/health`. Items beyond the literal task text, all within the design:
`NotFoundPage` and its test, `METHOD_NOT_ALLOWED` error code, `UnauthorizedError`/`ConflictError` classes (in
design D5), `@testing-library/user-event` installed but not yet used (needed by later component tests).

## Documentation changes in this review
`design.md` D11 and `specs/dev-environment/spec.md` now describe the guard as implemented (name check regardless
of host, abort behaviour, no credential disclosure, accepted limits).

## Follow-up applied after review approval
- Connection timeout (`DB_CONNECT_TIMEOUT_SECONDS`, default 5): tests written first and seen failing (7 failures), then implemented. Includes an integration test with a TCP server that accepts and never answers (503 in < 5 s).
- Guard tests that no engine/connection is created for unsafe configurations (also re-check in destructive helpers); a temporary mutation removing the re-check made 2 tests fail, then the code was restored.
- Full backend suite now 62 tests.

## Verification after the review adjustments
Backend ruff/format/mypy strict clean, 62 tests pass (98 % coverage); frontend lint/format/typecheck clean, 2 unit tests and 2
Playwright tests pass; `docker compose up --build` healthy (health 200, frontend 200) on loopback ports;
`openspec validate project-scaffold --strict` valid.
