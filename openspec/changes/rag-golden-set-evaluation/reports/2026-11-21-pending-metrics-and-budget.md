# rag-golden-set-evaluation: metrics that could not be completed, and the real-request budget

Date: 2026-11-21. No real call to Gemini was made after the first run (owner's decision of 2026-11-21: none until a reliable budget exists).

## 1. What was obtained and is kept

| Result | Source | Status |
|---|---|---|
| Retrieval baseline with the real embedder (Hit@1/3/5, MRR, refusal, unanswerable-passed, sweep of top-k and threshold, follow-ups apart, isolation, accepted passages inside one chunk) over all 76 cases | `2026-11-20-rag-evaluation-retrieval-8d028ce-dirty.md/.json` | **Complete** |
| Partial answers run with the real model (first version of the harness) | `2026-11-20-rag-evaluation-answers-PARTIAL-first-run.md/.json` | Kept as evidence, **superseded**: it predates the fixes and the corrected classification |

## 2. Metrics that are still missing (explicit register)

The first answers run reached the model for 44 of the 49 cases marked for it (the other 5 retrieved nothing above the threshold). It answered 22 and failed 22 (`LLMUnavailableError`, cause not recorded in that version).

| Metric (answers mode, real model) | Planned | Obtained in the partial run | Missing |
|---|---|---|---|
| Answerable questions: valid marker, fallback, wrong citation | 24 | 12 | 12 (and the 12 obtained used the old classification: a fallback was counted as a wrong citation) |
| Follow-ups: same metrics | 8 | 4 | 4 |
| Traps (marker in document, stale marker in history) and injection in a document: marker, stale/repeated, forbidden text | 6 | 3 | 3, plus the corrected "stale or repeated marker" and "not exercised" reports have never run with the real model |
| Unanswerable questions that reach the model: answers for human review | 6 reached the model | 3 (all three refused in words; reviewed) | 3 |
| Injection in the question: prompt-leak check | 1 | 0 (it retrieved nothing above the threshold, so the model was never called) | the check cannot be exercised with this question as written; needs a question that retrieves material |
| Corrected attribution semantics (fallback is not a wrong citation, stale markers) | all | none | all: the partial numbers must not be quoted as the baseline |

The answers of the 22 successful calls were not stored (only aggregates), so they cannot be merged with a later run: **a consistent baseline needs a full rerun of the cases that reach the model (about 44 requests)**.

## 3. Real-request consumption

| Quantity | Value | Basis |
|---|---|---|
| Logical calls made | 44 | harness counter, report header |
| Library attempts per call in that run | up to 6 | `langchain_google_genai` `max_retries` default 6 (`_common.py:428`); the application client was used, with retries on |
| Lower bound of real requests | 22 | only the answered calls, if the 22 failures never reached the network (event loop closed) |
| Midpoint estimate used to seed the ledger | 154 | 22 answered (one request each) + 22 failed x 6 attempts; answered calls may also have retried, so the truth is only bounded by 22 and 264 |
| Theoretical maximum | 264 | 44 x 6 |
| Authorised by the owner | 50 | 2026-11-20 |

Which end is true cannot be known from here: the container logs were removed with the throw-away containers and the provider's usage page is the only source. Retried requests answered with 429 normally do not consume quota but they are requests, so the authorisation may have been exceeded at the upper end. **Action for the owner:** read the usage of the API key in Google AI Studio for 2026-11-20 and tell the real number.

## 4. Need for a persistent control, and what was done

Needed: yes. The cap of the first version was per run, with no memory, and the first run showed that the number of logical calls is not the number of requests. Implemented (tool only, no productive service touched): a ledger file (`real-request-ledger.json`) with the total authorised by the owner and what was spent; `--ledger` is required with the real model; a run stops before its first call when it needs more than what is left; it adds its calls afterwards, also when it fails; the harness never raises the authorised total. The ledger starts **overspent (154 of 50)**, so no real run can start until the owner sets a new total. Limits: it records what the harness sends, not the provider's quota; it needs the file mounted writable in the container.

## 5. Estimated budget to complete the baseline

| Option | Real requests | Result | Comment |
|---|---|---|---|
| A. Repeat only the 22 failed cases (`--only`) | 22 | Half of the cases; cannot be merged with the discarded 22 answers | Not recommended: no consistent baseline |
| **B. Full rerun of the cases that reach the model** | **44** (49 at most) | Complete baseline with the corrected semantics, one attempt per call | Recommended |
| C. B plus a second pass on cases with failures | 44 + up to 10 | Allows retrying provider errors by hand | Only if the provider dashboard shows room |

Recommended new authorisation: **50 requests, new and separate from the earlier spending**, set in the ledger by the owner after reading the usage page (and fixing `spent` to the true figure or to a reset value of the owner's choosing); pacing 6 s (about 5 minutes); stop after two consecutive failures. The free tier quota per minute and per day for this model was not verified from here (not read from the provider).
