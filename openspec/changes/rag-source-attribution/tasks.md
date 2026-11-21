# Tasks

> Approved by the owner on 2026-11-21: first slice only (alternative A of `design.md`, D-A1), `[1, 2]` and `[1][2]` accepted and ranges not (D-A3), history preserved, document markers neutralised, source presentation and contract unchanged. Visual flag and numbering of sources in the chat belong to a second change. The quantitative target waits for the real-model baseline (`rag-golden-set-evaluation` task 3.3b). No frontend, API contract, schema or infrastructure change; no real Gemini call; no commit, push, PR, merge, deploy or archive without a new authorisation. Follows `docs/openspec-tasks-mandatory-steps.md`.

## 0. Branch

- [x] 0.1 Step 0: create the branch `feature/rag-source-attribution` from `main` (301ad9a) before any code change. Merge only through a Pull Request.

## 1. Tests first (pytest, fake model, no real call)

- [x] 1.1 `select_cited`: `[1, 3]`, `[1,3]`, `[1][2]` cite each rank; `[1-3]` is no citation (fallback); `[2, 9]` keeps 2; existing cases unchanged; a public `cited_ranks` helper returns the valid ranks
- [x] 1.2 `build_prompt`: a history answer with `[2]` or `[1, 2]` shows `(2)` or `(1, 2)`, words unchanged, user and assistant messages both; the only `[n]` of the prompt are the context labels; a chunk with `[3]` and a filename with `[2]` are neutralised; the current question is unchanged; the input lists are not mutated
- [x] 1.3 Service test: a turn with a history marker and a chunk marker stores the original messages, the original chunk and the original snippet, and the sources come from the answer markers only
- [x] 1.4 Harness: `classify_answer` and the stale-marker report use the same marker reading as production (a test fails if the harness keeps its own pattern); the trap cases of the golden set still classify
- [x] 1.5 Run the new tests before any implementation and record the failing run (command and failure summary) in `reports/`

## 2. Implementation (backend, `prompt_builder.py` and the harness reader)

- [x] 2.1 `prompt_builder.py`: one citation pattern for `[n]` and `[n, m]`, `cited_ranks`, `neutralize_markers`; `select_cited` uses it; `build_prompt` applies it to history, chunk text and filename only; the system prompt, the labels and the stored data are unchanged
- [x] 2.2 `tests/evaluation/attribution.py`: replace the private pattern by the production helper
- [x] 2.3 Mutation checks (temporarily break each guarded behaviour and show a test fails): history not neutralised, chunk text not neutralised, filename not neutralised, list form not read, range accepted, labels altered, stored text altered, harness reader detached
- [x] 2.4 `ruff check --no-cache`, `ruff format --check`, `mypy --strict app tests` clean

## 3. Verification

- [x] 3.1 Step N: review and update existing unit tests (`test_prompt_builder.py`, `test_rag_service.py`, `test_evaluation_*`)
- [x] 3.2 Step N+1: run the unit tests and the integration suite; verify the database state before and after (development and test databases untouched); report in `reports/`
- [x] 3.3 Step N+2: manual endpoint test. No endpoint, request or response changes; a call to `/chat` on the development stack would call the real model and is not authorised. Verify instead through the integration tests of `/chat` against PostgreSQL and a harness run with the fake model; record the deviation in the report
- [x] 3.4 Step N+3: no user-facing change, so no browser run; record that
- [x] 3.5 Step N+4: documentation: `docs/api-spec.yml` text on markers if needed (no contract change), `docs/technical-debt.md` (TD-062: which of its four ways are covered by this slice, still open), `docs/backend-standards.md` if the rule is stated there, `docs/roadmap.md`
- [x] 3.6 Independent review (`adversarial-review` skill, clean context) of prompt handling: injection, marker spoofing through every channel, regression of the history and snippets
- [ ] 3.7 Final gates of `docs/base-standards.md` section 9 re-run after the last change; `openspec validate --all --strict`; CI on Linux after the pull request

> Open on purpose: **3.7** (CI on Linux, checked on the pull request). `docs/api-spec.yml` got a descriptive wording change only (list and adjacent markers, no ranges), authorised by the owner on 2026-11-21; schema and behaviour of the contract are unchanged. Outside this change: the quantitative target and the real-model comparison (baseline 3.3b of `rag-golden-set-evaluation`), the visual flag and numbering of sources (second change); TD-062 stays open.
