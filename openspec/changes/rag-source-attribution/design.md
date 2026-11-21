# Design

Follows `docs/backend-standards.md` and `docs/frontend-standards.md`. Written after Explore (2026-11-21). Nothing is implemented.

## Explore findings (verified in the repository)

| # | Finding | Consequence |
|---|---|---|
| E1 | `select_cited(answer, n)` keeps the valid `[n]` markers (regex `\[(\d{1,3})\]`) and, with none, returns every rank (`prompt_builder.py`). `_write_turn` stores those ranks as `message_sources` and returns them | The whole behaviour lives in one pure function plus `build_prompt`; both are covered by the harness |
| E2 | `_load_history` replays stored assistant answers unchanged, markers included, and `build_prompt` only neutralises CONTEXT/SYSTEM tags in them. The numbering restarts at `[1]` each turn | A model that copies `[2]` from an old answer can name a different chunk this turn. Confirmed by reading, not yet measured with a real model |
| E3 | Chunk text goes into the prompt after `neutralize_delimiters`; a document line such as `[3]` is kept as is | The model can repeat it; trap cases exist in the golden set (2 marker traps, 2 document traps) |
| E4 | The pattern accepts only `[n]`. A form such as `[1, 2]` is not read; `[1][2]` is | **Hypothesis**: some of the fallbacks come from `[1, 2]`. Not verified: the answers of the partial run were not stored |
| E5 | The fallback also applies to a refusal in words ("no tengo informacion"): the answer then lists every retrieved chunk as its sources | In the partial run all 3 unanswerable answers that reached the model fell back (provisional). A student can see sources under an answer that says it has no information |
| E6 | The student chat shows each source as filename, page and snippet, with **no rank number**, while the answer text still shows `[2]` | The marker in the text cannot be matched to a source by the reader. Pre-existing UX gap found now; outside this change unless the owner includes it |
| E7 | `api-spec.yml` documents `rank` and that an answer with no valid marker lists every retrieved chunk; base standards 9.5 and the spec "Every assistant answer persists its source chunks" require traceable citations | Dropping the sources on a fallback (R-D4 option 1) would contradict a MUST and the spec; it needs an explicit decision |
| E8 | Provisional numbers of the partial real run (superseded, 44 calls, not a baseline): answerable 12 answered, 67 % valid marker and 33 % fallback; follow-ups 4 answered, 25 % fallback; 7 cases with a source lacking every accepted passage | Order of magnitude only: the fallback is common, so R-D4 matters. Do not quote them as results |
| E9 | The first measurement of 2026-11-17 (17 answers with material, 17 with a valid marker, none fell back) differs from E8 | Two small samples disagree: the target cannot be set before the full baseline |
| E10 | The harness already reports valid marker, fallback, wrong marker, stale marker, forbidden text and prompt leak per case, with a mutation-tested classifier | Acceptance reuses it; no new evaluation tool is needed |

## Alternatives

| | Alternative | Pros | Cons | Contract change |
|---|---|---|---|---|
| A | Renumber or strip the markers of replayed history and neutralise `[n]` inside chunk text; accept `[1, 2]` | Small pure functions, deterministic tests with the fake model, no API or UI change | Does not help a model that cites the wrong block or no block; the effect on a real model is unmeasured | No |
| B | A plus an `attribution` field (`cited` / `retrieved`) and a flag in the sources block | Honest about the fallback; keeps the MUST of persisted sources | Additive API change, frontend change, copy to approve | Yes (additive) |
| C | Drop the sources when no valid marker exists | Simplest message | Violates the persisted-sources rule and the spec; hides what was retrieved | Yes (breaking semantics) |
| D | Ask the model for structured output with the cited ranks | Strongest signal | Changes the LLM service interface and prompt, more risk, needs the real model to evaluate | Possibly |
| E | Verify each cited chunk against the sentence (overlap or a second model) | Catches unsupported markers | New heuristic or an extra model call (cost, latency, TD-067 budget); an evaluator that itself needs evaluating | No |

Recommendation: **A as slice 1, B as slice 2**, each its own pull request. C is rejected unless the owner changes the standard. D and E are later options, to be reconsidered with the real-model baseline.

## Decisions pending the owner

- **D-A1**: approve slice 1 (alternative A) as the content of this change, with slice 2 as a second change or a second phase.
- **D-A2 (R-D4)**: what to show when no valid marker exists: keep all retrieved chunks silently (today), keep them flagged (B, recommended) or drop them (C, rejected by E7).
- **D-A3**: accept `[1, 2]` and `[1][2]` as multiple citations (recommended); accept ranges such as `[1-3]` (recommended not: ambiguous).
- **D-A4**: whether the missing rank label in the student chat (E6) joins slice 2 or becomes its own small frontend change.
- **D-A5**: whether refusals in words keep their sources (E5); depends on D-A2 and on `rag-retrieval-quality`.
- **D-A6**: the acceptance target. It cannot be set from E8/E9; it needs the real-model baseline (3.3b). Slice 1 can be implemented and tested with the fake model but cannot claim to close TD-062.

## Risks and regression checks

- A prompt or marker change can shift real-model behaviour: compare against the baseline before merging (blocked by 3.3b); until then only mechanics are proven.
- Stripping old markers must not alter the stored answer or the history shown to the student: only the prompt copy changes. Test with an assertion on the stored message.
- Neutralising `[n]` in chunk text must not change the snippet shown to the student (snippets come from the stored chunk, not from the prompt copy).
- Existing guards stay: delimiter neutralisation, subject isolation, the controlled no-material answer, persisted sources on every answer.
- No schema migration in slice 1; slice 2 can derive the flag without a column (a stored column would need a migration and an explicit decision).

## Reuse

`backend/tests/evaluation/` (cases, `classify_answer`, runner with the fake and the real model), roadmap decisions R-D4 and R-D2, TD-062, TD-067.
