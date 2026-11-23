# Design

Follows `docs/backend-standards.md`; nothing here restates it. Updated after Explore (2026-11-20): the findings are listed first.

## Explore findings (what changed in this design)

| # | Finding (verified in the repository) | Consequence |
|---|---|---|
| E1 | `RAGService.prepare` (consent, enrollment, conversation, embedding, `find_similar`, threshold, history) and `generate`, plus `build_prompt` and `select_cited`, are importable and `RetrievedContext` is a plain dataclass | The harness calls them; it reimplements nothing (D1, D6) |
| E2 | `prepare` loads history from the database by `conversation_id` and only when some chunk passed the threshold; retrieval ignores history | Follow-up cases are seeded as stored conversations (D9) so the harness keeps working when `rag-retrieval-quality` makes retrieval history-aware |
| E3 | The CI backend job runs `pytest -m "not realmodel"` with `EMBEDDER_BACKEND=fake`/`LLM_BACKEND=fake` (`APP_ENV=test`); the real model lives only in the worker/backend images (`/opt/models`) | CI can prove mechanics only; real-embedder metrics are local, run in a container (D2, D8) |
| E4 | Compose mounts only `backend/app` into the backend container; a harness outside `app/` is not visible there | The local run copies or mounts the harness ad hoc (`docker compose run -v ...`, no compose change) (D10) |
| E5 | CI runs `mypy --strict app tests`; a new top-level directory would escape it | The harness lives in `backend/tests/evaluation/` (D1) |
| E6 | The spike material (60 passages, 3 subjects, 45 questions, `corpus_es.py`) already exists, written in Spanish and fictitious | It seeds the set instead of writing 60 new passages (D4) |
| E7 | Spike similarity: relevant median 0.556 (p10 0.425); irrelevant same-subject median 0.285 (p90 0.438); default threshold 0.3 | Expect unanswerable cases to pass the threshold; the model's own refusal matters, hence the human-review list (D6) |
| E8 | The `asistenteia_test` database exists next to the development one; `TEST_DATABASE_URL` is in `.env.test` and the guard is a naming convention (TD-013) | The harness adds its own refusal check and cleans up (D7) |
| E9 | `LLM_BACKEND=fake` is accepted only with `APP_ENV=test`; the fake answer carries no markers | In CI every answer is a fallback: the fixture proves counting, not quality |
| E10 | The backend image has the model and the Gemini client but not `langchain_text_splitters`; the host environment has the splitter but not the model | Real-embedder runs mount that pure-Python package from the host virtual environment into the throw-away container (D10) |
| E11 | Found by the first real run and the independent review (2026-11-20): the application's Gemini client retries on its own and one event loop per call broke the pooled connections (22 of 44 calls failed) | One attempt per call, one event loop for the whole answers loop, abort after two failures, hard ceiling of 50 requests (D12) |

## Decisions

### D1. Location and shape
`backend/tests/evaluation/` (Python package: case model, loader, metrics, classifier, runner, report writer, CLI `python -m tests.evaluation`) with data in `backend/tests/evaluation/golden_set/`. It sits with the existing test-support modules, is covered by `mypy --strict app tests` and `ruff`, and is not imported by `app`. Pytest tests for the harness are `tests/unit/test_evaluation_*.py` and `tests/integration/test_evaluation_harness.py`.

### D2. Modes
- `retrieval`: embedder (real locally, fake in CI) + test database, no model.
- `answers --llm fake`: adds prompt, fake model and citation selection (CI fixture; local smoke).
- `answers --llm gemini --allow-real-llm --max-calls N`: manual, free tier, fictitious data.
The real embedder is selected with the existing `EMBEDDER_BACKEND=local` setting and only works where the model exists.

### D3. Golden set format
`corpus/<subject>/*.md|txt`, `cases.json` validated by a Pydantic model, `VERSION`, `README.md`. A case: `id`, `kind`, `subject`, `student` (enrolled or not), `question`, `history` (earlier messages), `expected` = `no_material` or a list of `{filename, page|null, passage_contains}` (any one acceptable). Judging by substring is deterministic and independent of chunk boundaries and of any model.

