# Step 3.2 Report - Unit tests and database verification

- Date: 2026-11-20
- Change: student-chat-ui
- Agent: Claude (implementing session)

## Commands Executed
- targeted: `npx vitest run` on the test files of the change (see `2026-11-20-tdd-and-mutation-evidence.md`)
- `npm run test:coverage` (full frontend suite with thresholds), ten consecutive plain full runs and twelve more coverage runs (the suite is sensitive to load, TD-065)
- backend: the chat and conversation tests are unchanged and run in CI (`test_chat*`, `test_conversations*`); no backend file changed
- read-only counts of the development database before and after the manual and browser verification (steps 3.3 and 3.4)

## Unit Test Results
- Full frontend suite: 41 files, **585 passed**, 1 skipped (on-demand policy release check); coverage 97.21 % statements, 92.31 % branches, 99.26 % functions.
- Ten consecutive plain full runs: **0 failures**; twelve coverage runs after raising the wait limit: 0 failures (one coverage run had failed once before, see the TDD report).

## Database State Verification
The change touches no table and no migration; the check covers the side effects of the manual and browser runs, which used the API only and the existing test accounts.

- Pre-test baseline: users 27; subjects 7; documents 14; enrollments 7; conversations 23; messages 56; message sources 22.
- Post-test validation: users **27**; subjects **7**; documents **14**; enrollments **7**; conversations **23**; messages **56**; message sources **22**.
- State restored: **Yes, entirely.** The subjects created by the checks were deleted through the API (which removes their documents, enrollments, conversations and sources) and the student test account's own history was deleted through the API; no account was created. That account had no conversation before the runs.
- Real Gemini calls (free tier, fictitious material, local only, never from CI): 2 in the API check, 1 in each of the three runs of the gated browser spec and 1 in the manual browser session.

## Outcome
- Step 3.2 status: PASS.
- Blocking issues: none.
