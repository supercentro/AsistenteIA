# teacher-material-ui: independent adversarial review (task 3.6)

Date: 2026-11-18. Reviewer: a separate read-only subagent session (skill `adversarial-review`), clean context, on the uncommitted tree of `feature/teacher-material-ui`. It ran the frontend suite (413 passed), the mocked Playwright suites (20 passed), typecheck and lint; it did not run the real-backend spec. Dispositions were added by the implementing session.

**Verdict of the first pass: FAIL** (two Major, no Blocker). Authorization and isolation held: students get the forbidden screen with no request, query keys carry the user id, the cache is cleared on session end, no server text or file content is shown or logged, and no dependency or contract was changed.

| # | Severity | Finding | Disposition |
|---|---|---|---|
| 1 | Major | The spec says 429 and 503 tell how long to wait; the code used `Retry-After` for 429 only, and the upload 503 carries it in the contract | Fixed: `Retry-After` is read for 429 and 503 and a 503 message adds the wait; tests |
| 2 | Major | The 15 s limit of ordinary requests applied to uploads: a 10 MB file on a slow link could time out while the server accepted it, inviting a duplicate | Fixed: uploads use 120 s; a timeout says the file may have arrived and to check the list first; spec scenario and tests |
| 3 | Minor | `setQueryData` without `cancelQueries`: an older refresh could make an uploaded row vanish or a deleted row reappear | Fixed: both hooks cancel the queries first; two tests with a delayed refresh |
| 4 | Minor | Direction characters in a file name could reorder neighbouring text | Fixed: the name is wrapped in `<bdi>` (and the confirmation question is isolated); test |
| 5 | Minor | The "subject unavailable" state survived a change of `:subjectId` | Fixed: the page is keyed by the subject; test navigating from a subject refused on upload to another |
| 6 | Minor | A failed background refresh of the subject replaced the whole page | Fixed: the error view shows only when there is no data; test |
| 7 | Minor | Only the last of several finished documents was announced | Fixed: all are announced; test |
| 8 | Minor | Focus lost after a deletion and after an upload; other confirm controls usable during a deletion | Fixed: the focus goes to the documents heading after a deletion and back to the upload button after an upload; every confirm control is disabled meanwhile; tests |
| 9 | Minor | Weak tests: the hidden-tab test had no positive control | Fixed: a test checks that polling resumes when the tab is visible again |
| 10 | Question | `accept=".pdf,.txt,.md"` as a hint | Confirmed intended (the API decides); written in design D4 |

Evidence of the corrections: `2026-11-18-tdd-and-mutation-evidence.md` (12 failed before, 429 passed after, ten more mutations detected).

Final state: no open Blocker or Major finding. A second independent pass was not run because every finding was fixed with a failing-first test and a mutation check; it can be requested before the merge.
