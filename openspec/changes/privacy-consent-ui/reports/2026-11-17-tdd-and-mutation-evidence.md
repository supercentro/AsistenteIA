# privacy-consent-ui: TDD and mutation evidence (sections 1 and 2)

Date: 2026-11-17. Branch `feature/privacy-consent-ui`. Frontend only.

## Failing run before the implementation (task 1.7)

Command (from `frontend/`): `npx vitest run src/lib/consent.test.ts src/lib/consentApi.test.ts src/pages/PrivacyPage.test.tsx src/pages/ConsentPage.test.tsx src/pages/consentGate.test.tsx`

Result: **5 test files failed; 31 tests failed, 7 passed (38)**. The 7 that passed are negative cases that hold trivially without the feature (for example "another 403 code leaves the profile alone"). Failure summary: modules `./consent` and `strings.privacy` / `strings.consent` did not exist, `markConsentStale` was not exported, `/privacy` and `/consent` rendered the not-found page, and the 403 `CONSENT_REQUIRED` left `consent_version` untouched (`expected '2026-10-v1' to be null`).

## Passing run after the implementation (tasks 2.1 to 2.7)

Same command: **5 files passed, 46 tests passed (46)**.

## Mutation checks (task 2.8)

Each change was applied to the production code, the five files were run, and the code was restored (`mutate.py`, scratchpad of the session). Every mutation is detected:

| Mutation | Result | Detected by |
|---|---|---|
| `RequireConsent` never holds | 6 failed / 40 passed | gate tests (`consentGate.test.tsx`) |
| remove the 403 `CONSENT_REQUIRED` handler in `apiClient.ts` | 1 failed / 45 passed | `consentApi.test.ts`: "marks the consent of a signed-in student as stale and does not retry" |
| hold only when the version is null (ignore an outdated one) | 5 failed / 41 passed | `consent.test.ts` and the outdated-version gate and notice tests |
| hold teachers too | 1 failed / 45 passed | `consent.test.ts`: "never holds a teacher" (the page-level teacher tests pass because `ConsentPage` itself redirects a teacher away, a second layer) |

After the restoration the suite is green again (46 passed).

Note (review): the "hold teachers too" mutation is detected by one unit test only; the page-level teacher tests pass because `ConsentPage` itself sends a teacher away.

## Review round (section 5)

Failing run before the corrections: `npx vitest run src/lib/consent.test.ts src/lib/policyPlaceholders.test.ts src/pages/ConsentPage.test.tsx src/pages/consentGate.test.tsx` gave **4 failed tests and 1 failed file**: the late acceptance wrote the profile of the first student (`1111...`) into the session of the next user (the defect of finding 1), the policy link had no `target`, the 403 mid-session path showed no changed-policy notice, the acceptance time was erased, and the placeholder detector did not exist. After the corrections: 8 files, 111 passed, 1 skipped (the on-demand release check, which fails while owner placeholders remain: `POLICY_RELEASE_CHECK=1 npx vitest run src/lib/policyPlaceholders.test.ts`).

## Deviations

- Task 1.6 asks for "no horizontal scrolling at 320 px": jsdom has no layout, so it cannot prove it. It is verified in the browser with Playwright MCP (task 4.4); the unit tests cover the accessibility rules (axe, labels, focus) and the absence of inline copy (`tests/copy.test.ts` covers the new pages and components).
- The shared test student `studentUser` now carries the current consent, and `unconsentedStudent` and `outdatedStudent` were added: without it, every existing test that signs a student in would land on the consent screen.

## Gates after the implementation (Windows host)

Re-run after the review corrections (final state): `npm run lint`, `format:check`, `typecheck`, `check:api-types`, `test:coverage` (22 files, **287 passed, 1 skipped** (the on-demand release check); overall coverage 98.07 % statements, 94.94 % branches), `build`, `npx playwright test consent-flow auth-flow smoke` (16 passed), `openspec validate --all --strict` (21 passed): all pass. The first implementation pass had 21 files and 282 tests.

## Adaptation to Ley 25.326 (2026-11-18)

First round: 6 tests written first failed (6 failed, then the file passed with 14 tests); 4 mutations of the text detected. After the independent review: 3 failed before the corrections, 37 passed after in the three touched files; 6 mutations of the text and 1 of the placeholders detected (`reports/2026-11-18-adversarial-review-argentina.md`). Final gates on the Windows host: `lint`, `format:check`, `typecheck`, `check:api-types`, `build` clean; `test:coverage` 22 files, **296 passed, 1 skipped** (the on-demand release check), 98.07 % statements and 94.94 % branches; Playwright mocked (`consent-flow auth-flow smoke`) 16 passed; `openspec validate --all --strict` 21 passed. The release check (`POLICY_RELEASE_CHECK=1`) fails on purpose while the six owner placeholders remain.
