# Step 3.2 Report - Unit tests and database verification

- Date: 2026-11-19
- Change: teacher-enrollment-ui
- Agent: Claude (implementing session)

## Commands Executed
- targeted: `npx vitest run` on the test files of the change (see `2026-11-19-tdd-and-mutation-evidence.md`)
- `npm run test:coverage` (full frontend suite with thresholds) and ten consecutive `npx vitest run` of the whole suite (the suite is sensitive to load, TD-065)
- backend: the enrollment tests are unchanged and run in CI (`test_enrollments*`); `uv run --no-sync python -m pytest` was not repeated because no backend file changed
- read-only counts of the development database before and after the manual and browser verification (steps 3.3 and 3.4)

## Unit Test Results
- Full frontend suite: 35 files, **497 passed**, 1 skipped (on-demand policy release check); coverage 97.54 % statements, 93.11 % branches, 99.52 % functions; `src/components` 96.15 %, `src/hooks` 100 %.
- Ten consecutive full runs: **0 failures** (the intermittent test of TD-065 did not fail).
- Notes: no flaky behaviour seen in these runs.

## Database State Verification
The change touches no table and no migration; the check covers the side effects of the manual and browser runs, which used the API only and the existing test accounts.

- Pre-test baseline: revision `0007`; users 27 (teachers 10); subjects 7; documents 14; chunks 50; conversations 23; enrollments 7.
- Post-test validation: revision `0007`; users **27** (teachers **10**); subjects 7; documents 14; chunks 50; conversations 23; enrollments **7**.
- State restored: **Yes, entirely.** The subjects created by the checks were deleted through the API (which removes their enrollments) and no account was created.

## Outcome
- Step 3.2 status: PASS.
- Blocking issues: none.
