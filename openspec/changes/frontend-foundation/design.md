# Design

## Context

State after change 3: the backend serves `POST /auth/register`, `POST /auth/login` (token response `access_token`, `token_type`, `expires_in`), `GET /users/me`, `POST /users/me/consent`, and the subject and enrollment endpoints. Errors use `{code, message, details}`; 422 carries `details.errors`; 429 carries `Retry-After`. The JWT does not carry an authoritative role (the backend rereads it per request). There is no refresh endpoint (TD-006) and CORS allows `http://localhost:5173`.

The frontend (`frontend/`) is the change 1 scaffold: Vite, React 18, React Router 7, TanStack Query, Axios, Tailwind 4, Vitest, React Testing Library, MSW and Playwright, with `lib/apiClient.ts`, `lib/queryClient.ts`, `lib/strings.es.ts`, empty `components/`, `hooks/`, `services/`, `types/` folders and two pages. The CI frontend job runs lint, format, typecheck, unit tests, build and `npm audit` (non-blocking) but not Playwright. The standards are in `docs/frontend-standards.md`; this design references them instead of repeating them.

The scope of this change comes from the owner's decisions (D1 to D9 of the planning session), not from an earlier specification; "decision N" below is this document's numbering and the owner's number is given in brackets.

## Goals / Non-Goals

**Goals:**
- A signed-in session that is correct, in memory only, and ends cleanly (expiry, 401, sign-out) without loops or leaks between users.
- One HTTP layer and one error model, with Spanish messages chosen by code.
- Role-aware routing and a shell on which changes 7 and 10 add screens.
- A contract-typed, tested, accessible base: TDD, coverage thresholds, accessibility scan, mocked E2E in CI and checks against the real backend.

**Non-Goals:**
- Subject management, enrollments, documents, chat, consent screens or consent enforcement, erasure, refresh tokens, teacher registration, dark mode, extra locales, any backend change.

## Decisions

### Decision 1. Layering and file layout [owner: keep existing standards]
`pages` (route views) use `components` and `hooks`; `hooks` call `services`; only `services` and `lib/apiClient.ts` touch Axios (`docs/frontend-standards.md` sections 2 and 3).

```
lib/session.ts      token + profile store (module level, subscribable) - single source of truth
lib/apiClient.ts    Axios instance + request/response interceptors
lib/apiError.ts     ApiError, classification, code -> copy key
lib/queryClient.ts  QueryClient with the retry policy
lib/strings.es.ts   all Spanish copy (extended)
services/authService.ts, subjectService.ts
hooks/useSession.ts, useLogin.ts, useRegister.ts, useSubjects.ts
components/         AppShell, NavBar, RequireAuth, RequireRole, LoadingState, ErrorState,
                    EmptyState, Alert, Button, FormField, SubjectList
pages/              LoginPage, RegisterPage, SubjectsPage, ForbiddenPage, NotFoundPage
types/api.generated.ts   generated, committed, never edited by hand
tests/              MSW handlers typed with the generated types, render helpers
```
`PrivacyPage`, `ChatPage` and `TeacherSubjectPage` listed in the standards are not created here.

### Decision 2. One in-memory session store [owner D2]
`lib/session.ts` holds `{token, expiresAt, user}` in a module variable and exposes `getToken()`, `getUser()`, `subscribe()`, `startSession()`, `setUser()` and `endSession(reason)`. React reads it through `useSyncExternalStore` (`useSession`), and the Axios interceptor reads the token from the same store, so there is exactly one copy of the token. Nothing is written to `localStorage`, `sessionStorage`, cookies, IndexedDB or the URL; the module never logs. Reload loses the store by construction and the router sends the user to `/login`.

