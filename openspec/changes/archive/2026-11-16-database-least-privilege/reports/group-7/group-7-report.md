# Group 7: POST /users/me/consent commits before it answers (2026-11-13)

Scope: only `POST /api/v1/users/me/consent`. No real database, role, `.env` file or container of the project was touched; tests ran on disposable PostgreSQL 15.19 + pgvector 0.8.7.

## Tasks

| Task | Result |
|---|---|
| 7.1 failing tests first | `tests/unit/test_consent_endpoint.py` (6 tests, recording session) and `tests/integration/test_consent_persistence.py` (5 tests, real application role). RED: `tdd-red-unit.txt` (signature failure of the new `db` argument, 4 failures) and `run-integration-red.txt` (`assert 200 == 500`: PostgreSQL refused the UPDATE after the 200 was sent; 2 failed, 3 passed) |
| 7.2 explicit commit | `users.py`: `service.record`, then `db.commit()` (rollback and re-raise on error), then the response. `docs/api-spec.yml`: 500 `INTERNAL_ERROR` added to the consent endpoint |
| 7.3 standard and audit | `docs/backend-standards.md` section 7 (rule and audit); TD-039 for register, subjects and enrollments |

## Evidence

- GREEN: unit 6 passed; integration `test_consent_persistence.py` 5 passed (`run-integration-green.txt`); legacy consent, profile and registration tests 35 passed (`run-integration-legacy-consent.txt`). Mixing the new file with the legacy ones in one harness process errors because the `cluster` fixture drops every `tstdb_*_test` database, including the harness guard database `tstdb_guard_test`; this is a harness artefact, not a CI issue.
- Persistence and rollback: the 200 is read back from a separate administrator session; with `UPDATE (consent_version, consent_accepted_at)` revoked from the application role the answer is 500 `INTERNAL_ERROR`, the row stays `(NULL, NULL)`, neither the email, the password, the hash nor the administrator password appear in the response or captured logs; after the privilege returns, the same client succeeds (no broken session left); a wrong version is 422 with nothing stored; a second acceptance is idempotent.
- Mutations (`mutation-unit.txt`): 8 of 8 caught (no commit, flush only, no rollback, swallowed error, commit before the update, rollback only for ValueError, double commit, no version check). Against PostgreSQL the first mutation is the pre-fix code, shown failing in the RED run.

## Independent review (read-only, clean context): PASS WITH GAPS

| ID | Disposition |
|---|---|
| G7-1 (High) no integration GREEN | fixed: run obtained once 6 GB were free; tasks were un-ticked meanwhile |
| G7-2 (Medium) integration mutation run cited but missing | fixed: docstring corrected; the pre-fix RED run is the integration mutation, the others are unit-only (stated) |
| G7-3 (Low) uncovered variants | fixed: tests for non-SQLAlchemy errors and a failing rollback, mutation "only ValueError" added |
| G7-4 (Low) test name | fixed: renamed `..._after_the_200`; ordering is proven by the unit test |
| G7-5 (Low) only endpoint with a 500 in the spec | accepted: documents also commit explicitly and declare none; to align in the TD-039 change |
| G7-6 (Low) audit wording | fixed |

## Gates

ruff check and format clean; mypy strict 212 files; unit 1116 passed plus the 3 known Windows baseline failures; integration collection 1226; `openspec validate --all --strict` 18/18.

## Six extra INSERT columns

Recorded, not implemented: `six-columns-for-next-authorisation.md`.
