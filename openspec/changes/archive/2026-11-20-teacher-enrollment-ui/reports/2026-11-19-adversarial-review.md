# teacher-enrollment-ui: independent adversarial review (task 3.6)

Date: 2026-11-19. Reviewer: a separate read-only subagent session (skill `adversarial-review`), clean context, on the uncommitted tree of `feature/teacher-enrollment-ui`. It ran the frontend suite twice (488 passed each time), the mocked Playwright suites (23 passed), typecheck and lint, and found no flaky test. Dispositions were added by the implementing session.

**Verdict of the first pass: FAIL** (two Major, no Blocker). Held: the neutrality of the 404 (the same code path for an unregistered e-mail and a teacher's e-mail, no difference in the interface, the DOM or the logs), e-mails rendered as text, the role guard, the query keys and the cache isolation, no request for students, the `cancelQueries` race tests, and the wording of the removal against the data model.

| # | Severity | Finding | Disposition |
|---|---|---|---|
| 1 | Major | A 404 on the removal was always taken as "the enrollment no longer existed"; the same status also comes from a subject that is gone or not the teacher's, so the page said so and hid it | Fixed: after a removal 404 the subject and the list are requested again and the not-found view appears if the subject is gone; test for both outcomes |
| 2 | Major | Enrolling while the list was loading or had failed wrote a one-row list into the cache, so the page showed an incomplete roster as if it were whole | Fixed: with no loaded list the list is requested again instead; two tests (list failed, list loading) |
| 3 | Minor | Weak assertions: a constant compared with a regex of itself (the hint), a string constant checked for "no teacher" instead of the rendered message, and a double-submit test that clicked a disabled button | Fixed: assertions on the rendered DOM; Enter pressed twice proves one request |
| 4 | Minor | The accessibility scan covered only the populated list | Fixed: scans for the empty state, the form error and the open confirmation |
| 5 | Minor | The enrollment error and the "gone" notice stayed after unrelated actions | Fixed: the error clears when the field is edited; the notice clears when a student is enrolled; tests |
| 6 | Minor | The label of the remove button is not bidirectionally isolated | Accepted: the API accepts ASCII e-mails only; written in design D6 |
| 7 | Question | No record of the failing-first run or the mutations | Recorded in `2026-11-19-tdd-and-mutation-evidence.md` |

Evidence of the corrections: the TDD report (4 failed before, 497 passed after, three more mutations detected).

Final state: no open Blocker or Major finding. A second independent pass was not run because every finding was fixed with a failing-first test and a mutation check; it can be requested before the merge.
