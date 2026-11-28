# Step 8 Report - Unit Tests and Database Verification

- Date: 2026-11-28
- Change: frequent-questions-and-topics
- Agent: Claude Code (Claude Sonnet 5.5)

## Environment

Disposable PostgreSQL 15 + pgvector 0.8.7 on `tmpfs`. Linux suites in a local image (the worker image plus the locked development dependencies) on an internal network, worktree mounted read-only. No command targeted the owner's database; Gemini was not called.

## Commands and results (final state)

| Command | Result |
|---|---|
| `mypy --strict app tests` (Linux) | no issues, 322 files |
| `pytest tests/unit` (Linux) | 2049 passed, 11 skipped (git not available in the container), 23 deselected, 2 xfailed |
| `pytest tests/integration -m "not role_bound and not realmodel"` (Linux) | 1163 passed, 454 deselected; total coverage 77% (the role-bound code is covered by the other job); new modules 92-100% |
| `privilege_gate.sh` (all steps) | 1142 tests, no drift, `alembic check` clean |
| `ruff check --no-cache`, `ruff format --check` | clean |
| `npm run lint / typecheck / format:check / check:api-types / build` | all exit 0 |
| `vitest run --coverage` | 708 passed, 1 skipped, 48 files; 96.7% statements |
| `npm run test:e2e` | 36 passed, 9 skipped (real-backend specs) |
| `npm audit` | 0 vulnerabilities |
| `pip-audit` | not run; no backend dependency changed |

After the integration and privilege runs, one unused `type: ignore` comment was removed from a test; lint, `mypy`, the unit suite and that test file (18 passed) were run again.

On the Windows host three unit tests of the worker fail with or without this change (POSIX paths and subprocess environment); they pass on Linux.

## Database state

- Before: empty disposable databases. After: the fixtures drop everything (0 tables in the test database).
- The containers of the Linux runs were removed. The owner's containers and volumes were not touched.

## Outcome

PASS at the time of this step. The later independent review, the corrections and the final figures are in `2026-11-28-step-12-adversarial-review.md`.