### D4. Size and composition (proposal)
Seed: the 45 spike questions and 60 passages (3 subjects), rewritten as files with accepted passages. Added: ~10 unanswerable (plausible but absent), ~8 follow-ups, ~6 injection or marker traps (a document containing `[3]`, a history with a stale `[2]`), ~6 cross-subject or not-enrolled. About 75 cases, of which about 50 reach the model (answerable, follow-up, traps). Stated limit: written by the assistant and reviewed by the owner (one author, like TD-033); it measures regressions and relative improvement, not absolute quality on real courses.

### D5. Real course material is a later, approved step (decision for the owner)
Not part of this change: it needs the owner's decision on who provides it, the authors' consent and the pilot conditions (TD-003, TD-063, TD-064). The harness accepts a second golden set loaded from a path outside the repository.

### D6. Attribution judgement without an LLM judge
A cited chunk is "supporting" when it contains one of the case's `passage_contains` strings. Markers pointing to a chunk without an accepted passage are wrong citations; answers with no valid marker are fallbacks; markers copied from history or from a document (trap cases) are stale/repeated. Unanswerable cases that pass the threshold are listed with their full answers for a person to read; no automatic score (a refusal phrase heuristic would be fragile in Spanish). Limit: a correct citation of an unexpected valid passage counts as wrong, so each case lists every acceptable passage.

### D12. Real-model accounting (added after the review)
The library default retries failed requests, so one logical call could be several requests. The harness client is built with `max_retries=1` (one attempt; the library passes it as `HttpRetryOptions(attempts=1)`), records the class and HTTP status of every failure (never the message), spaces calls (`--pause-seconds`, default 6) and stops after two failures in a row. `--max-calls` cannot exceed 50. The whole answers loop runs in one event loop. A persistent ledger (`reports/real-request-ledger.json`, its directory mounted writable for the run; `--ledger`, required for the answers mode with the real model) holds `authorised_total` (only the owner edits it) and `spent` (the harness reserves the calls a run needs before its first request and settles the real number at the end, also for a failed run; a failure to settle is reported in the report, never raised over it). A run stops before its first call when it needs more than what is left. The first run is recorded conservatively: its library retries were on, so its real request count is unknown (lower bound 22 answered calls, conservative estimate 154 = 22 + 22 x 6, theoretical maximum 264) and the ledger starts overspent, which blocks further real runs until the owner decides a new authorised total, ideally after reading the provider's usage page. The ledger is an authorisation, not the provider's counter: the harness cannot see the real quota. The first run (before these fixes) made 44 logical calls with the library's retries on; the real number of requests is unknown.

### D13. Attribution semantics (corrected after the review)
A fallback lists every retrieved chunk but the model chose none, so it is a fallback and not a wrong citation; "wrong citation" is a marker chosen by the model for a chunk without an accepted passage; "stale or repeated" is a wrong marker that an earlier assistant message of the case or a retrieved chunk already contained. Cases without expected sources (refusals, free-form) are not part of the attribution shares. Traps whose target chunk was not retrieved are listed as not exercised.

### D14. Isolation semantics (corrected after the review)
A student enrolled in the subject may legitimately receive its chunks for any question (60% of the unanswerable questions pass the default threshold). Isolation therefore fails when a chunk of another subject is returned, or when a student without access (enrolled nowhere, or enrolled only in another subject) is not refused.

### D7. Isolation and cleanup
The CLI refuses to start unless the database name is the isolated test database and differs from the application database (checked by the harness itself, in addition to the existing guard), creates its synthetic users (student with the current consent version, enrolled and not enrolled) and subjects, and deletes them at the end or on failure (try/finally). No development data is read or written.

