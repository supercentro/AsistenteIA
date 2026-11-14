# Step 14: E2E applicability decision (2026-11-13)

Branch `feature/database-least-privilege`, code at `96b3897`. Scope: group 14 of `tasks.md`, whose only task is **14.1** "Record that no frontend change is made, and that the mocked Playwright suite in CI runs unchanged". No browser, API, frontend server or Docker service was started in this step, nothing was pushed, the new workflow has not run on GitHub Actions, and no functional code or frontend file was changed.

## Decision

- **Browser E2E tests: not required by this change.** They are **not executed** and none were run in this step; the flows they would cover are covered at HTTP level (below). This is justified by evidence, not by the absence of visual changes alone.
- **Task 14.1 stays unchecked.** Its statement is only half true: the frontend source has no change (0 files), but **the frontend job of CI would fail at its step "API types match docs/api-spec.yml", before it reaches the mocked Playwright suite**, because of a defect introduced by this branch (finding F-14-1). Marking 14.1 now would record something false. It can be marked once the finding is resolved (decision requested from the owner).

## The task, and what "no frontend change" is made of

| Check | Result |
|---|---|
| Frontend files changed against `main` | 0 (`git diff main..HEAD --name-only -- frontend`) |
| `ci.yml`, job `frontend` | the steps are identical to `main` (compared as parsed YAML); the branch only added `timeout-minutes: 30` and `persist-credentials: false` to the job (group 10 hardening) |
| Mocked Playwright suite (`frontend/e2e/auth-flow.mocked.spec.ts`, `smoke.spec.ts`, `support/mockApi.ts`) | unchanged; it stubs the API origin with `page.route`, starts no backend, so it cannot observe the database roles |
| Real-backend suite (`frontend/e2e/real-backend.spec.ts`) | exists, **opt-in** (`E2E_REAL_BACKEND=1`), needs the compose frontend on 5173 and the backend on 8000, is skipped in CI; unchanged |
| Cheap local steps of the frontend job (`group-14/frontend-steps-local.txt`) | `lint` passes, `format:check` passes, `typecheck` passes, `test:coverage` (Vitest) passes, **`check:api-types` fails** |

## Applicability analysis (the points the owner asked to weigh)

1. *No frontend change*: true, and not enough on its own; the question is whether the HTTP contract the frontend relies on changed.
2. *Identities and permissions changed*: invisible to a browser unless a permission is missing, which shows up as an HTTP error; every route was run under the restricted roles with persisted-state assertions (group 9: 15 operations, 484 existing tests under the roles) and by hand with curl (group 13: 101 checks).
3. *Migration 0006*: the default of `users.role`; registration answers the same (201, role `student`); tested up, down and round trip, and through the API.
4. *Registration and teacher provisioning*: registration is unchanged for the client; teachers no longer come from any endpoint (there never was one) but from the CLI role; a payload asking for `teacher` still yields a student (group 13).
5. *Existing coverage*: the authentication flows of `real-backend.spec.ts` have equivalents with the restricted roles (the CORS preflight, the real 429 with `Retry-After` and the short-token expiry of that file have none in groups 9 or 13, see F-14-2): register and duplicate (`test_auth_register`, group 13), login and wrong credentials (`test_auth_login`, group 13), `GET /users/me` and a tampered token (`test_users_me`, group 13), a new student seeing an empty subject list (`test_subjects_api::test_list_is_an_empty_array_without_subjects`, run in the roles mode), logout (client side, no API). Contract change visible to a client: a write that the database refuses at commit now answers `500 INTERNAL_ERROR` instead of a 2xx, for the consent endpoint (documented in `docs/api-spec.yml`) and for registration, subjects and enrollments (not documented, see F-14-4); it is reachable only when the database refuses the write. The figures of groups 9 and 13 (484 tests under the roles, 101 curl checks) come from local runs on disposable clusters, not from GitHub Actions.

What is **not** proved by these: the behaviour of the real React application in a browser against a backend that runs under the restricted roles (rendering, local storage, redirects). The risk is low because no request or response shape changed.

## Finding F-14-1 (blocks ticking 14.1): the generated API types are stale

