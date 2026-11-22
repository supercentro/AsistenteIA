# Proposal

## Why

TD-068: the Playwright mocked test "a student asks, reads the sources, continues and deletes a conversation with the keyboard" fails intermittently in CI (5 of 8 runs on unchanged chat code, none in 40 local runs). Explore (2026-11-22) found that this is not only a test problem. `QuestionBox` calls `setFocus('message')` whenever an answer arrives, wherever the focus is at that moment. The delete trigger of a conversation stays usable while an answer is pending, so a keyboard or screen-reader student who has opened the delete confirmation sees the focus pulled away from it to the question box when the answer arrives. The test only exposes it because it opens the confirmation as soon as the second request is seen, and a slower CI runner processes the answer after that. A deterministic reproduction with a delayed second answer fails every time (`design.md`).

## What Changes

- Frontend only, no contract, data or architecture change: after an answer, the question box takes the focus back only when the focus is on the question form or has fallen to the page body (which happens when the send button becomes disabled). A focus the student has moved elsewhere, such as an open confirmation, stays where it is.
- A deterministic end-to-end test of the late answer (the second answer arrives after the confirmation was opened) and a component test of the focus rule, written first.
- TD-068 is closed when the fix is merged and CI is stable; its text is updated with the cause.

Out of scope: disabling the delete trigger while an answer is pending (changes the behaviour), other focus rules of the chat, the other mocked suites, the rest of TD-065.

## Capabilities

### New Capabilities
<!-- None. -->

### Modified Capabilities
- `frontend-student-chat`: a new requirement says that the arrival of an answer does not take the focus from a control the student has moved to.

## Impact

- Code (when implemented): `frontend/src/components/QuestionBox.tsx` and its tests, `frontend/e2e/student-chat.mocked.spec.ts` (one added test).
- Docs: `docs/technical-debt.md` (TD-068), possibly `docs/lessons-learned.md` (a focus move after an asynchronous result must check where the focus is).
- No dependency, API, backend or infrastructure change.
