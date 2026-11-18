# Step 4.4 Report - E2E verification

- Date: 2026-11-17
- Change: privacy-consent-ui
- Tools: Playwright MCP driven by the agent against the local stack (frontend `http://localhost:5173` from the Compose container with the bind-mounted source; backend `http://localhost:8000`, the only origin its CORS allows), plus the committed Playwright Test suite.

## Playwright MCP (interactive, real backend)

| Step | Observed |
|---|---|
| `/privacy` as an anonymous visitor | Page shows title (focused), version `2026-10-v1`, 7 sections including "Tratamiento por Gemini (Google)", "Cómo borrar las conversaciones" and the not-self-service list; 0 console errors; no API request |
| Viewport 320 x 700 | `scrollWidth` 305 for `innerWidth` 320: no horizontal scrolling |
| `/register` | Link "Política de privacidad" to `/privacy` present |
| Register a student, sign in | Redirected to `/consent`; the heading has focus; checkbox unticked; "Aceptar y continuar" disabled; `localStorage`, `sessionStorage` and cookies empty |
| Keyboard only | Tab: policy link; Tab: checkbox; Space ticks it; Tab: "Aceptar y continuar"; Enter accepts |
| After accepting | Navigated to `/subjects` ("Mis asignaturas"); the database shows `consent_version = 2026-10-v1` and an acceptance time for that student |
| Teacher signs in | Goes straight to `/subjects`, never to `/consent`; the database shows no consent for the teacher |

Note: the browser profile autofilled the login form with saved credentials that are not the test account's; they were overwritten before submitting and never used.

Not exercised in the browser: the 403 `CONSENT_REQUIRED` mid-session path (it needs the policy version to change while a session is open); it is covered by `consentApi.test.ts` and by the mutation check. A held student cannot type another address without reloading, and a reload ends the session by design (memory-only session), so that case is covered by the routing tests.

## Playwright Test (committed)

- `npx playwright test consent-flow auth-flow smoke`: **16 passed** (mocked API). New `e2e/consent-flow.mocked.spec.ts` has 5 tests: held student accepts and reaches the subjects (posted body checked), public policy at 320 px without overflow and without API requests, version rejected keeps the student held, sign-out from the consent screen, teacher and consented student are never held.
- `E2E_REAL_BACKEND=1 npx playwright test real-backend -g "register, sign in"`: **1 passed** against the real API; the spec now goes through the consent screen. The test creates one account (`e2e-<timestamp>@example.com`). The other real-backend cases were not run here (the last one exhausts the login rate limit of the address).
- Existing mocked fixtures: `student` now carries the current consent; `unconsentedStudent` was added.

## Outcome
Step 4.4 status: PASS.