### D8. CI
One integration test runs a fixture of about 6 cases over 2 tiny documents with the fake embedder and fake model, inside the existing `tests/integration` run (needs the existing test database, no new job). It fails when the harness breaks, never because a metric moved. No Gemini, no model download.

### D9. Follow-ups as stored conversations
For a follow-up case the runner stores the earlier messages as a conversation of the synthetic student (through the repositories) and calls `prepare` with its id, as the endpoint does. If a later change makes retrieval use the history, the harness measures it unchanged.

### D10. Running it locally (operational)
Real-embedder runs go in the backend or worker container (model at `/opt/models`), with the harness provided ad hoc (`docker compose run --rm -v ./backend/tests/evaluation:/app/tests/evaluation ...`) and the test database URL taken from `.env.test`; this changes no compose file. The run prints the mode, embedder, model, set version and the call count before any call. Credentials never reach the report (TD-054 describes the existing risks).

### D11. Reports
Markdown plus JSON under `openspec/changes/<change>/reports/`; later changes append comparable runs with the same header. The header repeats set version, git revision, embedder, model, settings and mode. Fictitious data only; no secrets.

## Risks

| Risk | Mitigation |
|---|---|
| The set is too easy and hides weaknesses | Hard negatives, paraphrases, follow-ups and traps; add a case for every future finding |
| Overfitting thresholds to the set | Report the sweep, not only the best row; keep a hold-out part not used to choose settings |
| Free-tier quota or model change makes manual runs flaky | Call cap, bounded retries, model name in the report |
| The harness drifts from production | It calls the production functions (E1); a test fails if it stops doing so |
| Fixture mistaken for real data | README and report header state it is fictitious |
| Real-embedder numbers differ slightly across machines | Report rank-based metrics and the image/model revision; compare runs from the same image |

## Decisions that need the owner's approval

1. **D4/D5**: size, language and authorship of the set, and when (if ever) real material is used. Recommended: approve the seeded set of about 75 cases now.
2. **D1 location**: `backend/tests/evaluation/` (recommended, covered by mypy/ruff) versus a new top-level directory.
3. **D10**: running the harness in the backend container with an ad hoc mount against `asistenteia_test`, and about 50 free-tier Gemini calls per manual run on fictitious data (consistent with the standing authorization; confirm for the first run).

### D15. Preparation of the single answers run (2026-11-22)
The owner confirmed the account data (free plan, no billing, 15 requests per minute, 250 000 tokens per minute and 500 requests per day for `gemini-3.1-flash-lite`, read in AI Studio) and approved: keep every answer of the run in the report (`AnswerRecord`: question, answer, markers, ranks, files, fallback), reformulate `inj-q-01` so that it retrieves material (it now starts with the question of `ans-ia01` and then gives the instruction; set `v0.2-draft`, the other 75 cases unchanged), list the model-marked cases that retrieved nothing, and prepare **one** controlled run of at most 50 real requests without running it and without touching `authorised_total`. A dry run with the real embedder and the **fake** model (no Gemini) gave 45 model calls: 24 answerable, 8 follow-ups, 6 traps and documents with injection, 6 unanswerable and the injection question; 4 unanswerable cases retrieve nothing and are not sent. The results of v0.1 keep their own version and are not comparable with v0.2 without saying so.

### D16. One authorisation, one run (2026-11-23)
The review of the preparation found that the ledger bounded the total but not the number of runs: after an aborted run the rest of the 50 stayed available and a second run could start only by the operator's discipline. Now `reserve_run` records, in the new entry, the `authorised_total` it ran under, and `require_budget` (called by the CLI before it connects and by the runner before the first call) refuses a run whose current `authorised_total` was already used by an entry, even with room left. The owner gives a new authorisation by editing the number; the harness never writes it and never rewrites old entries (the entry of 2026-11-20 has no total and does not block anything). Consequence for the procedure: the number to set for the run is any value not used before that leaves room for the 50 (for example 204); setting the same value again for a second run is refused, so a second run needs a different value and a new decision.
