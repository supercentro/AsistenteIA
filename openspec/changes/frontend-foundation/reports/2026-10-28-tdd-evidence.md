# TDD Evidence - frontend-foundation

Rule: `docs/base-standards.md` section 9.2 (failing run recorded per functional group). Commands run from `frontend/`.

## Group 1 - tooling and contract types
- Command: `npm run check:api-types` before the generated file existed. Result: exit 1, `src/types/api.generated.ts is missing or out of date with docs/api-spec.yml`.
- After generating the file and then adding `required` to `User` and `Subject` in `docs/api-spec.yml` (without regenerating): the same command failed again (stale), then passed after `npm run generate:api`. This demonstrates both failure modes of the check.
- `vitest-axe` probe (a temporary test, removed): `axe(<input />)` reported violations and `axe(<label>Name <input /></label>)` reported none, `2 passed`, so the library detects what it must with Vitest 5 and jsdom 30. jsdom prints `Not implemented: getComputedStyle with pseudo-elements` noise; colour-contrast cannot be evaluated in jsdom and is disabled in the helper.

## Group 2 - session store
- Command: `npx vitest run src/lib/session.test.ts`. Result before the implementation: collection error `Failed to resolve import "./session"` (0 tests run).
- Command: `npx vitest run src/hooks` for `useSession`. Result before: collection error `Failed to resolve import "./useSession"`.
- After the implementation: 20 session tests and 2 hook tests pass.

## Group 3 - API client, errors and query policy
- `src/lib/apiError.test.ts`: collection error (`./apiError` did not exist). After: `40 passed`.
- `src/lib/apiClient.test.ts` and `src/lib/queryClient.test.tsx` against the scaffold client: `apiClient.test.ts 14 tests | 13 failed`, `queryClient.test.tsx 7 tests | 7 failed` (no interceptors, no `createQueryClient`, `shouldRetry`).
- First green attempt: 9 tests of `apiClient.test.ts` still failed because jsdom ran CORS preflights (`OPTIONS` without a mock handler). Fix: the test environment uses the API origin (`environmentOptions.jsdom.url`), documented as a test-only choice since CORS is verified against the real backend.
- `src/services/services.test.ts`: collection error (`./subjectService` missing). After: `5 passed`.
- Total after group 3: 82 tests in `src/lib`, `src/hooks`, `src/services`.

## Group 4 - copy module and shared UI
- `npx vitest run src/components src/tests/copy.test.ts` before the components existed: collection error `Failed to resolve import "./Button"` (shared.test.tsx, 0 tests). After: `15 passed`.
- Deviation: `src/tests/copy.test.ts` passed on its first run because the code base had no inline copy yet. Compensation (mutation check): a temporary `components/Tmp.tsx` containing `<p>Hola mundo</p>` made the test fail listing `Tmp.tsx: "Hola mundo"`; the file was removed and the test passes again. The detector itself has its own tests.

## Groups 5, 6 and 7 - login/registration, guards, shell and subject list
- The test files of the three groups (`LoginPage.test.tsx`, `RegisterPage.test.tsx`, `App.test.tsx`, `SubjectsPage.test.tsx`) were written together and run together before any of those pages, hooks or guards existed. Command: `npx vitest run src`. Result: `64 failed | 130 passed (194)` and `App.test.tsx` failing at collection (`RequireAuth` did not exist). The 130 passing tests were the earlier groups.
- Deviation from per-group red runs: one combined red run instead of three, because the pages depend on the route table. Compensated by the mutation run below.
- After the implementation: first run `7 failed | 203 passed`. Causes, all test-infrastructure: the location probe used `<output>` (implicit `status` role) and collided with the notice queries; `findByRole('status')` matched the Suspense fallback of the lazy routes. Fixed in the helper and by querying by text. Final: `210 passed (14 files)`.
- Mutation checks (`scratchpad/mutate_f4.py`, 20 temporary mutations of guards, run against the whole suite, sources restored and re-verified): **19 killed, 1 survived**. The survivor removes `!error.config?.public` from the 401 handler; it is an equivalent mutant because the next condition (`headers.has('Authorization')`) is already false for public requests, so the behaviour cannot differ. The killed mutations cover: expired token returned, expiry timer not cleared, token on public requests and on other origins, 401 not ending the session, 4xx retried, cache surviving the session, protocol-relative and login-route return targets, unvalidated server code, `Retry-After` bound, role guard, auth guard, unvalidated return target in the redirect, token kept after a failed profile load, cache key without user, role in the registration payload, description as HTML and the login password minimum.
- Threshold proof (task 1.4): with the component threshold temporarily set to 100 %, `npm run test:coverage` failed with `Coverage for lines (96.96%) does not meet "src/components/**" threshold (100%)`; the configuration was restored to 70 %.

## Group 8 - mocked browser tests
- Command: `npm run test:e2e` after writing `e2e/auth-flow.mocked.spec.ts` against the finished UI: `9 passed, 2 failed`. (The specs were written after the implementation of the UI; the failing run below is the first run and each failure was a real finding.)
  1. `narrow viewport`: the page scrolled horizontally at 320 px with a 140-character unbroken name. Cause: the list grid had no explicit single column, so the long word widened the track. Fix: `grid-cols-1` on the list. A regression check stays in the E2E suite.
  2. `rate limit`: the stubbed `Retry-After` was not readable by the browser. Cause (also present in the real backend): the CORS middleware does not set `expose_headers`, so a cross-origin page cannot read `Retry-After`. The frontend degrades to the generic rate-limit message by design. The spec was adjusted to mirror the real behaviour; the finding is reported to the owner (backend change outside this scope).
- After the fixes: `11 passed`; `real-backend.spec.ts` is skipped (5 skipped) unless `E2E_REAL_BACKEND=1`.

## Review follow-ups (task 14.2)
- Command: `npx vitest run src/lib/reviewFixes.test.ts src/reviewFixes.test.tsx` before the fixes: `9 failed, 17 passed`. Failing: late 401 ending another user's session (1), return targets resolving to the authentication screens (6), the previous user's page carried after sign-out (2). The 17 passing tests are characterisation tests for behaviour that already existed (keyboard flow, `/users/me` 401 during login, status-class fallbacks, `loading-profile` state).
- First version of the late-401 test sent the request after the second sign-in (the interceptor runs asynchronously), so it failed for the wrong reason; the test now waits until the request reached the server carrying user A's token. Mutation check: reverting the bearer comparison to a header-presence check makes it fail (`1 failed | 19 passed`); the fix restores `20 passed`.
- After the fixes: `236 passed (16 files)`; lint, Prettier, `tsc`, `check:api-types` clean; mocked E2E `11 passed`.
