# Step 6 Report - Unit Tests and Database Verification

- Date: 2026-10-28
- Change: subjects-and-enrollments
- Agent: Claude Code (Sonnet 5.5)

## Commands Executed (from `backend/`)
- `uv run pytest tests/unit tests/integration/test_migrations_subjects.py tests/integration/test_subject_repositories.py tests/integration/test_subjects_api.py tests/integration/test_enrollments_api.py -q` (targeted)
- `uv run pytest --cov=app --cov-report=term -q` (full suite with coverage)
- `uv run ruff check .`, `uv run ruff format --check .`, `uv run mypy --strict app tests`

## Unit Test Results
- Targeted tests: 300 passed, 0 failed, 0 skipped (all unit tests plus the new migration, repository and API suites).
- Full suite: **476 passed**, 0 failed, 0 skipped, about 62 s (baseline before this change: 344).
- Coverage: total 98 %; `services/` 100 % (`subject_service`, `enrollment_service`, `auth_service`, `consent_service`, `user_admin_service`); `repositories/` 97 % to 100 % (the only uncovered line in each new repository is the defensive re-raise of an unrelated `IntegrityError`); `schemas/validators.py` 100 %; the two new endpoint modules 100 %.
- Lint, format and `mypy --strict`: clean.
- Notes: no flaky behaviour observed. The concurrency tests (8 parallel identical requests) passed on every run.

## Mutation Checks
See `2026-10-28-mutation-checks.md`: 13 mutations of actor filters, ownership checks and the log defences, all killed.

## Database State Verification
- Pre-test baseline:
  - `asistenteia` (development): extensions `plpgsql`, `vector`; alembic `0003` (applied during task 2.3); tables `alembic_version`, `enrollments`, `subjects`, `users`; rows 0 / 0 / 0.
  - `asistenteia_test`: no tables, extension `plpgsql` only (the suite builds and drops the schema itself).
- Post-test validation: identical to the baseline for both databases (the integration suite only touches `asistenteia_test`; the isolation guard of the scaffold change stayed active).
- State restored: not needed (no residue).
- Note: during task 2.3 the compose backend container (image without `0003`) ran `alembic downgrade -1` and `upgrade head` on `0002` against the development database. It held 0 users, so no data was lost; afterwards `0003` was applied from the host.

## Outcome
- Step 6 status: PASS
- Blocking issues: none
