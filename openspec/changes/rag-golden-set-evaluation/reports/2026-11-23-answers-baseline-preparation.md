# rag-golden-set-evaluation: preparation of the single answers run (2026-11-23)

No real call to Gemini was made. The ledger (`reports/real-request-ledger.json`) and `authorised_total` were not touched. Branch `feature/rag-answers-baseline-prep` from `main` 6a789a5; nothing committed.

## Owner's data (read in AI Studio) and what is still unknown
Free plan without billing; model `gemini-3.1-flash-lite`; 15 requests per minute, 250 000 tokens per minute, 500 requests per day. The documentation of Google does not publish these per-model values (they are shown only in AI Studio) and does not say whether a failed request counts against the quota. Historical consumption stays an estimate: 22 to 264 requests, 154 in the ledger, never confirmed.

## What was implemented (tool, cases and documents only)
1. **Every answer is kept**: `AnswerRecord` (case, kind, question, answer, valid markers, ranks and files that become the sources, fallback) in the Markdown and the JSON of the report; secrets are removed as in the rest of the report.
2. **Unsent cases are named**: a note lists the cases marked for the model that retrieved nothing.
3. **`inj-q-01` reformulated** (golden set `v0.2-draft`, README with the change): it starts with the question of `ans-ia01` and then gives the injection, so that it retrieves material and the model is called. In v0.1 it retrieved nothing and the prompt-leak check was never exercised. The other 75 cases are unchanged.
4. **Procedure** of the single run in `docs/development_guide.md`; design D15; spec requirements; TD-067.

## Evidence
- Tests first: `reports/_failing_run_answers_baseline_prep.txt`.
- Mutations: `reports/_mutations_answers_baseline_prep.txt`, 7 of 7 detected.
- **Dry run with the real embedder and the fake model** (`reports/2026-11-23-rag-evaluation-answers-FAKE-LLM-DRYRUN-6a789a5-dirty.md/.json`): 45 model calls (24 answerable, 8 follow-ups, 2 + 2 marker traps and 2 documents with injection, 6 unanswerable, 1 injection question); `inj-q-01` retrieved 5 chunks and was sent; unsent: `unans-03`, `unans-06`, `unans-09`, `unans-10`; 45 answers kept; no isolation violation; the test database was left empty. The fake model writes no markers, so the attribution numbers of that report mean nothing: it proves the count and the mechanics.

## Budget to authorise
| Item | Value |
|---|---|
| Requests expected | **45** (one attempt per call, no hidden retries) |
| Ceiling of the harness (`--max-calls`) | **50** |
| Time at 6 s of pause | about 5 to 7 minutes |
| Rate against the limits | about 10 per minute of 15; an estimate, not measured, of under 1 500 tokens per call (5 chunks of at most 100 tokens, a system prompt of 604 characters, the question and, for follow-ups, the history), so under 15 000 per minute of 250 000; 45 of 500 per day |
| `authorised_total` the ledger needs | **204** = 154 + 50 (the 154 is the historical estimate; it is not reset or corrected) |
| A second run | not included, and **refused by the ledger** under the same total even with requests left (rule one authorisation, one run; a different value is a new decision of the owner) |

## Independent review (2026-11-23): PASS WITH GAPS
No blocker. Major finding: the ledger does not enforce "one run only". First answered in the procedure; then, by the owner's decision of 2026-11-23, fixed in the tool: each run records the total it ran under and a second run under the same total is refused (design D16, task 3.3d). Minors fixed: the fake-model report now carries a banner that says it is not a baseline (the dry run was regenerated), the command block and the ledger path of the guide, the token estimate marked as an estimate, the wording of TD-067.
