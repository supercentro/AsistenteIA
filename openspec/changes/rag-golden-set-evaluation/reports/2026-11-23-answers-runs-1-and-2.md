# rag-golden-set-evaluation: the two real runs of 2026-11-23 (task 3.3b stays open)

Model `gemini-3.1-flash-lite` (free plan, no billing), golden set `v0.2-draft` (76 fictitious cases, 45 of them reach the model), real embedder, top-k 5, threshold 0.3, one attempt per call, pause of 6 s, abort after two failed calls in a row, only the isolated database `asistenteia_test` (left empty). **These are partial results and not a baseline.**

## Conditions of each run
| | Run 1 | Run 2 |
|---|---|---|
| Authorisation | `authorised_total` 204 | `authorised_total` 206 (a different value, as the ledger rule requires) |
| Cases sent | the 45 that reach the model | only the 41 not answered by run 1 (`--only`) |
| Time (UTC) | 12:39 to 12:43 | 12:57 to 13:01 |
| Report | `reports/2026-11-23-rag-evaluation-answers-aa8fe37-dirty-RUN1-503.md/.json` | `reports/2026-11-23-rag-evaluation-answers-aa8fe37-dirty-run2.md/.json` |
| Checks before | no other consumer of the key found (the last chat of the development backend was on the previous quota day); the limits of the project were the owner's observations (15 requests per minute, 250 000 tokens per minute, 500 requests per day); the live usage of AI Studio could not be read from here | same; the public status pages showed no incident (the AI Studio page is a dynamic shell without data; the incident list of Google Cloud had no recent entries and is not proof of health) |

## Results
| | Run 1 | Run 2 | Together |
|---|---|---|---|
| Requests made (one attempt each) | 7 | 11 | **18** |
| Answered | 4 | 6 | **10 of 45** (22 %) |
| Failed | 3 (`503` x3) | 5 (`503` x4, `504` x1) | 8 (44 % of the requests) |
| Stopped by the rule of two failures in a row | yes | yes | |
| Answers with a valid marker / fell back | 3 / 1 | 5 / 1 | 8 / 2 |
| Wrong citation, repeated marker, forbidden text, prompt leak | 0 | 0 | 0 |

All ten answers are `answerable` cases, in the order of the set (`ans-ia02`, `ia03`, `ia04`, `ia06`, `ia07`, `ia09`, `bd02`, `bd04`, `bd06`, `bd07`). The two that fell back are `ans-ia06` (a retrieval miss already known: the model said that the material has no information, and the answer still lists the five retrieved chunks, TD-062) and `ans-bd04`. `ans-ia01` and `ans-ia08` failed in both runs.

Retrieval and refusal (complete in both reports, over their cases): self-contained questions Hit@1 69 %, Hit@3 and Hit@5 93 %, MRR 0.793; follow-ups Hit@5 75 %; 6 of 10 unanswerable questions pass the threshold. No isolation violation.

## Ledger and consumption

**The ledger file is not published with these reports.** `real-request-ledger.json` is the owner's local record of her authorisations; the version in the repository keeps the values of 2026-11-21 (`authorised_total` 50, `spent` 154, one entry) and the local file holds what follows, so that the consumption stays traceable from this document:

| Entry | Date | Requests recorded | `authorised_total` it ran under |
|---|---|---|---|
| 1 (historical) | 2026-11-20 | 44 logical calls, **estimated** 154 real requests, never confirmed | none (before the rule) |
| 2 (run 1) | 2026-11-23 | 7 | 204 |
| 3 (run 2) | 2026-11-23 | 11 | 206 |

Local totals: `authorised_total` 206, `spent` 172 = 154 estimated + 18 counted by the harness.
`authorised_total` 206, `spent` **172** = 154 historical (an estimate, never confirmed) + 7 + 11 requests counted by the harness (one attempt per call). The rule "one authorisation, one run" refuses a third run under 206 although 34 requests remain by arithmetic, and the run under 204 can not be repeated either. Whether a `503` or a `504` counts against the quota of the provider is not stated by its documentation.

## Limits and decision
- The errors are the provider's (`503` unavailable and `504` timeout), about 44 % of the requests in both runs, not a quota error (it would be `429`) and no billing is involved. They were persistent in the two runs, separated by 15 minutes.
- The answers of the first ten cases say nothing about follow-ups, traps, injection, unanswerable questions or the other cases: **35 of the 45 cases have no answer**. A baseline from 22 % of the cases that are all `answerable` would be misleading, so none is consolidated and the two reports are kept apart.
- No third run was made. The alternatives below need the owner's decision and a new `authorised_total`.

## Alternatives (not applied)
1. Try again for the 35 pending cases at another time of the day, with a new authorisation (for example `authorised_total` 210 = 172 + 38) and `--only` with the pending ids; the results of the runs would still be reported apart.
2. Let the harness wait and retry a `503` or `504` once (the owner excluded retries for these runs); each retry is a request and must be counted in the budget.
3. Run in smaller batches (each needs its own authorisation under the new rule).
4. Use a paid tier of the project (billing, the owner's decision, not recommended before the others).
5. Change the model: not comparable with the application, not recommended.
