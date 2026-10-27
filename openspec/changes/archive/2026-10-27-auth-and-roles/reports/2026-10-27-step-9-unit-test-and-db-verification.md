# Step 9 Report - Unit Tests and Database Verification

- Date: 2026-10-27
- Change: auth-and-roles
- Agent: Claude Code (Sonnet 5.5)

## Commands Executed
- `psql` snapshots (extensions, public tables) of `asistenteia` and `asistenteia_test` before and after
- `uv run pytest tests/unit` and each integration module separately
- `uv run pytest tests --cov=app --cov-report=term-missing -q`
- `uv run ruff check .`, `ruff format --check .`, `mypy --strict app tests`
- Frontend: `npm test`, `npm run lint`, `npm run format:check`, `npm run typecheck`

## Results
| Scope | Result |
|---|---|
| `tests/unit` | 129 passed |
| `test_auth_register.py` | 12 passed |
| `test_auth_login.py` | 8 passed |
| `test_auth_rate_limit.py` | 6 passed |
| `test_users_me.py` | 13 passed |
| `test_role_guards.py` | 6 passed |
| `test_consent.py` | 10 passed |
| `test_cli.py` | 28 passed |
| `test_user_repository.py` | 7 passed |
| `test_migrations.py` | 3 passed |
| `test_auth_logging.py` | 2 passed |
| Full suite | 231 passed, 0 failed, 0 skipped (about 22 s) |
| Coverage | 97 % of `app`; `services/` 100 %, `repositories/` 100 %; `cli.py` 86 % (the `main()` wiring and `__main__` guard are exercised by the curl step, not by unit tests) |
| Frontend Vitest | 3 passed (App, privacyPolicy) |

Notes: flaky tests: none observed. The rate-limit "window elapsed" test uses a real 1.2 s sleep with a `2/second` limit (the `limits` library does not accept an injected clock), a deviation from design D13 ("injectable clock").

## Database State Verification
- Pre-test baseline:
  - `asistenteia` (development): extensions `plpgsql`; no tables.
  - `asistenteia_test`: extensions `plpgsql,vector`; tables `alembic_version,users` (leftover schema from the earlier development runs of this change, before the session fixture started dropping it).
- Post-test validation:
  - `asistenteia`: unchanged (`plpgsql`, no tables). The isolation guard keeps tests away from it.
  - `asistenteia_test`: extensions `plpgsql`, no tables (the `migrated_db` session fixture now drops everything at the end).
- State restored: Yes.

## Outcome
- Step 9 status: PASS
- Blocking issues: none

## Update after F8 (final)
Full run: **344 passed**, 97 % coverage, `pip-audit` clean (completed run), `npm audit` 0, Vitest 3, Playwright 2, `alembic check` clean on the migrated development database.

## Update after the independent review
Full run: **305 passed**, 97 % coverage (`services/`, `repositories/`, `rate_limit.py`, `handlers.py` 100 %), `alembic check` clean, `npm audit` 0, Playwright 2 passed.

## Update after the review follow-ups
Added: registration rate limiting tests (7 integration + 2 settings), real-process CLI tests (`test_cli_process.py`, 9), adversarial probes (13), JWT strictness tests. Final full run: **274 passed**, 97 % coverage (`services/` and `repositories/` 100 %, `rate_limit.py` 100 %, `cli.py` 86 % in-process plus the real-process tests above), ruff/format/mypy strict clean, `npm audit` clean, frontend 3 Vitest + 2 Playwright passing. `pip-audit` was clean on the last run that completed (no dependency changed since); the final reruns timed out reaching pypi.org (network), so it is re-checked by CI.
