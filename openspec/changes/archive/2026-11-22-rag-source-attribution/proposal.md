# Proposal

## Why

The citation markers (`[n]`) of a chat answer decide which chunks are stored and shown as its sources (`select_cited`). Four known ways make a source unreliable (TD-062): a marker the answer does not rely on, an answer with no valid marker that lists every retrieved chunk, a stored answer replayed as history whose old `[2]` collides with the new numbering that restarts at `[1]`, and a `[3]` copied from a document. The evaluation harness (`rag-golden-set-evaluation`, merged in #22) can now measure these cases, and the roadmap schedules this change as step 1b. Not yet measurable: the real-model baseline is partial (task 3.3b, TD-067), so the effect on a real model cannot be quantified before and after.

## What Changes

Approved by the owner on 2026-11-21: slice 1 only (D-A1, D-A3). The plan (decisions in `design.md`):

- **Slice 1, backend only, no contract change**: stop markers from other turns and from documents being read as citations of the current turn, and accept the common forms of one citation (for example `[1, 2]`). Every stored answer, response field and error stays as today.
- **Slice 2, contract change (needs approval R-D4)**: say in the response whether the sources were cited by the model or are only the retrieved chunks (`attribution`), and show it in the student chat.
- Out of scope: retrieval quality (`rag-retrieval-quality`), a second model that judges citations, structured model output, real student data.

## Capabilities

### New Capabilities
<!-- None. -->

### Modified Capabilities
- `rag-chat`: the requirement "The sources of an answer are the chunks it cites" gains the accepted marker forms (`[n]`, `[n, m]`, `[n][m]`; no ranges), and a new requirement says that markers of the history, of documents and of filenames are neutralised in the prompt. The attribution flag and `frontend-student-chat` belong to the second change.

## Impact

- Code (when implemented): `backend/app/services/prompt_builder.py` (slice 1), `rag_service.py` and the schemas (slice 2), `docs/api-spec.yml` (slice 2, additive field), `frontend/src/components/SourcesBlock.tsx` and its copy (slice 2).
- Evidence to reuse: the evaluation harness (`classify_answer`, stale markers, the 11 trap and injection cases) as the acceptance measure; its fake model proves mechanics only.
- Dependencies: no new library. Real-model measurement waits for the owner's decision on the Gemini budget (TD-067).
