# rag-source-attribution slice 1: verification (2026-11-21)

No real call to Gemini was made. Branch `feature/rag-source-attribution` from `main` 301ad9a. Nothing committed.

## TDD evidence
- Failing run before the code: `reports/_failing_run.txt` (18 failed, 97 passed: the new tests in `test_prompt_builder.py`, `test_rag_service.py`, `test_evaluation_attribution.py`).
- After the implementation: the same files, 205 passed together with the evaluation tests (107 + new).
- Mutations (`reports/_mutations.txt`): 12 of 12 detected (history, chunk text and filename not neutralised; list form not read; range accepted; spaces next to the brackets accepted; labels altered; current question neutralised; snippet altered; fallback removed; out-of-range kept; harness reader detached).

## Gates (after the last change)
- `ruff check --no-cache`, `ruff format --check`, `mypy --strict app tests`: clean.
- Unit suite: 1617 passed; 4 failed, the same four Windows-host-only failures as before (paths, subprocess environment), unrelated files.
- Integration suite: 980 passed, 37 skipped, 444 errors: all errors are the `privileges` tests refusing to run without `TEST_CLUSTER_IS_DISPOSABLE=true` (they run in the CI `privileges` job); the same error appears on `main` with this change stashed.
- `openspec validate --all --strict`: see the final run in the report of the session.

## Database state
Unit tests and the harness never touch the development database. After the integration run the test database `asistenteia_test` holds 0 users, 0 subjects and 0 messages.

## Deviation (step N+2, manual endpoint test)
No endpoint, request or response changed, and `/chat` on the development stack would call the real model, which is not authorised. Verified instead with the integration tests of `/chat` against PostgreSQL (in the 980 passed) and the service test with a fake model that checks the prompt and the stored sources.

## Limits
The effect on a real model is not measured (baseline 3.3b pending). Only the mechanics are proven. TD-062 stays open.