- `npm run check:api-types` fails: `src/types/api.generated.ts is missing or out of date with docs/api-spec.yml`. It is a required step of the CI job `frontend` (before unit tests, build and Playwright).
- Cause, verified: commit `4d6bfc3` (group 7, task 7.2) added the `500` response of the consent endpoint to `docs/api-spec.yml`. A fresh generation from the branch spec differs from the committed file by exactly one block (the `500` entry, 12 lines, type-level only); a fresh generation from the spec of `main` equals the committed file, so the defect is introduced by this branch and not pre-existing.
- Why it was missed: the backend gates (ruff, mypy, tests, privilege gate) do not run the frontend check, and the review of group 7 did not include it.
- Impact: the frontend job fails on the first run on GitHub, and the mocked Playwright suite never runs in that job.
- Options (none applied; the owner's instruction for this step is not to change functional code, and the fix touches a frontend file):
  - **A (recommended)**: run `npm run generate:api` and commit `frontend/src/types/api.generated.ts` (a generated, type-only file, +12 lines, no runtime effect). Then `check:api-types` passes, and 14.1 is rewritten to say "the only frontend file changed is the generated types file, because of the documented consent 500".
  - B: remove the `500` from `docs/api-spec.yml`. That contradicts the approved consent requirement and DD-10, and the other endpoints' behaviour is then undocumented. Not recommended.
- Process lesson to record in `docs/lessons-learned.md` when authorised: whenever `docs/api-spec.yml` changes, run `npm run check:api-types` (and the generation) in the same change.

## Further findings of the independent review (read-only, PASS WITH GAPS; the decision and F-14-1 were confirmed)

- **F-14-2 (Medium): the scenarios of `real-backend.spec.ts` are more than the report first listed.** It also contains the browser-visible CORS preflight (`access-control-allow-origin`), a real `429` with `Retry-After` exposed through CORS and, with `E2E_SHORT_TOKEN=1`, the token expiry. None of these was exercised in groups 9 or 13 (curl does not do a CORS preflight). The branch did not change the CORS or rate-limit code, so the risk is low, but that part of the browser path is unverified.
- **F-14-3 (Low): origin of the figures.** Stated above: local runs, not GitHub Actions.
- **F-14-4 (Low): a spec gap, not only the consent endpoint.** `commit_or_rollback` runs before the response in `POST /auth/register`, `POST` and `DELETE /subjects`, and the enrollment `POST` and `DELETE`, so a refused write is a `500` for them too, while `docs/api-spec.yml` documents a `500` only for consent. The generated types cannot flag it because the spec is silent. If the owner authorises the regeneration of the types (option A of F-14-1), the same change can document the `500` for these endpoints in the spec first so the types are regenerated once.
- **F-14-5 (Low): the startup instructions in the header of `real-backend.spec.ts` are stale.** They say "docker compose: frontend 5173, backend 8000"; with this branch `backend` and `worker` wait for `bootstrap` and `migrate`, so a plain `docker compose up` needs the role files, which the real stack does not have yet (task 3.3b). A run of that suite needs the disposable stack described below.
- **F-14-6 (Medium, to be tracked): `docs/base-standards.md` section 9.2 requires a committed Playwright E2E of the main flow (teacher uploads, student asks, answer with citation) before final delivery.** `real-backend.spec.ts` covers authentication and the empty subject list only, is skipped in CI, and the chat flow does not exist yet. That requirement belongs to the final delivery and not to this change; it is stated here so it stays visible, and it is a candidate for `docs/technical-debt.md` (not edited in this step).
- Other steps of the frontend job (`build`, `playwright install`, the mocked e2e) depend only on frontend files and npm, which are unchanged; the non-blocking `npm audit` was not evaluated. Because F-14-1 showed that a "nothing changed" claim can be wrong, the browser-level rehearsal in group 16 is worth keeping.

## If an E2E run is wanted (not mandatory, not run)

| Item | Detail |
|---|---|
| Scenario | `E2E_REAL_BACKEND=1 npm run test:e2e -- real-backend`: register, sign in, empty subject list, reload, sign out, wrong credentials, tampered token (real 401), CORS preflight, real 429 with `Retry-After`; with `E2E_SHORT_TOKEN=1` (API with `JWT_EXPIRE_MINUTES=1`) the token expiry |
| Environment | a disposable stack like group 13 (`g13scratch`: scratch cluster with roles, API on a free loopback port) plus the Vite dev server on a free port, with `E2E_BASE_URL`, `E2E_API_URL`, `VITE_API_URL` pointing to them and the API `CORS_ORIGINS` set to the frontend origin; Chromium installed |
| Risks | starts a frontend server (not authorised in this step); the registration endpoint is rate limited to 5 per minute; the suite leaves `e2e-*@example.com` accounts (harmless in a scratch cluster that is destroyed) |
| Dependencies | the F-14-1 fix does not block it; Playwright browsers; the images of group 13 |
| Recommendation | optional; it fits the rehearsal of group 16 on a restored copy rather than a new standalone group; the value over group 13 is the browser layer only |

## State

Development database untouched (read-only verification after this step: revision 0005, worker healthy, tree clean). Evidence: `group-14/frontend-steps-local.txt`.
