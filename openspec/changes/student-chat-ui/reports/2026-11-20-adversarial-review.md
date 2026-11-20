# student-chat-ui: independent adversarial review (task 3.6)

Date: 2026-11-20. Reviewer: a separate read-only subagent session (skill `adversarial-review`), clean context, on the uncommitted tree of `feature/student-chat-ui`. It ran the frontend suite twice (579 passed each time), the mocked Playwright suites (27 passed), typecheck and lint, and found no flaky test. Dispositions were added by the implementing session.

**Verdict of the first pass: FAIL** (two Major, no Blocker). Held: no `dangerouslySetInnerHTML` or autolinking, answers and previews as plain text, file names isolated with `bdi`, `[n]` markers literal, the neutral wording of the sources, logging of method, path and status only, user id in every query key, cache cleared at the end of the session, the teacher route guard, the policy link in a new tab with `noopener`, the deletion wordings, and the policy text and its version untouched.

| # | Severity | Finding | Disposition |
|---|---|---|---|
| 1 | Major | The student could open another conversation, start a new one or delete the open one while a question was pending; the answer then selected its own conversation and took the student away | Fixed: the list, the new-conversation action and every confirm control are locked while a question is pending; test of the lock and of the answer staying in its conversation |
| 2 | Major | A 404 on a question that carried a conversation id (a conversation deleted elsewhere) replaced the page with "subject not available" | Fixed: the page keeps the subject, shows that the conversation is not available, refreshes the list, keeps the question and starts a new conversation next; a 404 or 403 on a new conversation still means the subject; tests |
| 3 | Minor | Deleting the open conversation while a question is pending | Covered by the lock of finding 1 (the confirm control is disabled) |
| 4 | Minor | A timeout keeps the question in the box, which invites a duplicate turn; for a new conversation only the list is refreshed | Accepted with the existing warning and refresh; the message now also points at the list of conversations |
| 5 | Minor | The no-guarantee check of the sources is a regex in one language | Accepted: plus the label "consultado" check and the mutation that relabels the sources as proof |
| 6 | Minor | `Required<>` over the generated types asserts what the contract does not mark | Accepted with the comment (the backend always sends them); a contract change would be its own work |
| 7 | Minor | The pending question inside the log is announced, and again when replaced by the saved message | Accepted: the replacement keeps the same position (index key) and was not tested with a screen reader; noted for the pilot |

Evidence of the corrections: `2026-11-20-tdd-and-mutation-evidence.md` (3 failed before, 585 passed after, four more mutations detected).

Final state: no open Blocker or Major finding. A second independent pass was not run because every finding was fixed with a failing-first test and a mutation check; it can be requested before the merge.
