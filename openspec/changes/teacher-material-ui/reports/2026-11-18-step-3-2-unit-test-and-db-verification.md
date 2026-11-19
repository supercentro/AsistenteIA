# Step 3.2 Report - Unit tests and database verification

- Date: 2026-11-18
- Change: teacher-material-ui
- Agent: Claude (implementing session)

## Commands Executed
- targeted: `npx vitest run` on the nine files of the change (see `2026-11-18-tdd-and-mutation-evidence.md`)
- `npm run test:coverage` (full frontend suite with thresholds)
- `uv run --no-sync python -m pytest tests/unit -k "subject or document or enrollment" -q` (backend unit tests of the touched areas; `pytest.exe` is blocked by Windows Application Control on this host)
- read-only counts of the development database before and after the manual and browser verification (steps 3.3 and 3.4)

## Unit Test Results
- Targeted tests: all passed after the implementation (92 tests in nine files).
- Full frontend suite (after the review corrections): 30 files, **429 passed**, 1 skipped (on-demand policy release check); coverage 97.69 % statements, 93.46 % branches; `src/components` 97.08 %, `src/hooks` 100 %. Before the review it was 29 files and 413 passed.
- Backend (not changed by this change): 99 passed, 1 skipped (Linux-only PDF child); the integration tests run in CI.
- Notes: the existing test `App.test.tsx` "ends the session once..." failed in 2 of 8 full-suite runs with the new tests present (0 of 8 on the unchanged code, and once in the CI of PR #17 on a documentation-only commit); it passes alone and in subsets. Recorded as TD-065. Its cause (2026-11-19): a `GET /subjects` left in flight by an earlier test reached the handler of this test late and was counted; with more test files the delay is more frequent. The test now counts only the requests of its own session (10 of 10 full runs passed afterwards, against 8 of 10 failing before); the product code was not involved.

## Database State Verification
The change touches no table and no migration; the check covers the side effects of the manual and browser runs, which used the API only.

- Pre-test baseline: revision `0007`; users 24 (teachers 8); subjects 7; documents 14; chunks 50; conversations 23.
- Post-test validation: revision `0007`; users **27** (teachers **10**); subjects 7; documents 14; chunks 50; conversations 23.
- State restored: **partly.** Subjects, documents and chunks are back to the baseline (the runs deleted what they created through the API, which cascades). Three test accounts remain (two teachers created with the administrative command, one student registered through the API): `tm-teacher-a-1118202025@example.com`, `tm-teacher-b-1118202025@example.com`, `tm-student-1118202025@example.com`. They cannot be removed through the API (no account deletion, TD-064) and removing them needs a `DELETE` on the persistent database, which was not authorised. The student also accepted the privacy policy in the browser run.
- The test-only copies of the three fictitious files used for the browser run were removed from `.playwright-mcp/` (ignored by Git) after the run.

## Outcome
- Step 3.2 status: PASS.
- Blocking issues: none. Open point (inherited): the accumulated test accounts of the development database.
