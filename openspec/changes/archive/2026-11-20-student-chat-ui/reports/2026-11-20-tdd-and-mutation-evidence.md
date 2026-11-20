# student-chat-ui: TDD and mutation evidence (sections 1 and 2)

Date: 2026-11-20. Branch `feature/student-chat-ui` (from `main` `88a56f3`). Frontend only.

## Failing run before the implementation (task 1.10)

Command (from `frontend/`): `npx vitest run src/lib/questionSchema.test.ts src/services/chatServices.test.ts src/pages/ChatAccess.test.tsx src/pages/ChatAsking.test.tsx src/pages/ChatConversations.test.tsx src/pages/SubjectsPage.test.tsx`

Result: **6 test files failed; 44 tests failed, 16 passed (60)**. Failure summary: `questionSchema`, `chatService`, `conversationService` and `strings.chat` did not exist, the chat route rendered the not-found page, and the student's subject list had no chat link and no history action. The 16 that passed are existing tests and negative cases that hold without the feature.

## Passing run after the implementation (tasks 2.1 to 2.4)

All passed after five rounds of corrections found by the first runs themselves: the reader of the generated types (fields not marked required, `Required<>` with a justification), a `jsx-a11y` rule that rejects a component prop named `role`, `react-hook-form` `reset()` unregistering the field so that the focus could not return to the box (`resetField` keeps it registered), a test helper whose ids did not match the answer's `message_id`, and a thread keyed by a local id that remounted the question when the server id replaced it (an index key on the append-only list).

## Mutation checks (task 2.5)

Each change was applied to the production code, the test files of the feature were run, and the code was restored. Every mutation is detected:

| Mutation | Result |
|---|---|
| teachers reach the chat route | 1 failed |
| the send control is not disabled while pending | 1 failed |
| the conversation id is never sent | 3 failed |
| answers rendered as HTML | 1 failed |
| sources labelled as proof | 1 failed |
| a deletion without confirmation (trigger confirms) | 11 failed |
| the 15-second limit | 1 failed |
| the question cleared on failure | 9 failed |
| the question logged | 1 failed |
| no shared-limit remark on 429 | 1 failed |
| no refresh after a timeout | 1 failed |
| the history action shown to teachers | 2 failed |
| the whole-history wording drops the other subjects | 1 failed |
| no refresh of the list when a thread is gone | 1 failed |
| no reconciliation after the answer | 1 failed |

One more mutation was **not** detected at first: removing `cancelQueries` before the cache update of an answer. The reason is that the invalidation that follows already cancels the request still on its way, so `cancelQueries` was redundant; it was removed and the reconciliation mutation above guards the behaviour.

## Review round (task 3.6)

The independent review gave FAIL (two Major findings). Failing run before the corrections: `npx vitest run src/pages/ChatReviewFixes.test.tsx`: **3 failed, 2 passed** (the open conversation changing while a question is pending; a 404 on a question of an open conversation taken as a vanished subject, twice). After the corrections the whole suite passes: 41 files, **585 passed, 1 skipped**; coverage 97.21 % statements, 92.31 % branches. More mutations were detected: the list not locked while pending (1 failed); a 404 on an open conversation taken as a vanished subject (2 failed); the kept question sent into the vanished conversation (1 failed, after adding the test of a thread whose messages answered 404); a conversation without a preview labelled with a constant (1 failed).

## Deviations

- The label of a conversation without a preview was added after the browser run showed that the backend never fills the preview (TD-066); its test passed together with the code, so it is covered by the mutation above instead of a separate failing run.
- 320 px, keyboard use and real timing are verified in the browser (`2026-11-20-step-3-4-e2e-verification.md`): jsdom has no layout.
- One run of the coverage suite failed once and 12 consecutive coverage runs and 20 plain runs afterwards did not; the asynchronous wait limit was raised (design D11).
