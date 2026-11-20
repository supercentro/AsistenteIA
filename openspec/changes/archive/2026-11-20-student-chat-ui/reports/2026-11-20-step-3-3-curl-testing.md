# Step 3.3 Report - Manual endpoint testing against the local stack

- Date: 2026-11-20
- Change: student-chat-ui
- Target: local development stack `http://127.0.0.1:8000/api/v1` (backend and worker as they were running; not rebuilt or recreated). The existing test accounts (two teachers and a student) and a fictitious text document about mitochondria; real Gemini (free tier) for two questions only.
- The script is not part of the repository; no password was printed.

| Call | Expected | Result |
|---|---|---|
| document of the fictitious subject | `ready` | `ready` |
| a student not enrolled asks | 403 | 403 |
| a teacher asks | 403 | 403 |
| empty message / 2001 characters | 422 / 422 | 422 / 422 |
| the enrolled student asks (real Gemini) | 200 with answer and sources | 200 in 1.4 s, 3 sources |
| a source | `filename`, `rank`, `snippet`, `page_number` (null for text) | as expected |
| follow-up on the same conversation (real Gemini) | 200, same `conversation_id` | 200, same id |
| an off-topic question | 200 `no_material`, no sources, no model call | 200, `no_material` true |
| list of the subject's conversations | both, none of another subject | 2 |
| messages of the conversation | user, assistant, user, assistant, sources on the answers | as expected |
| a teacher lists conversations / another teacher reads the messages | 403 / 403 | 403 / 403 |
| delete one conversation / again | 204 / 404 | 204 / 404 |
| unenrol the student, then ask | 403 | 403 |
| after leaving, read the messages | 404 | 404 |
| delete the whole history | 204 (also the conversation hidden by leaving) | 204 |
| the history | empty | `[]` |
| delete the subject (cleanup) | 204 | 204 |

## Observations
- The answer to the first question carried **no `[n]` marker** and the backend listed **all three retrieved chunks** as sources: the situation of TD-062, and the reason why the interface shows them as "material consultado" and not as support.
- `last_message_preview` was `null` for every conversation (TD-066).

## Restoration
The subject and everything under it were deleted through the API and the student's history was deleted; no account was created.

## Outcome
Step 3.3 status: PASS (23 of 23 checks).
