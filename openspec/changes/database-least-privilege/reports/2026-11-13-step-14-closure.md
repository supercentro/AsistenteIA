# Step 14 closure: finding F-14-1 corrected (2026-11-13)

Branch `feature/database-least-privilege`, starting from `c2eb837`. Authorised scope: correct F-14-1 with option A, complete the associated documentation and close group 14. Nothing was pushed, the new workflow has not run on GitHub Actions, no browser, API, frontend server or Docker service was started, the development database and worker were not touched, and no React component, frontend logic, dependency, `.env`, role or password was changed. The mocked Playwright suite was **not run** in this group (it runs in CI); no browser E2E was executed.

## What changed and why

| File | Change | Reason |
|---|---|---|
| `docs/api-spec.yml` | new `components/responses/InternalError` (standard `Error` schema, code `INTERNAL_ERROR`); `500` added to `POST /auth/register`, `POST /subjects`, `DELETE /subjects/{subject_id}`, `POST /subjects/{subject_id}/enrollments`, `DELETE /subjects/{subject_id}/enrollments/{student_id}`; the inline `500` of `POST /users/me/consent` now references the same response | these six handlers call `commit_or_rollback` before building the response (TD-039, DD-15), so a write that the database refuses answers `500`; only consent was documented (F-14-1, F-14-4) |
| `frontend/src/types/api.generated.ts` | regenerated with `npm run generate:api` (not edited by hand) | derived from the spec; +19 lines (6 + 13), all of them the six `500` entries and the `InternalError` response, type-level only |
| `frontend/e2e/real-backend.spec.ts` | header comment only | F-14-5: the startup instructions were stale |
| `docs/technical-debt.md` | new TD-041 and its origin line | F-14-2 and F-14-6 recorded as open debt, not as proved |
| `docs/lessons-learned.md` | new L30 | process lesson of F-14-1 |
| `docs/backend-standards.md` | one sentence | the `500` is documented and the types regenerated in the same change |
| `openspec/.../tasks.md` | group 14 title and wording of 14.1, ticked | see below |

The behaviour of FastAPI and the routes were not changed: the contract test compares the status codes only for the three document paths, which are unchanged (`test_api_contract.py`, 15 passed), and the responses added describe behaviour that already exists and is tested (`test_endpoint_commit_persistence.py`: the five handlers answer the standard 500 with nothing stored; `test_consent_persistence.py` for consent). The `500` is documented only for the six handlers that commit through `commit_or_rollback`, which is the authorised set; the other endpoints are listed under "Observations".

## HTTP 500 documented (six endpoints)

| Endpoint | Meaning of the 500 |
|---|---|
| `POST /auth/register` | the account was not stored |
| `POST /users/me/consent` | the consent was not stored (unchanged text, now shared) |
| `POST /subjects` | the subject was not stored |
| `DELETE /subjects/{subject_id}` | the subject was not deleted |
| `POST /subjects/{subject_id}/enrollments` | the enrollment was not stored |
| `DELETE /subjects/{subject_id}/enrollments/{student_id}` | the enrollment was not removed |

## Generated types

The difference of `api.generated.ts` against the committed file is six `500: components["responses"]["InternalError"];` lines plus the `InternalError` response (13 lines: its description and type), nothing else. A generation from the spec of `main` equals the previous committed file, so before this change the file was exactly current for `main`.

## Frontend quality gates (`group-14/frontend-steps-final.txt`, run after the last edit)

| Gate | Result |
|---|---|
| `npm run lint` | exit 0 |
| `npm run format:check` | exit 0 |
| `npm run typecheck` | exit 0 |
| `npm run check:api-types` | exit 0, "API types are up to date." |
| `npm run test:coverage` | exit 0, statements 97.68 %, branches 94.17 %, functions 100 %, lines 97.58 % |

Also: `openspec validate --all --strict` 18 of 18; `test_api_contract.py` 15 passed. No Python file was modified, so ruff and mypy were not repeated.

## Detection of stale types (`group-14/stale-types-detection.txt`)

A `507` response was deliberately added to `POST /auth/register` in the spec without regenerating the types: `check:api-types` failed (exit 1, "missing or out of date with docs/api-spec.yml"). The spec was restored from a copy byte for byte (the SHA-1 before and after is equal) and `check:api-types` passed again.

## Findings F-14-1 to F-14-6

| ID | Status |
|---|---|
| F-14-1 stale generated types | **corrected and proved**: spec and types agree, gates pass, drift is detected |
| F-14-2 browser scenarios not run (CORS preflight, real 429 with `Retry-After`, token expiry) | **registered, not run, not proved**: TD-041 |
| F-14-3 figures are local runs | informational; stated in the reports |
| F-14-4 undocumented 500 on five endpoints | **corrected**: documented |
| F-14-5 stale instructions of the real-backend suite | **corrected** (header comment only); the real stack still needs the authorised preparation of roles and credentials (tasks 3.3b, groups 16 and 17) |
| F-14-6 main-flow E2E required by `docs/base-standards.md` section 9.2 | **registered, not satisfied**: TD-041; belongs to the final delivery |

## Task 14.1

Ticked with a rewritten statement: the only frontend file changed by the change is the generated types file (plus a comment in the opt-in E2E spec), no component, logic or dependency changed, the steps of the CI job `frontend` are unchanged and pass locally except Playwright, and the mocked Playwright suite was not run in this group. The criteria that have evidence: frontend diff (`git diff main..HEAD -- frontend`), CI job comparison (applicability report), the five gates and the drift detection above. F-14-1 and its correction are traced in this report and in the applicability report.

## Limits

GitHub Actions has not run the workflow, so the frontend job is verified only through its steps run locally; the browser behaviour under the restricted roles is not verified (TD-041).

## Independent review (read-only, clean context): PASS WITH GAPS, no Critical, High or Medium finding

It confirmed the scope (seven modified files, all authorised; the e2e spec differs in comments only; no change to `package.json` or the lock file), that the operations with a `500` in the spec are exactly the six handlers that call `commit_or_rollback`, that the committed types equal a fresh generation and differ from HEAD by the six entries and the `InternalError` block only, that the evidence supports each claim, and that nothing else reads the added responses. Its observations:

- **Observation L-1 (Low, not fixed: outside the authorised set):** `DELETE /subjects/{subject_id}/documents/{document_id}` commits explicitly with a bare `db.commit()` (`documents.py:243`), so a refused commit also ends in the generic `500 INTERNAL_ERROR`, and the contract does not list it. Nothing is stored or removed in that case, so only the documentation is missing. Candidate for the next contract edit.
- **Observation L-2 (Low, not fixed):** `DELETE /users/me` and the conversation and chat deletes rely on the `get_db` commit after the response, the exposure described by TD-039 for the five handlers fixed there; they are not in the scope of TD-039 as recorded.
- **L-3 (Low):** wording of the contract-test scope, clarified above.
- **Info:** the claims about `git diff main..HEAD -- frontend` and the CI job comparison come from the applicability report and were not re-verified by this review; the reviewer did not hash the seven reference documents (`git status` shows them unchanged and untracked).
