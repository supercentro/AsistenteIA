# Tasks

> Explore finished 2026-11-22; planning only. Implementation needs the owner's approval of D-F1 (alternative B). Frontend only: no API contract, backend, data, dependency or infrastructure change; no check is disabled, skipped or relaxed (no retries, no longer timeouts). Follows `docs/openspec-tasks-mandatory-steps.md`.

## 0. Branch

- [x] 0.1 Step 0: create the branch `feature/student-chat-focus-stability` from `main` before any code change. Merge only through a Pull Request.

## 1. Tests first

- [x] 1.1 Component test of `QuestionBox` (or `ChatPage`) with the focus rule: after an answer the box has the focus when it was on the form or on the body; a control focused elsewhere (a button, a group with `tabIndex=-1`) keeps it
- [x] 1.2 Playwright mocked test of the late answer: the second `POST /chat` is held back, the delete confirmation is opened with the keyboard and focused, the answer arrives and is shown, the group still has the focus, Tab + Enter confirm and the conversation leaves the list. Hold the answer with an explicit gate released by the test (no fixed sleep)
- [x] 1.3 Keep the existing keyboard test as it is: with the fix it passes whichever comes first, the opened confirmation or the answer (record that decision in the report)
- [x] 1.4 Run the new tests before any implementation and record the failing run (command and failure summary) in `reports/`

## 2. Implementation (frontend)

- [x] 2.1 `QuestionBox.tsx`: the focus returns to the box on success only when `document.activeElement` is null, the body or inside the form
- [x] 2.2 Mutation checks: remove the condition (the late-answer test fails), invert it (the first-answer test fails), keep it but ignore the body case (the pending-answer test fails)
- [x] 2.3 ESLint, Prettier, `tsc` clean; `npm run check:api-types` unchanged

## 3. Verification

- [x] 3.1 Step N: review and update the existing chat tests (`ChatAsking.test.tsx`, `ChatConversations.test.tsx`, the e2e specs)
- [x] 3.2 Step N+1: run the unit tests and the mocked Playwright suite; repeat the keyboard test 40 times with 6 workers and with a throttled CPU; verify no persistent data is touched; report in `reports/`
- [x] 3.3 Step N+2: no endpoint changes; record that
- [x] 3.4 Step N+3: Playwright MCP run by the agent: open the chat, ask, open the delete confirmation while the answer is pending, check that the focus stays (mocked API or the local stack with the fake model only, no real Gemini call)
- [x] 3.5 Step N+4: documentation: `docs/technical-debt.md` (TD-068 with the cause and the fix; closed only after CI is stable over several runs), `docs/lessons-learned.md` (a focus move after an asynchronous result must check where the focus is), `docs/frontend-standards.md` if the rule belongs there
- [x] 3.6 Independent review (`adversarial-review` skill): focus management, keyboard and screen-reader behaviour, regressions of the first-answer focus
- [x] 3.7 Final gates of `docs/base-standards.md` section 9 re-run after the last change; `openspec validate --all --strict`; CI on Linux watched over several runs after the pull request

## 4. Diagnosis of the CI failure that remains (owner's decision of 2026-11-22, option 1)

- [x] 4.1 `frontend/e2e/support/diagnostics.ts`: a recorder that only listens (focus, key, click, group added or removed, navigations and reloads, console errors, API responses) and prints the timeline and a last snapshot of the page when the keyboard test fails; the expectations of the test are unchanged, no wait, no retry, no workflow change
- [x] 4.2 Validated locally by forcing a failure (the dump shows the timeline and the snapshot); the suite passes and 150 repetitions of the chat spec pass with the recorder on
- [x] 4.3 Remote evidence (the CI was blocked by the account billing and unblocked on 2026-11-22 after the budget was raised): the recorder printed the dump of a failing run (commit `3f6cfcd`, first CI run with the fix of the guard) and it was read and analysed before any further correction (report `reports/2026-11-22-verification-and-review.md`: the deferred `focus()` of react-hook-form's `setFocus`); the second recorder version (`1c8e79d`) never ran because the jobs did not start; after the second fix the frontend job passed in 11 of 11 executions (5 at `011f852`, 2 at `81e38f8`, 1 at `f8f28b0`, 2 at `69f48bc`, 1 at `4f17dfa`), and the CI of `main` stayed green
- [x] 4.4 Cause found without CI (owner's decision of 2026-11-22): react-hook-form's `setFocus` defers the focus with a timer; the guard of the first fix ran before the move. Reproduced in a real browser with a hook that focuses the trigger in that window; fixed by focusing in the same task (`QuestionBox.tsx`); component test with the timer window, 5 of 5 mutants detected; independent review PASS WITH GAPS (documentation gaps fixed). The recorder stays until the owner decides
- [x] 4.5 Remote confirmation (the CI unblocked after the budget of the account was raised, 2026-11-22): at the commit `011f852` the frontend job passed in 5 of 5 executions (3 reruns of the `push` run and 2 of the `pull_request` run); backend and privileges passed in both runs; the recorder printed nothing because no run failed; before the second fix the same test failed in 5 of 8 runs. TD-068 stays open under observation until the CI of `main` is stable after the merge

> Notes: 3.7 closed with the CI of `011f852` (backend, frontend and privileges green in both runs, frontend 5 of 5). TD-068 is closed here only as a change task; the debt itself stays open in observation after the merge. Not archived. Outside this change: the other asynchronous focus moves (TD-068 text), the intermittent `LoginPage` test, the duplicated `push` and `pull_request` runs that double the minutes of Actions.
