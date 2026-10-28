# Independent Adversarial Review - frontend-foundation

- Date: 2026-10-28
- Reviewer: a separate Claude subagent (general-purpose, `model=opus`) with a clean context, no access to the implementing conversation, read-only on the repository (probes ran on a copy outside the working tree; no backend, no compose stack, no development database touched). This report summarises its final report; the resolution column is written by the implementing session.
- Scope: `git diff origin/main..HEAD` of `feature/frontend-foundation` at `6f50382` (frontend, CI workflow, docs, OpenSpec change).
- Verdict of the reviewer: **PASS WITH GAPS**, no blocker and no major.

## What the reviewer tried (summary)
Token exposure (storage, URL, cookies, logs, DOM, hooks); session lifecycle (timer clamp and re-arm, clock sleep, repeated starts, concurrent 401s, an in-flight request of user A resolving after sign-out and user B signing in with the same id); return-target tricks (`//`, schemes, backslashes, encoded and Unicode slashes); interceptor edge cases (undefined base URL, other origins, anonymous requests, the `public` flag); role confusion; Zod limits against Pydantic (code points, emoji, NUL, bidi, BOM); XSS sinks; the `required[]` edits of `docs/api-spec.yml` against the backend schemas; the CI workflow; vacuous tests; owner constraints (no browser storage, backend untouched, no `prompts.md`/`readme.md` edits, no change to original OpenSpec/SpecBoot components). Gates re-run by the reviewer: lint, typecheck, `check:api-types`, Prettier, `npm audit`, 210 tests, mocked E2E (11 passed, 5 skipped), build.

## Findings and resolution
| # | Severity | Finding | Resolution |
|---|---|---|---|
| 1 | Minor | A late 401 to a request sent with an earlier session's token ended the current session of a different user | **Fixed** (test first, mutation-verified): the response handler ends the session only when the request's bearer equals the current token; tests `a late 401 for an earlier session` (3) |
| 2 | Minor | Session-auth scenarios "Too many attempts/registrations" promised seconds that a browser cannot read (TD-021) | **Fixed** in the spec: seconds when `Retry-After` is readable, generic message otherwise (new scenario); owner decision on `expose_headers` still requested |
| 3 | Minor | `LoginRequest` was a hand-written type | **Fixed**: derived from `paths['/auth/login']['post']['requestBody']` of the generated types |
| 4 | Minor | No test for "Keyboard use" | **Fixed**: `reviewFixes.test.tsx` signs in, signs out and registers with `Tab`/`Enter` only and asserts the focus order |
| 5 | Minor | Untested: `/users/me` 401 during login, status-class fallbacks (403/404/409/422/...), the `loading-profile` branch of `RequireAuth` | **Fixed**: added tests (these passed on first run because the behaviour already existed; characterisation tests) |
| 6 | Minor | The auth-route filter of the return target was case-sensitive and did not resolve dot segments or percent-encoding (`/LOGIN`, `/subjects/../login`, `/%6cogin`) | **Fixed** (test first): the path is resolved with `URL`, percent-decoded and lowercased before the check; new scenario wording in the spec |
| Q1 | Question | The token goes to any path of the API origin, not only below the base URL | **Accepted** and made explicit in the spec ("origin of the API base URL"); one backend origin |
| Q2 | Question | A backward clock jump lengthens the local session; the profile is not refreshed mid-session | **Accepted**: the server remains the authority (401 ends the session); noted here, no new debt row |
| Q3 | Question | After sign-out the next user was sent back to the previous user's last path | **Fixed** (test first): no `from` is recorded when the session ended by deliberate sign-out; new scenario in the spec |

## Verified as sound (by the reviewer)
No `localStorage`/`sessionStorage`/`document.cookie`/IndexedDB/`innerHTML`/`dangerouslySetInnerHTML` in `src`; the only `console.*` call logs method, path and status; the token is never in the URL; `useSession` exposes no token; `ApiError` keeps no server `message`/`details` and validates the code; the timer is clamped and re-armed and the request interceptor checks the clock; `startSession` replaces the timer; simultaneous 401s end the session once; a 401 from `/users/me` during login leaves one generic alert and no session; the in-flight cache cannot leak across users; the return target comes only from router state; other-origin and protocol-relative requests get no token; the role comes only from `/users/me`; Zod length counting matches Pydantic for non-BMP characters; the `required[]` additions match the backend; CI uses no secrets and the E2E step needs no backend; changes outside `frontend/` and the change folder are limited to `ci.yml` and five docs; backend, `readme.md`, `prompts.md` and the original OpenSpec/SpecBoot components are untouched.

## Verification after the fixes
Full suite 236 tests passed (210 + 26 in two new files), lint, Prettier, `tsc`, `check:api-types` clean, mocked E2E 11 passed, coverage thresholds pass. The failing run of the new tests before the fixes is recorded in `2026-10-28-tdd-evidence.md`.

## Final verdict
**PASS WITH GAPS**, all gaps resolved or accepted above. No open blocker or major. Open items for the owner: the `Retry-After` exposure decision (TD-021).
