# Step 3.2 Report - Unit tests and database verification

- Date: 2026-11-20
- Change: rag-golden-set-evaluation
- Agent: Claude (implementing session)

## Commands Executed (from `backend/`)
- `uv run --no-sync ruff check --no-cache .` and `ruff format --check .`
- `uv run --no-sync mypy --strict app tests`
- `uv run --no-sync python -m pytest tests/unit -q`
- `uv run --no-sync python -m pytest tests/integration -m "not role_bound and not realmodel" -q` (the CI selection)
- harness runs in the backend container (see the step 3.3 report)

## Results
- ruff: clean (301 files formatted); mypy strict: no issues in 282 files; `git diff -- backend/app` empty (no product file changed).
- Unit suite: **1576 passed, 110 skipped, 4 failed**. The four failures are in files this change did not touch and fail the same way on this Windows host without the change: `test_worker_health::test_the_defaults_leave_room_for_the_beat_interval` (a `/tmp` path becomes `\\tmp`), `test_worker_settings` (two tests that start a subprocess with the API absent) and `test_migration_settings::test_alembic_refuses_to_use_the_application_url` (depends on the host environment). CI runs on Linux and passed on `main` (8d028ce) with the same code; the harness tests are not involved.
- Integration suite (CI selection): **966 passed, 35 skipped** in two complete runs after the last code change; one earlier complete run ended with `1 error` at teardown that did not repeat in the next run (not investigated further; recorded here).
- Evaluation tests: 84 passed (unit 70 + integration 14).

## Database State Verification
- Development database `asistenteia` (read-only counts before and after every harness run and every suite run): users 27, subjects 8, documents 15, enrollments 8, conversations 25, messages 70, message_sources 43, chunks 75 (the owner's manual test data; **identical before and after**).
- Test database `asistenteia_test`: empty (0 tables) before and after. The harness creates the schema only with `--create-schema`, removes its synthetic rows and drops the schema it created; the integration suite drops and rebuilds it as it always did.
- No container of the harness remains (`docker ps -a` has none).

## Real services
- Gemini free tier: 44 logical calls in the first answers run (library retries were on, so the real number of requests is unknown), none since. See the step 3.3 report.

## Outcome
Step 3.2 status: PASS for the change (the four Windows-only unit failures predate it and are outside it).

## Update 2026-11-21 (after the second review and the request ledger)

Re-run after the last code change: ruff and format clean (303 files), `mypy --strict` clean (284 files), `git diff -- backend/app` empty. Unit suite: 1591 passed, 110 skipped, the same 4 Windows-only failures in files this change does not touch. Integration suite (CI selection): **974 passed, 35 skipped**. Evaluation tests: **107 passed** (85 unit, 22 integration). Development database counts identical to the baseline (27 / 8 / 15 / 8 / 25 / 70 / 43 / 75 users, subjects, documents, enrollments, conversations, messages, sources, chunks); `asistenteia_test` empty. No real Gemini call was made on 2026-11-21.
