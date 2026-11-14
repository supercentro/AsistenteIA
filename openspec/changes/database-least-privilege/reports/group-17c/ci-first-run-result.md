# First real GitHub Actions run of the branch (J2), 2026-11-14

Authorised: publish `feature/database-least-privilege` (only that ref; no PR, no merge, no force) and verify the first run. Push of `53031a1` (72 commits on top of `main` = `3b312e4`); nothing else was published (no tags, no `refs/backup`, no `refs/original`, `main` unchanged). Run: https://github.com/supercentro/AsistenteIA/actions/runs/43621336229 (event `push`). The log was read from outside the repository; only counts, durations and step names are recorded here. No secret and no user name appears in the log (the only credential-like strings are the documented throw-away `*_not_a_secret` values of the CI clusters).

| Job | Result | Duration | Tests |
|---|---|---|---|
| `frontend` | success | 101 s | 236 unit/component tests in 16 files passed (statement coverage 97.68 %); 11 browser tests (Playwright, mocked API) passed; `npm audit`: 0 vulnerabilities |
| `privileges` | success | 279 s | 1 072 privilege tests, 0 failed, 0 errors, 0 skipped: 149 unit (floor 60), 439 role-bound suites (floor 400), 484 roles mode (floor 480); all steps green including the exclusive/empty/local cluster check, the flow to 0006 with `db-verify`, the drift self-check and the summary step |
| `backend` | success | 397 s | 1 388 unit tests passed (1 skipped), 864 integration tests passed (439 role-bound deselected, run in `privileges`); coverage 70 % |

Observations (none blocks the gate):
- The one skipped test is `tests/unit/test_pdf_child.py:107` ("AES encryption needs the cryptography package") in the `backend` job; a privilege suite never skips and the `privileges` job would fail on any skip.
- `pip-audit` (non-blocking) reports 2 known vulnerabilities in `backend/uv.lock`: `dnspython 2.9.0` (fix 2.9.2, GitHub rates it high) and `opentelemetry-api 1.45.1` (fix 1.45.2, medium). They are the same two alerts Dependabot already shows for `main`; they are not introduced by this branch. To be handled as a separate dependency update.
- TD-045: the timing, runner networking and 40-minute limit are now measured (privileges 279 s). Branch protection is still unavailable on this plan, so the job is advisory.
