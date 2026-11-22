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
