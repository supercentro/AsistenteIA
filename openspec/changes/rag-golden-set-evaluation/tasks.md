# Tasks

> Approved by the owner on 2026-11-20 (about 75 fictitious cases pending the owner's review, `backend/tests/evaluation/`, at most 50 real free-tier requests). Follows `docs/openspec-tasks-mandatory-steps.md`. Backend tooling change; no frontend, contract, schema, dependency or `app/` change.

## 0. Branch

- [x] 0.1 Step 0: create the branch `feature/rag-golden-set-evaluation` from `main` before any code change. Merge only through a Pull Request. [branch `feature/rag-golden-set-evaluation` from `main` 8d028ce]

## 1. Tests first (pytest; Gemini is never called, the real embedding model is never loaded)

- [x] 1.1 Case loader tests: a complete case loads; a case without kind, question or expected outcome fails naming the case; duplicate ids fail; every accepted passage exists in its corpus file; the set version is read [done, see reports/2026-11-20-tdd-and-mutation-evidence.md]
- [x] 1.2 Metric tests on hand-made rankings: Hit@k, MRR, refused answerable share, unanswerable-passed share, the sweep rows with the default marked, follow-ups reported apart [done]
- [x] 1.3 Attribution classifier tests with fake answers and the production `select_cited`: valid marker, no marker (fallback), marker out of range, stale marker copied from history, marker repeated from a document, wrong citation against `passage_contains`, unanswerable cases listed for human review [done]
- [x] 1.4 Production path test: the runner reaches the chunks, the prompt and the sources only through `RAGService.prepare`/`generate`, `build_prompt` and `select_cited` (a test fails if the runner computes them itself) [done]
- [x] 1.5 Guard tests: the real model is not called without the explicit flag; the run stops before the first call when the cap is exceeded and prints the count; the API key and database URL never appear in output or report; the CLI refuses a database that is not the isolated test database and writes nothing [done]
- [x] 1.6 Isolation tests: a cross-subject case that retrieves a chunk fails the run; a not-enrolled student retrieves nothing [done]
- [x] 1.7 Cleanup test: after a run and after a failed run no synthetic user, subject, document or conversation remains [done]
- [x] 1.8 Determinism test: two runs with the fake embedder give identical metrics [done]
- [x] 1.9 Integration test `tests/integration/test_evaluation_harness.py`: fixture of about 6 cases, fake embedder and fake model, through the existing test database; it passes in the CI job and does not load the model [done]
- [x] 1.10 Run the new tests before any implementation and record the failing run (command and failure summary) in the change report. [5 collection errors before any code, then the later groups; reports/_failing_run.txt]

## 2. Implementation (backend tooling only)

- [x] 2.1 `backend/tests/evaluation/`: case model, loader, metrics, attribution classifier, runner on the production functions, report writer (Markdown and JSON), CLI with the three modes [done]
- [x] 2.2 Golden set: corpus files from the spike material, `cases.json` (about 75 cases, 3 subjects), `VERSION`, README stating that the content is fictitious and who wrote it [done, 76 cases pending the owner's review]
- [x] 2.3 Isolation and cleanup (own database check, synthetic users with current consent, try/finally removal) [done]
- [x] 2.4 Real-model mode: `--allow-real-llm`, `--max-calls`, count announced, bounded retries, no secret in output [done, one attempt per call, ceiling of 50]
- [x] 2.5 Mutation checks (temporarily break each guarded behaviour and show a test fails): runner computes chunks itself, cross-subject leak, missing cap, a metric off by one, API key printed, database guard removed, cleanup removed [25 of 25 detected, reports/_mutations.txt]
- [x] 2.6 Lint, format and `mypy --strict app tests` clean (the harness is under `tests/`) [ruff, ruff format, mypy --strict clean]

## 3. Verification

- [x] 3.1 Step N: review and update existing unit tests [done]
- [x] 3.2 Step N+1: run unit tests and verify database state (development database untouched; test database clean afterwards); report in `reports/` [reports/2026-11-20-step-3-2-unit-test-and-db-verification.md]
- [x] 3.3 Step N+2 (retrieval): run the harness for real inside the backend container (D10), retrieval mode with the real embedder over the full set; baseline report with the sweep of threshold and top-k and the numbers for TD-033 [reports/2026-11-20-rag-evaluation-retrieval-8d028ce-dirty.md]
- [x] 3.3c Preparation of the single answers run (2026-11-23, no real call, `authorised_total` untouched): all answers kept in the report, `inj-q-01` reformulated (set `v0.2-draft`), unsent model-marked cases listed, dry run with the real embedder and the fake model (45 calls expected), tests first, 7 of 7 mutations detected, independent review, the controlled-run procedure in `docs/development_guide.md` [reports/2026-11-23-answers-baseline-preparation.md]
- [x] 3.3d One authorisation covers one run (the owner approved it on 2026-11-23, review finding of 3.3c): the ledger records the total each run ran under and refuses a second run under the same total; the history and `authorised_total` are not touched; tests first, 5 of 5 mutations of the rule detected (the last five lines of `reports/_mutations_answers_baseline_prep.txt`), odd ledgers refused cleanly
- [ ] 3.3b Step N+2 (answers, **BLOCKED by the availability of the provider**, still open after two real runs on 2026-11-23): 18 requests were made (7 + 11), 10 of the 45 cases were answered (all `answerable`), 8 requests failed with `503` and `504` of the provider, each run stopped by the rule of two failures in a row; no baseline is consolidated because 35 of the 45 cases have no answer. Authorisations 204 and 206 are used; the ledger says `spent` 172 (154 estimated + 18) and refuses a third run under the same totals. A new run needs the owner's decision and a new `authorised_total` [reports/2026-11-23-answers-runs-1-and-2.md]
- [x] 3.4 Step N+3: no user-facing flow, so no browser run; record that in the report [no user-facing flow: no browser run]
- [x] 3.5 Step N+4: update documentation: `docs/development_guide.md` (how to run the harness), `docs/backend-standards.md` (evaluation rule, linked), `docs/technical-debt.md` (evidence for TD-033 and TD-062, still open), `docs/roadmap.md` (baseline numbers) [development_guide, backend-standards, technical-debt (TD-033, TD-062, new TD-067), roadmap]
- [x] 3.6 Independent review (`adversarial-review` skill, clean context): production-path fidelity, isolation cases, secrets in reports, injection traps, honesty of the stated limits
- [x] 3.7 Final gates of `docs/base-standards.md` section 9 re-run after the last change: `ruff check --no-cache`, `ruff format --check`, `mypy --strict`, backend tests, CI green on Linux, `openspec validate --all --strict` [PR #22, commit 282df01: backend, frontend and privileges green on Linux in both CI runs; the first frontend run failed once in the mocked Playwright test `student-chat.mocked` (keyboard deletion, not touched by this change) and passed on rerun, see TD-068; local gates re-run after the last change]

> Update 2026-11-21: the owner approved the 76-case set provisionally, authorised one incremental review and forbade new real calls until a reliable budget exists; the request ledger (reserve before, settle after) was added, see `reports/2026-11-21-pending-metrics-and-budget.md`.
> Open on purpose: **3.3b** only (answers baseline with the real model). Two real runs on 2026-11-23 answered 10 of the 45 cases and were stopped by `503` and `504` errors of the provider (18 requests; ledger: `authorised_total` 206, `spent` 172 = 154 estimated + 18 real); nothing is presented as a baseline and no third run is authorised. The change is **not archived**: 3.3b is a condition of archiving, and moving it to a follow-up change is a decision of the owner. The seven minor findings of the third review are accepted for the PR (TD-067) and the 76-case golden set stays provisional (`v0.2-draft`) until the owner reviews it.
