# Scenario Coverage - frontend-foundation

Map of every scenario of the delta specs to the automated check that covers it (Vitest = `npm run test:coverage`, E2E = mocked Playwright suite, REAL = real-backend report or gated spec).

## frontend-session-auth
| Requirement / scenario | Automated check |
|---|---|
| Sign in: student, teacher | `LoginPage.test.tsx` signing in (student, teacher); E2E "registers a student", "a teacher signs in"; REAL spec |
| Sign in: wrong credentials | `LoginPage.test.tsx` "one message for wrong credentials"; E2E; REAL spec |
| Sign in: profile load failure | `LoginPage.test.tsx` "discards the token when the profile cannot be loaded", "no session notice left behind", "invalid token lifetime" |
| Sign in: required fields validated | `LoginPage.test.tsx` validation block (empty, 255, non-ASCII, 128, 100 KB) |
| Sign in: no double submit | `LoginPage.test.tsx` "one request when submitted twice" |
| Sign in: too many attempts, server unavailable | `LoginPage.test.tsx` 429 with and without `Retry-After`, 503 retry, network failure; E2E rate limit; browser run (step 12) |
| Register: success, 409, 422, limits, no role, 429 | `RegisterPage.test.tsx` (registering and validation blocks, "never sends a role"); E2E register |
| Session only in memory: nothing persisted, reload, sign-out, second user | `session.test.ts` "where the session is stored"; global storage/cookie guard in `tests/setup.ts` (fails any test that writes); `SubjectsPage.test.tsx` sign-out and second user; E2E reload test (storage empty); step 12 browser inspection |
| Expiry: automatic, expired token not sent, no residue | `session.test.ts` expiry and "no residue"; `apiClient.test.ts` "ends an expired session before sending"; REAL spec with `JWT_EXPIRE_MINUTES=1` and step 11 curl |
| 401 ends the session once; concurrent; login 401 is a form error | `apiClient.test.ts` 401 block; `App.test.tsx` "ends the session once ... 401"; E2E 401 mid-session; REAL spec (tampered header) |
| Role from the profile; token claims ignored | `App.test.tsx` "takes the role from the profile and ignores the claims inside the token"; `session.ts` never decodes the token |
| Protected routes: anonymous, return target, unsafe target, wrong role, signed-in user on auth screens | `App.test.tsx` routing and `RequireAuth and RequireRole` blocks; `returnTarget.test.ts` |
| Sensitive data never in logs, messages or URLs | `LoginPage.test.tsx` "sensitive data" block; `RegisterPage.test.tsx` console check; `session.test.ts` logging; `apiClient.test.ts` diagnostics; step 12 console review |

## frontend-api-client
| Requirement / scenario | Automated check |
|---|---|
| Token only to the API and only where needed | `apiClient.test.ts` token injection block; `services.test.ts`; E2E "token to protected endpoints only" |
| Error classification and Spanish messages by code | `apiError.test.ts` (known, unknown, non-JSON, markup, status fallbacks, server text never kept); component tests assert the visible Spanish text |
| Rate limit with `Retry-After` | `apiError.test.ts` `parseRetryAfter`; `LoginPage.test.tsx`; **limit**: not readable across origins (step 11 finding 1) |
| Network failure or timeout | `apiError.test.ts`; `apiClient.test.ts` network and timeout configuration; `LoginPage.test.tsx` network |
| Retry policy | `queryClient.test.tsx` (4xx once, 503 recovers in two, persistent 503 in two) |
| Cache isolated per user | `queryClient.test.tsx` cache clearing; `SubjectsPage.test.tsx` key per user and second user |
| Types from the contract: up to date, stale, mocks typed | `npm run check:api-types` (failing run in the TDD evidence, CI step); `tests/api.ts` and `e2e/support/mockApi.ts` use the generated types |
| Verified against the real backend | `reports/...step-11-curl-verification.md`, `...step-12-e2e-verification.md`, `e2e/real-backend.spec.ts` |
| Diagnostics limited to method, path, status | `apiClient.test.ts` "logs at most method, path and status"; step 12 console review |

## frontend-app-shell
| Requirement / scenario | Automated check |
|---|---|
| Layout and role navigation; unknown routes | `SubjectsPage.test.tsx` "Application shell"; `App.test.tsx` not-found for anonymous and signed-in |
| Read-only subject list (shown, student, teacher, text not markup, no controls) | `SubjectsPage.test.tsx` content block; E2E; step 12 (real data with `<b>` in the name) |
| Loading, empty, failure and retry, 401 while loading | `SubjectsPage.test.tsx` states block; `shared.test.tsx` |
| All copy from one module | `tests/copy.test.ts` (detector and scan of `pages/` and `components/`) |
| Accessible forms and screens | `shared.test.tsx` and page tests: labels, `aria-describedby`, `aria-invalid`, focus on the first invalid field, one level-one heading, `vitest-axe` scans (login, register, subject list, not-found, shared components) |
| Responsive from 320 px | E2E "narrow viewport" (it found and fixed a real overflow); step 12 at 320 px |
| Split by route | Production build lists separate chunks for login, register, subjects and not-found (`npm run build` output) |

## continuous-integration (delta)
| Scenario | Check |
|---|---|
| Types stale | CI step `npm run check:api-types` (stale run proven locally, see TDD evidence) |
| Coverage below threshold | `vite.config.ts` thresholds; proven failing at 100 % (TDD evidence) |
| Mocked browser flows | CI step `npm run test:e2e`; no backend or database in the job |

## Added after the independent review
| Scenario | Automated check |
|---|---|
| Too many attempts when the wait time is not readable | `LoginPage.test.tsx` "generic rate limit message when Retry-After is not trustworthy"; E2E "rate limit shows the generic message"; browser run (step 12) |
| No return to the previous user's page after sign-out | `reviewFixes.test.tsx` "does not carry the previous user page after a deliberate sign-out" and "keeps the page when the session ended by itself" |
| Return target resolving to the authentication screens (case, dot segments, encoding, trailing slash) | `reviewFixes.test.ts` (7 rejected forms, 3 accepted forms) |
| Late 401 for an earlier session | `reviewFixes.test.ts` "a late 401 for an earlier session" (mutation-verified) |
| Keyboard use | `reviewFixes.test.tsx` "keyboard use" (login, sign-out, registration) |
