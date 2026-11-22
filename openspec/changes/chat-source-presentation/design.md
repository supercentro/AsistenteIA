# Design

Follows `docs/backend-standards.md` and `docs/frontend-standards.md`. Written after Explore (2026-11-22). Nothing is implemented. Reuses `rag-source-attribution` (first slice) and the evaluation harness.

## Explore findings (verified in the repository)

| # | Finding | Consequence |
|---|---|---|
| E1 | The API returns `sources` with `chunk_id`, `document_id`, `filename`, `page_number`, `rank`, `snippet` for the chat answer (`endpoints/chat.py`) and for each message of the history (`endpoints/conversations.py`). Nothing says whether the sources were cited or are the fallback "all retrieved" | A flag is needed; the data to decide it already exists |
| E2 | `message_sources` stores `rank`, `score`, filename, page and chunk; the stored answer text keeps its `[n]` markers. In the fallback every retrieved rank is stored; in the cited case only the cited ranks | The flag can be **derived** from the stored answer and ranks, with no column and no migration (the migrations, grants and privilege matrix gates are avoided) |
| E3 | Derivation rule: with `N` the highest stored rank, the sources are *cited* iff `cited_ranks(content, N)` equals the set of stored ranks; otherwise *retrieved*. It holds for the cited case (the markers inside `1..N` are exactly the stored ranks), for the fallback (no marker inside `1..N`) and for **old answers written before the first slice** (an old fallback caused by `[1, 2]` has all ranks stored while the new reader finds only `{1, 2}`: not equal, so *retrieved*) | A property test must check that the live answer (where `select_cited` knows it fell back) and the derivation of the stored data agree. **Checked in Explore** with the production functions (`select_cited`, `cited_ranks`) on 20 000 generated answers (markers, lists, ranges, invalid and spaced markers, 1 to 6 chunks): 0 mismatches; the old-fallback case gives `retrieved`. **Documented limit** (independent review): an answer stored before the list form was read, whose only markers were a list covering every retrieved rank (for example `[1, 2]` with 2 chunks), is derived as `cited`; the set of ranks is the same either way, so nothing shown changes |
| E4 | The frontend shows each source as file name, page and a collapsible snippet under "Material consultado", with a neutral note; **no rank number** is shown while the answer text shows `[n]`; the label and the note are in `strings.es.ts` | The marker cannot be matched with its source today (pre-existing UX gap found in Explore of slice 1, E6) |
| E5 | The spec "Sources are shown as provided, without guarantees" forbids stating or implying that a source proves a statement; the answer text is plain text, never markup | The new labels must say "cited by the answer" (a fact about the text), never "supports" or "confirms" |
| E6 | The fallback also covers an answer that refuses in words; such an answer lists every retrieved chunk. Provisional partial-run numbers (not a baseline, superseded): 33 % of the answerable questions and all 3 unanswerable ones that reached the model fell back | Showing retrieved-only fragments apart and collapsed reduces the impression that a refusal is backed by sources, without hiding what was retrieved (the persisted-sources rule stays) |
| E7 | A marker pointing outside the stored ranks (for example `[7]` with sources 1 to 3) stays as text; with a flag `cited` there is at least one valid marker, with `retrieved` none | The interface does not try to repair the text; the group label tells the reader which case applies |
| E8 | Files touched in the frontend: `SourcesBlock.tsx`, `MessageBubble.tsx`, `strings.es.ts`, the chat tests, `e2e/student-chat.mocked.spec.ts` and `student-chat.real-backend.spec.ts` | Small, contained |
| E9 | The CI gate `check:api-types` regenerates the types from `docs/api-spec.yml`; the contract tests read `docs/api-spec.yml` | The additive field needs the docs, the schemas and the generated file to change together |

## Alternatives

| | Alternative | Pros | Cons |
|---|---|---|---|
| A | **Derive** `attribution` and add it to the API (chosen) | No migration, no grant change, works for old messages | The rule must be shared and tested (live and derived agree) |
| B | Persist a column `attribution` in `message_sources` or `messages` | Explicit, cheap to read | Migration, role grants, privilege matrix and rollback; old rows need a backfill |
| C | No API change: the frontend derives the flag from the text and the ranks | No contract change | Duplicates the backend marker reader in TypeScript; drift between the two readers |
| D | Show only rank numbers on the sources, no flag | Smallest | Does not distinguish retrieved from cited; the user explicitly asks for it |
| E | Turn the markers of the text into links to the sources | Best reading experience | Needs a client-side reader of markers (drift risk), a11y of inline links, more tests; optional later |

Recommendation: **A** with the UI of D-S3, and E left out of this slice.

## Proposed contract (additive)

`attribution`: string enum `cited | retrieved`, nullable, **not required**, on `ChatResponse` and on `Message`; null when the message has no sources (a question, or a "no material" answer). `docs/api-spec.yml` documents it; `Source` keeps its fields. Clients that ignore it keep working: they see the same sources as today.

## Proposed interface (Spanish copy to approve, in `strings.es.ts`)

- `cited`: label "Material citado en la respuesta"; each item starts with its marker, `[2]`, so the reader matches it with the `[2]` of the text; the neutral note stays.
- `retrieved`: a collapsed detail "Material recuperado (la respuesta no indica cuáles fragmentos usó)"; the items show file, page and snippet but no marker number; the neutral note stays.
- No text says that a source supports, proves or guarantees the answer.

## Risks and regression checks

- **Live and derived flags must agree**: property test over generated answers and chunk counts.
- **Old messages**: the derivation rule of E3 is tested with an answer that only the new reader recognises.
- **Contract drift**: the three places (docs, schemas, generated types) change in one commit; `check:api-types` and the contract tests are the gate.
- **Wording**: the spec scenario of neutral wording gets a test on the new labels.
- **Accessibility**: the collapsed group is a native `<details>`; the markers are text, not colour only; axe checks of the chat tests stay.
- **Stale marker text** in an old answer (E7) is not repaired; documented.
- Real-model effect: not measured (baseline 3.3b pending); only mechanics are proven. TD-062 stays open.

## Decisions pending the owner

- **D-S1**: approve alternative A (derived, additive, no migration).
- **D-S2**: confirm the field name `attribution` and the values `cited` and `retrieved`, optional and nullable.
- **D-S3**: approve the interface above and its Spanish copy (or give other wording).
- **D-S4**: keep the retrieved-only fragments visible but collapsed (recommended), or hide them.
- **D-S5**: markers as links in the text: not in this slice (recommended) or later as its own change.
- **D-S6**: whether old messages are classified by derivation (recommended) or left without the flag.

## Implementation notes (2026-11-22)

- `attribution_of(content, ranks)` in `prompt_builder.py` next to `select_cited`; `ChatResponse.attribution` and `MessageResponse.attribution` (`Literal["cited", "retrieved"] | None`, default null); both endpoints compute it from the content and the stored ranks. No model, repository, migration, grant or configuration change.
- The cached message of the live answer (`useAskQuestion`) copies the flag, otherwise the first render of an answer would show retrieved material until the history is refetched.
- A response without the field (an older server) or with null is shown as retrieved material, as the spec says.
- `[n]` markers are shown only for cited sources; the retrieved block is a native `<details>` (keyboard operable) labelled by its `<summary>`.
- Not done by decision D-S5: links from the markers in the text.
