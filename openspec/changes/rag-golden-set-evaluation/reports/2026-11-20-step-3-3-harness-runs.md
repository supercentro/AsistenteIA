# Step 3.3 Report - Running the harness for real

- Date: 2026-11-20
- Change: rag-golden-set-evaluation
- Environment: the existing local stack; harness run in a throw-away container of the `backend` service (`docker compose run --rm --no-deps`) with `backend/tests`, `.env.test` and the `langchain_text_splitters` package mounted for the run; database `asistenteia_test` only; no compose file, image, dependency or volume changed.

## 1. Retrieval mode, real embedding model, no Gemini
Golden set v0.1-draft (76 fictitious cases), revision `8d028ce-dirty`. Reports: `2026-11-20-rag-evaluation-retrieval-8d028ce-dirty.md` / `.json`. No problems, no isolation violation, every student without access refused, every accepted passage lies inside a single chunk.

| Group (top-k 5, threshold 0.3 = production default) | n | Hit@1 | Hit@3 | Hit@5 | MRR | refused |
|---|---|---|---|---|---|---|
| Self-contained questions | 45 | 69 % | 93 % | 93 % | 0.793 | 0 % |
| Follow-ups | 8 | 38 % | 62 % | 75 % | 0.531 | 0 % |
| Traps with expected sources | 6 | 100 % | 100 % | 100 % | 1.000 | 0 % |

Unanswerable questions that pass the threshold: **60 %** at 0.3, 40 % at 0.4, 10 % at 0.5 (answerable questions refused: 0 %, 4 %, 27 %). Reading: the result reproduces the spike (Hit@3 0.889, MRR 0.798) and confirms the expectation of the Explore: the default threshold barely refuses off-topic questions, so the model's own refusal matters; follow-ups retrieve worse because retrieval ignores the conversation. The three answerable questions that never reach Hit@5 are real retrieval misses (the passage check found no boundary artefact).

## 2. Answers mode, real model (partial, free tier, fictitious data)
`2026-11-20-rag-evaluation-answers-PARTIAL-first-run.md`. 44 logical calls were made; **22 failed** with `LLMUnavailableError` (cause not recorded in that first version), the rest returned answers. The independent review found the probable cause: one `asyncio.run` per case on a client with pooled connections; the library's own retries were also on, so the real number of requests is unknown and may exceed 44. Valid answers of that run, for what they are worth: answerable 8 of 12 with a valid marker (4 fallbacks), follow-ups 3 of 4, traps 3 of 3, and the 3 unanswerable questions that reached the model were refused in words. These numbers are **provisional**: the run predates the fixes and the corrected classification.

After the fixes (one attempt per call, one event loop, two-failure abort, ceiling of 50, pacing, error kinds recorded) **no further real call was made**: the authorised budget of 50 requests may be nearly spent and a new run needs the owner's confirmation (TD-067). Task 3.3 therefore stays open for the answers baseline.

## 3. Accounting
Real Gemini requests in this change: 44 logical calls (first answers run); 0 since. Development database and test database state: see step 3.2.