Alternatives rejected: React context holding the token (the interceptor could not read it without a second copy); `sessionStorage` (contradicts the owner's decision and widens the XSS exposure; the trade-off is registered as TD-019 together with the lost-on-reload behaviour).

Expiry: `startSession` records `expiresAt = now + expires_in` and arms one timer (`setTimeout`, clamped to 2^31-1 ms) that calls `endSession('expired')`. The request interceptor also compares `Date.now()` with `expiresAt` before each request, because timers are throttled or paused while a computer sleeps; an expired session is ended and the request is rejected locally without sending the token.

### Decision 3. Login flow and role from the profile [owner D3]
`useLogin` calls `POST /auth/login`, stores the token with `startSession`, then calls `GET /users/me`. Only when that succeeds does `setUser` run and the app navigate. If `/users/me` fails, `endSession('login-failed')` discards the token and the form shows a generic error. The UI never decodes the JWT. Consent fields stay inside the stored profile object (typed from the contract) and no component reads them (owner D8).

### Decision 4. 401 handling without loops [owner D4]
The response interceptor treats a 401 as session loss only when the request is a protected one (not login/register, identified by an explicit marker on the request config, not by URL guessing) and a session exists. It calls `endSession('unauthorized')`, which is idempotent (a second call with no session does nothing), clears the query cache and sets a one-shot notice. Navigation is declarative: `RequireAuth` renders `<Navigate to="/login" state={{from}} />` when the store says anonymous, so concurrent 401s cause one transition and no imperative `navigate` is needed in the interceptor. Login and register 401/409/422/429 are returned to the forms as `ApiError`.

### Decision 5. Registration [owner D5]
`RegisterPage` sends only `{name, email, password}`; on 201 it navigates to `/login` with router state `{registered: true}` so the login page shows a notice. 409 is shown as "email already registered" (approved contract, TD-008). No automatic login.

### Decision 6. Generated contract types [owner D6]
`openapi-typescript` (dev dependency, version pinned by the lock file) generates `src/types/api.generated.ts` from `../docs/api-spec.yml`. Scripts: `generate:api` writes the file; `check:api-types` regenerates to a temporary path and fails if it differs from the committed file (used in CI and in the final gate). The committed file is required because the frontend image and the Vite container do not contain `docs/`. Services, hooks, fixtures and MSW handlers import payload types from it; no handwritten duplicates.

Known gap to verify at implementation: response schemas in `docs/api-spec.yml` do not declare `required` for `User` (and possibly others), so generated fields are optional. The task compares `docs/api-spec.yml` with the OpenAPI generated by the real backend (`create_app(...).openapi()`) and with the observed responses. A field is declared `required` only when that evidence confirms it is always returned; the backend behaviour is not touched. If the comparison finds a real incompatibility that would force a change of the approved contract, implementation stops and the owner decides. Every correction and every unchanged divergence is listed in the contract reconciliation report. The alternative (narrowing in code) is rejected because it hides the contract defect.

### Decision 7. Errors and Spanish copy [owner: uniform error handling]
`ApiError {status, code?, retryAfterSeconds?}` is built from the Axios error; the server `message` and `details` are never stored in it. `strings.es.ts` has `errors.byCode` and `errors.byStatusClass`; unknown codes fall back by status (401, 403, 404, 409, 422, 429, 5xx, network). `Retry-After` is accepted only as an integer between 1 and 3600; anything else produces the message without a number. The Axios client has a request timeout (15 s). Diagnostics log method, path without query and status only. A lint-level test enforces that no component file contains a user-visible Spanish literal (the check scans JSX text and common attributes; the copy module is exempt).

### Decision 8. Query client policy [owner: no retries on 4xx]
`retry` is a function: never for `ApiError` with a 4xx status, at most once for network errors and 5xx. `refetchOnWindowFocus` stays off. Query keys include the user id (`['subjects', userId]`) and `endSession` calls `queryClient.clear()`, so a second user never reads the first user's cache.

### Decision 9. Routing and role guards
```
/login        public  (redirects home when signed in)
/register     public  (redirects home when signed in)
/             RequireAuth -> redirects to /subjects
/subjects     RequireAuth + RequireRole(student|teacher)   SubjectsPage (read-only)
/forbidden    rendered in place by RequireRole (no URL change needed)
*             NotFoundPage
```
`RequireRole` receives the allowed roles; with a wrong role it renders `ForbiddenPage` and does not mount children, so their queries never run. The only production route today allows both roles, so the guard is exercised by tests with a role-exclusive test route; the first role-exclusive production routes arrive in changes 7 (teacher) and 10 (student). The post-login return target comes from router state only, never from the query string, and is accepted only if it starts with a single `/`, does not start with `//`, contains no scheme and is not `/login` or `/register`. Pages are loaded with `React.lazy` per area (auth screens, authenticated area).

### Decision 10. Forms [owner: React Hook Form and Zod]
React Hook Form with Zod schemas through the Zod resolver. The schemas mirror the contract: login `email` 1 to 255 ASCII, `password` 1 to 128 (never 10, which would reveal the registration rule and lock out existing users); register `name` 1 to 100 after trimming, `email` as above, `password` 10 to 128. Client validation never promises more than the server (TD-018: the server also trims Unicode whitespace) and the server stays the authority (a 422 is still handled). Failed submits focus the first invalid field (`shouldFocusError`), errors are linked with `aria-describedby`/`aria-invalid` and announced with `role="alert"`. The submit control is disabled while the mutation is pending.

### Decision 11. Shared UI components
`LoadingState` (`role="status"`, polite), `ErrorState` (`role="alert"`, retry button), `EmptyState`, `Alert` (info/success/error with the right role), `Button`, `FormField` (label, input, hint, error wiring). Tailwind utility classes only, mobile first (320 px minimum), long text wraps (`break-words`), descriptions preserve line breaks (`whitespace-pre-line`) and are rendered as React text, never as HTML.

### Decision 12. Test strategy [owner D7]
Pyramid, every group test-first with the failing run recorded in `reports/` (L01):
- **Unit**: `session` (expiry timer with fake timers, idempotent end, no storage writes), `apiError` classification, query retry policy, return-target validation, copy-literal scan.
- **Component** (Vitest, RTL, MSW; queries by role and label): login, register, guards, shell, subject list states, forms accessibility and focus, double submit, 401 mid-session, concurrent 401s, sign-out clearing cache, second user isolation. MSW handlers and fixtures are typed with the generated types.
- **Accessibility**: `vitest-axe` is evaluated first (compatibility with Vitest 5 and jsdom 30 is unverified); if it cannot be used, the fallback is `axe-core` called from a small test helper, and the decision is recorded in the report. Not silently skipped.
- **Coverage**: `@vitest/coverage-v8` with thresholds of 70 % lines/statements/functions/branches on `src/components` and `src/hooks`, as in the standards, enforced by `npm run test:coverage` in CI.
- **Mocked E2E (CI)**: Playwright Test with `page.route` stubs typed by the generated types: register then login, student and teacher login with their lists, invalid credentials, rate limit, reload returns to login, 401 mid-session, wrong-role view, mobile viewport. No backend, no database.
- **Real backend (mandatory, not in CI)**: the mocked suite is never enough on its own. (a) The agent drives the Docker Compose stack with Playwright MCP and `curl` and reports under `reports/`: authentication (register 201/409/422, login 200/401/429 with `Retry-After`, `GET /users/me`), CORS (preflight with an allowed and a disallowed `Origin`, requested headers `authorization,content-type`), the `Authorization` header accepted on protected endpoints and absent on login/register, a real 401 with an invalid, tampered or expired token, and the expiry flow. (b) Expiry is verified with a real short-lived token: the backend runs with `JWT_EXPIRE_MINUTES=1` (the minimum), the UI signs out when the announced lifetime elapses and a request made with that token after the lifetime is answered with 401 by the server. A real mid-session 401 is also provoked by restarting the backend with a different `JWT_SECRET`. These overrides are temporary (environment on the command line or an untracked override), never committed, and the original configuration is restored and verified afterwards. (c) A Playwright spec gated by `E2E_REAL_BACKEND=1` (skipped otherwise) repeats the register, login, list, sign-out and reload-returns-to-login flow against the running stack; a second gate (`E2E_SHORT_TOKEN=1`) enables the expiry case when the backend runs with the short lifetime. Credentials come from environment variables, never committed. The register rate limit (5 per minute) is respected by spacing the cases.
- **Existing tests**: `App.test.tsx` and `e2e/smoke.spec.ts` are updated (the landing page becomes the login redirect) keeping their intent.

### Decision 13. CI and tooling
Frontend job gains `npm run check:api-types`, `npm run test:coverage` (replacing `npm test` there) and a Playwright step (`npx playwright install --with-deps chromium`, then `npm run test:e2e`) using the mocked suite. `npm audit` stays non-blocking. New dependencies are exact-locked by `package-lock.json`; ESLint stays on major 9 (TD-015) so any new plugin must be compatible. The frontend Docker image must be rebuilt after the dependency change and the development guide says so (L15).

### Decision 14. Documentation and debt
`docs/frontend-standards.md` is updated for the register page, the session module, error mapping, generated types and the test strategy; `docs/development_guide.md` for the new scripts and the rebuild note; `docs/technical-debt.md` gains TD-019, one item with two separately described parts: (a) **loss of the session on reload or tab close**, a usability limitation caused by the absence of a refresh endpoint (TD-006) and by the decision to never persist the token; and (b) **exposure to XSS**, because an in-memory token is readable by any script running in the page (mitigated by text-only rendering, no `dangerouslySetInnerHTML`, the independent review and the content security policy planned for change 13, and not by persistence, which would be worse). Each part has its own risk, mitigation and owner; both are accepted by the owner. It also gains TD-020 (mocked E2E can drift from the backend; mitigated by generated types, the gated real-backend spec and change 12). `docs/lessons-learned.md` only if the review or the process produces a new lesson. `readme.md` and `prompts.md` are not touched without approval.

## Risks / Trade-offs

- **Reload logs the user out** (no refresh endpoint): accepted by the owner; the login notice says what happened. Registered in TD-019 part (a), separate from the XSS exposure of part (b).
- **Token readable by page scripts**: mitigated by never rendering HTML from data, no `dangerouslySetInnerHTML`, text-only rendering and the independent review; a content security policy belongs to the deployment change (13).
- **Mocks can lie** (L03, L06): generated types, a gated real-backend spec and the agent-run verification against Compose; the full real flow is change 12.
- **`openapi-typescript` on `api-spec.yml`** may reject or loosely type parts of the spec (nullable, `allOf`); mitigated by running it as the first implementation task and fixing the contract, not the generated file, when the spec is wrong.
- **`vitest-axe` compatibility** with the current Vitest/jsdom is unknown: fallback defined in Decision 12.
- **Zod/resolver version pairing**: the resolver must match the installed Zod major; the first task pins and verifies it.
- **Docker image staleness**: dependency changes require a rebuild (L15); documented.
- **Only one production route is role-neutral**, so the guard is tested synthetically until changes 7 and 10 use it.
- **Open questions**: none that block the plan; two assumptions are recorded: (a) the default home is `/subjects` for both roles, and (b) the Spanish copy uses neutral, impersonal wording that avoids regional forms of address. Both can change in review without affecting the specs.
