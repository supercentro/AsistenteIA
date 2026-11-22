# Design

Follows `docs/frontend-standards.md`. Written after Explore (2026-11-22). Nothing is implemented.

## Explore findings

| # | Finding | Evidence |
|---|---|---|
| E1 | The failing assertion is always the same: `await expect(group).toBeFocused()` after Enter on the delete trigger (`student-chat.mocked.spec.ts:128`), with "Expected: focused", in the run of PR #22 (once) and in PR #23 (at commits 2b66c0c and 7aad322, several attempts; the owner counted 5 failures in 8 runs). It never failed in 40 local repetitions with 6 workers | CI logs; local run `--repeat-each=40` |
| E2 | `QuestionBox` called `setFocus('message')` in the `onSuccess` of every question, unconditionally (`QuestionBox.tsx`, `onSubmit`); the first fix guarded that call, which turned out not to be enough (see the last section) | Code |
| E3 | The delete trigger (`ConfirmPanel`) is not disabled while an answer is pending; only the confirm control is (`busy={removal.isPending \|\| locked}`). So the student can open the confirmation while the answer is on its way | `ConfirmPanel.tsx`, `ConversationList.tsx` |
| E4 | The test waits for the second request to be seen (`expect.poll(() => asked.length)`), not for the second answer to be shown. The mock fulfils the response at once, so the answer is processed within milliseconds of the keyboard actions; on a slow runner the order of "confirmation opened and focused" and "answer processed" varies | Test code; CI timings |
| E5 | **Reproduced deterministically**: with the second `POST /chat` delayed by 1.5 s, the confirmation group opens and is focused, and after the answer arrives the group is no longer focused (`Received: inactive`). The repro is a throw-away spec in the scratchpad, not part of the repository | Scratchpad `repro_td068` |
| E6 | After the first answer the focus goes to the question box on purpose (the existing test asserts it). That behaviour must stay | Spec "keeps the focus"; test |
| E7 | User impact: a keyboard or screen-reader student loses the confirmation they opened and the focus lands in the question box; the confirm control is disabled until the answer arrives, so nothing is deleted by mistake. The cost is confusion and an unexpected focus change, not data loss | Code reading, E5 |
| E8 | Not an application defect in the React Query layer: the invalidations after an answer do not remount the list (items keep their key), the confirmation state survives them | Code reading; E5 shows the focus is the only thing lost |

Root cause: **an unconditional focus move after an asynchronous result (application), exposed by a test that does not wait for that result (test synchronisation).** The test is correct to expect that the group keeps the focus; the application is what breaks that expectation.

## Alternatives

| | Alternative | Pros | Cons |
|---|---|---|---|
| A | Make the test wait for the second answer before using the keyboard | Smallest; removes the flake | Hides a real focus defect; a student can still hit it |
| B | Application: move the focus to the box only when it is on the form or on the body | Fixes the defect and the flake; tiny; keeps the first-answer behaviour; testable deterministically | A rule to document and test; `document.activeElement` read at the moment of the answer |
| C | Application: disable the delete trigger while an answer is pending | Removes the situation | Changes the behaviour and the spec; the student cannot open the confirmation during a slow answer |
| D | B plus A | Belt and braces | A would only be redundant once B and its deterministic test exist |

Recommendation: **B**, with the deterministic late-answer test (the repro turned into a committed test) and a component test of the rule. A alone is rejected as it would treat the symptom. C is not proposed (behaviour change). No retries, no timeouts raised, no check skipped.

## Rule of B

On a successful answer: `resetField('message')`, `onAnswered(...)`, and then focuses the box (see "Root cause of the CI failure": directly, not through `setFocus`) only if `document.activeElement` is the page body, null, or inside the question form. Anything else (a confirmation group, a conversation button, the history deletion) keeps the focus. The send button turning disabled while the answer is pending drops the focus to the body, which the rule covers.

## Risks and regression checks

- The existing assertion that the box has the focus after the first answer must keep passing (focus is on the form or the body then).
- The error paths (validation error focus to the box, failed question keeps the text) are untouched.
- Other `setFocus` or `focus()` calls after asynchronous results (for example the heading focus after a deletion in `ConversationList`) are listed in the report for a later review, not changed here.
- The 40-run local repetition proves little because the failure needs a slower runner; the deterministic test replaces it as evidence, and CI is watched over several runs after the merge.
- Jsdom `document.activeElement` behaves like the browser for these cases; the Playwright test is the final proof.

## Decisions pending the owner

- **D-F1**: approve B (recommended) over A or C.
- **D-F2**: whether the other focus moves after asynchronous results (see risks) get their own review.
- **D-F3**: whether a lesson is added to `docs/lessons-learned.md` (recommended).

## Diagnosis after PR #24 (2026-11-22)

The fix removes a real defect (focus taken by a late answer), but the keyboard test still failed once in CI with the fix and with another signature (`element(s) not found`: the confirmation group never appeared). Locally nothing reproduces it. The owner approved a diagnostic recorder in the test (option 1): it listens and prints a timeline when the test fails. It may change timing slightly (listeners and a function exposed to the page); a pass with the recorder on is therefore weaker evidence than a pass without it, and the owner decides later whether to keep it.

## Root cause of the CI failure (2026-11-22)

The first fix guarded the call to `setFocus`, but react-hook-form 7.91 runs `fieldRef.focus()` inside a `setTimeout` (`node_modules/react-hook-form/dist/index.esm.mjs`, `setFocus`). The guard was therefore evaluated in one task and the focus moved in a later one. In CI the keyboard test focused the delete trigger about 6 ms after the answer reached the page and before it was rendered (first dump, report of 2026-11-22), the guard had already found the focus free, and the deferred `focus()` took the focus from the trigger about 3 ms after the render: Enter went to the box and the confirmation never opened (`element(s) not found`). It was not reproducible locally because the window is a few milliseconds wide.

**Decision (second fix)**: decide and move the focus in the same task. `QuestionBox` no longer calls `setFocus`; it takes the textarea from the submitted form (`form.elements.namedItem('message')`) and calls `focus()` only if `focusIsFree(form)` at that instant. A JavaScript task cannot be interleaved, so the window does not exist.

**Evidence**: (a) in a real browser, with a hook that focuses the trigger in the window of the deferred `setFocus` (a throw-away spec, not kept), the committed first fix ends with the box focused and the test fails as in CI, and the new code has no deferred focus at all; (b) a component test opens the window with a spy on `setTimeout` (stacks of react-hook-form or `QuestionBox`) and asserts that every programmatic focus of the box happened while the focus was free: it fails on the first fix and on a mutant that defers again; (c) mutations 5 of 5 detected. The cause is supported by the dump and the library source; the caller of `focus()` was not logged in CI (the second recorder version could not run, billing).

Limits: the component test opens the window only through timers scheduled from react-hook-form or the box; a future deferral through a microtask, an animation frame or an effect would not be covered by it, although the invariant it asserts (the box is focused only while the focus is free) would still catch a violation if the window occurred. If `namedItem('message')` ever returned something other than the textarea (a duplicated name) nothing would be focused, silently; the form has a single `message` field.
