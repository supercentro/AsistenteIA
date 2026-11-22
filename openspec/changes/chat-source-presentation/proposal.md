# Proposal

## Why

Second slice of `rag-source-attribution` (TD-062). The first slice (merged, PR #23) made the citation markers reliable inside the prompt, but the student still cannot tell two things apart: sources the assistant **cited** with a marker, and fragments that were only **retrieved** because the answer carried no valid marker (the stored fallback "every retrieved chunk"). The chat also shows the marker `[2]` in the answer text while the sources list shows no number, so the reader cannot match them. Provisional evidence of the partial real-model run (not a baseline): the fallback was frequent (33 % of the answerable questions and all 3 unanswerable ones that reached the model), so an answer that says "I have no information" can appear with sources under it.

## What Changes

Proposed after Explore (2026-11-22); **not implemented** and awaiting the owner's decisions (`design.md`, D-S1 to D-S6):

- **Additive API field** `attribution` (`cited` or `retrieved`) on the chat answer and on each message of the history, derived from the stored answer and its stored sources (no migration, no new column). It is absent or null when there are no sources.
- **Student chat**: a source cited by the answer shows its marker number (`[2]`) so the marker of the text can be matched with it; fragments that were only retrieved are shown apart, collapsed, under a neutral label that says the answer did not indicate which fragments it used.
- Unchanged: the persisted sources of every answer, the rank, the snippet, the fallback rule of the first slice, the neutral wording about guarantees, the retrieval, the prompt and the model.
- Out of scope: turning the markers of the text into links (optional, D-S5), retrieval quality, a model that judges citations, any real-model measurement (task 3.3b of `rag-golden-set-evaluation`).

## Capabilities

### New Capabilities
<!-- None. -->

### Modified Capabilities
- `rag-chat`: the answer and the history say whether their sources were cited or only retrieved.
- `frontend-student-chat`: the requirement "Sources are shown as provided, without guarantees" gains the distinction and the marker numbers.

## Impact

- Backend: `app/schemas/chat.py`, `app/schemas/conversation.py`, `app/api/v1/endpoints/chat.py` and `conversations.py`, one pure helper next to `select_cited`. No model, repository, migration, grant or configuration change.
- Contract: `docs/api-spec.yml` (additive, optional field) and the generated `frontend/src/types/api.generated.ts` (gate `check:api-types`).
- Frontend: `SourcesBlock.tsx`, `MessageBubble.tsx`, the strings file (Spanish copy in one place), tests and e2e of the chat.
- Existing clients: the only client is this frontend; an unknown additive field is ignored by any tolerant client.
