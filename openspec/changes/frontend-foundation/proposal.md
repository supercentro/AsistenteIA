# Proposal

## Why

The backend already exposes authentication, roles, subjects and enrollments (changes 1 to 3), but the frontend is only a static landing page: nobody can register, sign in or see their subjects. Every later screen (teacher material, student chat, history, erasure) needs a signed-in session, role-aware navigation, one HTTP/error layer and shared loading/error/empty states. This change builds that base (change 4 of 13).

**Scope origin.** The approved 13-change plan names this change `frontend-foundation` but no preexisting specification or ticket describes its scope. The scope below is defined by the project owner's decisions D1 to D9 of the planning session, not by an earlier document. It is recorded here so later changes do not assume more or less than this.

## What Changes

- **Authentication screens**: login for every user and registration for students (`POST /auth/register`, `POST /auth/login`). A successful registration redirects to the login screen with a notice; there is no automatic sign-in.
- **Session in memory only**: the access token lives in one module-level store, never in `localStorage`, `sessionStorage`, cookies or the URL. Reloading the page requires signing in again. The session ends automatically when the token expires (`expires_in`) and when the API answers 401 on a protected request.
- **User and role from the backend**: after login the app calls `GET /users/me`; the role shown in the UI always comes from that response, never from the token. The backend remains the authority on permissions. Consent fields returned by `/users/me` are kept in the session data and not interpreted.
- **Role-aware routing and shell**: protected routes (`RequireAuth`, `RequireRole`), a layout with navigation per role, sign-out, a "not allowed" view and the existing not-found view.
- **HTTP layer**: Axios client with an interceptor that adds the token, one error model (`ApiError`) with Spanish messages chosen by error `code` (server messages are never shown), `Retry-After` handling for 429, and React Query retries disabled for 4xx.
- **Reusable UI states**: loading, error (with retry) and empty-state components, plus the form field, button and alert primitives the forms need.
- **Read-only subject list** (`GET /subjects`) for both roles, to prove the integration with the change 3 backend. No create, delete, enrollment or detail screens.
- **Contract types**: TypeScript types generated from `docs/api-spec.yml` with `openapi-typescript`, committed, with a check that fails when the generated file and the spec drift apart.
- **Forms**: React Hook Form with Zod schemas that mirror the API limits without being stricter or looser than the contract.
- **Quality tooling**: Vitest coverage with the existing thresholds (70 % on components and hooks), `vitest-axe` accessibility checks if compatible (decided during implementation, with a documented fallback), a mocked Playwright suite run in CI, and a mandatory verification against the real backend (authentication, CORS, `Authorization`, 401 and token expiry) made by the agent and repeatable through a gated Playwright spec.
- **Docs**: `docs/frontend-standards.md`, `docs/development_guide.md`, `docs/technical-debt.md` (TD-019 recording separately the loss of the session on reload and the XSS exposure of an in-memory token, and TD-020) and, only where the comparison with the generated OpenAPI of the backend proves it, `docs/api-spec.yml` (required fields of the response schemas; behaviour-neutral).
- **Process controls from `docs/lessons-learned.md`**: TDD evidence per group, independent adversarial review (mandatory, session handling is security sensitive), explicit `update-docs`, contract reconciliation, AI-usage notes for a later `prompts.md` proposal.

### Out of scope (not added)

Subject creation, deletion or detail pages and enrollment management (change 7, decision D1); documents and uploads (6, 7); chat, conversations and sources (8 to 10); consent screens, the privacy page and any consent enforcement (decision D8, change 10); account and data erasure (11); refresh tokens, "remember me", logout-everywhere or password change (TD-006, outside the MVP); social login; teacher registration in the UI (teachers are created by the CLI); i18n beyond the single Spanish constants module; dark mode; backend changes of any kind.

**BREAKING**: none. The landing page at `/` stops being public: anonymous users are redirected to `/login`.

## Capabilities

### New Capabilities
- `frontend-session-auth`: registration and login screens, the in-memory session, token expiry and 401 handling, role and user loading from `/users/me`, and protected, role-aware routes.
- `frontend-api-client`: the shared HTTP client behaviour: token injection, error classification and Spanish messages by code, rate-limit and outage handling, retry policy, no sensitive data in logs or messages, and consistency between the generated types and `docs/api-spec.yml`.
- `frontend-app-shell`: the authenticated layout and role navigation, the shared loading/error/empty states, the read-only subject list, centralised Spanish copy, accessibility and responsive behaviour.

### Modified Capabilities
- `continuous-integration`: the frontend job also checks the generated API types, enforces the coverage thresholds and runs the mocked Playwright suite (added requirement; existing requirements unchanged).

## Impact

- **Authorization / isolation**: no new server rule. The UI hides screens by role but is not an authority; wrong-role navigation shows a "not allowed" view, and every API call stays enforced by the backend. The React Query cache is keyed by user and cleared on sign-out so a second user on the same tab never sees cached data of the first.
- **Personal data (GDPR)**: the token and the profile exist only in memory; nothing is written to browser storage; tokens, passwords and emails are never logged or placed in error messages or URLs.
- **External services**: none (Gemini is not touched). Tests mock the API; the real backend is only used in the agent-run and gated verification.
- **Contracts**: `docs/api-spec.yml` is read, not redefined. A behaviour-neutral correction (declaring fields as required) is made only for fields that the comparison with the generated OpenAPI of the backend and its tests confirm are always returned. If a real incompatibility would require changing the approved contract or the backend behaviour, the work stops and the owner decides; the backend is never modified by this change.
- **Code**: `frontend/src/{pages,components,hooks,services,lib,types,tests}`, `frontend/e2e`, `frontend/package.json` and `package-lock.json` (new dependencies: React Hook Form, Zod, its resolver, `openapi-typescript`, `@vitest/coverage-v8`, optionally `vitest-axe`), `frontend/vite.config.ts` (coverage), `.github/workflows` (frontend job). The frontend image must be rebuilt after the dependency change (see `docs/lessons-learned.md` L15).
- **Existing tests**: the landing-page test in `App.test.tsx` and the smoke spec in `frontend/e2e` change because `/` becomes protected; their intent (the app boots, unknown routes show the not-found page) is preserved.
- **Integration adjustment approved during review (TD-021)**: the backend CORS configuration also exposes `Retry-After` (`expose_headers=["Retry-After"]` in `backend/app/main.py`), because without it a browser cannot read the wait time of a 429. It is the only backend line touched; origins, methods, credentials and allowed headers are unchanged, and it is tested in `backend/tests/integration/test_cors_retry_after.py`.
- **Dependencies on later changes**: none required. Changes 7 and 10 add their role-exclusive routes on top of `RequireRole` and the shell.
