# student-chat-focus-stability: verification and independent review (2026-11-22)

Branch `feature/student-chat-focus-stability` from `main` 2afdfbd. Frontend only; no backend, contract, data or real-model call.

## TDD evidence
`reports/_failing_run.txt`: before the fix, two of the three component tests and the new Playwright test fail (`Expected: focused, Received: inactive`); the third test guards the existing behaviour (the focus falls to the body) and passes before and after.

## Mutations (`reports/_mutations.txt`)
Condition removed, condition inverted, body case ignored, form case ignored: all detected; the e2e test also fails without the condition. Survivor: `form === null` accepted as free. It is reachable only if `handleSubmit` is called without an event (never in the UI: a submit always carries it) and is accepted as equivalent in practice.

## Gates
`tsc --noEmit`, ESLint, Prettier clean; `npm run check:api-types` unchanged; vitest 588 passed, 1 skipped (41 files); Playwright mocked suite 28 passed. Repetition: the new test and the keyboard test 40 times with 12 workers (80 of 80), then the whole chat spec 60 times with 6 workers (300 of 300) after the review fix.

## Independent review: PASS WITH GAPS
| Sev | Finding | Disposition |
|---|---|---|
| Major | The new e2e test was itself flaky (1 in 15-30 locally): its mocked thread did not hold the late answer, so the refetch after the answer removed it | Fixed: the handler adds both messages to the thread; the test also asserts that the confirm control is disabled before the answer arrives; 300 of 300 after the fix |
| Minor | Surviving mutant `form === null` | Documented above; the rule already treats an unknown form as "not inside" |
| Minor | Untested focus positions (conversation button, sources details) | Accepted: the rule is the same for any element outside the form; a policy link and the confirmation are tested |
| Minor | No announcement when the focus does not move | Checked: the thread is `role="log"` (a live region), so the answer is announced; noted in TD-068 |
| Minor | Diagnosis is not proven to be the only cause in CI | Accepted: TD-068 stays open until the CI is stable over several runs |
| Minor | TD-068 text still said the cause was missing | Fixed |

## Findings outside the scope (D-F2), documented in TD-068
Unconditional `focus()` after an asynchronous result in `ConversationList`, `DocumentsSection`, `EnrollmentsSection` (heading after a deletion) and `DocumentUploadForm` (input and submit button after an upload). Not changed.

## Update after the CI of PR #24 (2026-11-22)

The keyboard test failed again in CI at the commit with the fix (`186f914`, one of two runs; the other passed) at `expect(group).toBeFocused()` with `element(s) not found` (the confirmation group never appeared). The reproduced defect ends with `Received: inactive`, so it does not explain this failure. Local checks that did not reproduce it, with the old and the new code: the original test at CPU slowdowns of 6, 10 and 14 (30 runs each), the whole mocked suite four times against a cold Vite server, and 300 repetitions of the chat spec. CI uploads no trace, so the cause of the CI failure is **open**. Hypotheses, unverified: another focus or remount between `focus()` and Enter, or a dev-server reload during the run. TD-068 stays open and the fix is presented as the correction of a real defect, not as the end of the flake.

## First CI dump (2026-11-22, run of commit 3f6cfcd, the fix in place)

The recorder printed this timeline for the failing keyboard test (times in ms since the start of the test):

```
1201  click   button "Enviar"                       (second question)
1219  response POST /chat 200
1223  focusout button "Enviando…"                   (the test focuses the delete trigger)
1224  focusin  button "Eliminar la conversación …"
1230  group-added  the second answer is rendered
1233  focusout button "Eliminar la conversación …"  <- the trigger loses the focus
1234  focusin  textarea                             <- 1 ms later: a programmatic focus() on the question box
1244  keydown  Enter on textarea                    (the test presses Enter: it lands in the question box)
```

Reading: the test focuses the trigger about 6 ms after the answer arrived and before React rendered it. About 3 ms after the render, the focus goes from the trigger to the question box although the guard of the fix is in place, so Enter is typed into the box and the confirmation never opens (`element(s) not found`). The failure is therefore still a focus move to the question box when the answer arrives; the open question is **why `focusIsFree` allowed it**. Hypotheses, not yet distinguished: (a) the trigger was replaced in the DOM when the answer was rendered, which leaves `document.activeElement` on the body and makes the focus "free"; (b) the guard ran at a moment when the focus was elsewhere. In the jsdom probe (a throw-away test, not kept) the trigger survives the answer and keeps the focus, and locally the window between the answer and its render was never hit (0 failures in hundreds of runs), so only CI shows it.

## Second recorder version and the CI block

The recorder was extended (commit 1c8e79d) to log every programmatic `focus()` with the element that had the focus and the first frames of the stack, and the addition or removal of the delete buttons (a remount). It was validated locally by forcing a failure. The CI runs of that commit did not start: GitHub reports "recent account payments have failed or your spending limit needs to be increased" (billing of the account, outside the authorised scope). The next step needs the CI to run again, several times, until a failing run prints the new dump.

## Root cause found and second fix (2026-11-22, local, nothing pushed)

Cause: react-hook-form 7.91 `setFocus` moves the focus in a `setTimeout`; the guard of the first fix was evaluated before it (see `design.md`, "Root cause of the CI failure"). Local evidence: a real-browser spec (throw-away) that focuses the delete trigger in the window of the deferred focus fails on the committed first fix with the box focused, as in CI; the second fix focuses in the same task, so the window does not exist. Component test with the timer window: fails on the first fix and on the mutant "focus deferred again"; mutations 5 of 5 detected (`_mutations.txt`; the earlier survivor `form === null` no longer exists because the code path changed: with a null form nothing is focused, which no test covers and is accepted).

Controls: PASS locally, `npm run typecheck`, `npm run lint`, `npm run format:check`, `npm run check:api-types`, vitest with coverage (589 passed; the thresholds hold), Playwright mocked suite 28 passed, the chat spec 60 times with 6 workers (300 of 300). Note: one run of the coverage command failed once in `LoginPage.test.tsx` ("sends one request when submitted twice", a file this change does not touch) and passed in the next three runs, with and without this change; it is a separate intermittent test to record if it recurs.

Independent review of the second fix: PASS WITH GAPS (no Blocker or Major). Gaps: documentation of the root cause (fixed here), the limits of the timer window in the component test (stated in the design), the silent no-op if the textarea is not found (stated), the removed surviving mutant (stated above).

BLOCKED: the remote controls (CI of the pull request, several runs of the frontend job) cannot run while the GitHub account billing blocks the jobs; TD-068 stays open until they pass.

## CI confirmation (2026-11-22, commit 011f852)

After the account budget was raised the jobs started again. Frontend: 5 of 5 executions passed (3 of the `push` run, 2 of the `pull_request` run). Backend and privileges passed in both runs (those of the `pull_request` run had failed only because the jobs never started). The recorder printed no dump because no run failed. Approximate consumption of the reruns of this check: about 60 minutes of runner time. TD-068 stays open in observation until the CI of `main` is stable after the merge.
