# rag-golden-set-evaluation: TDD and mutation evidence (sections 1 and 2)

Date: 2026-11-20. Branch `feature/rag-golden-set-evaluation` (from `main` `8d028ce`). Backend tooling only: `git diff -- backend/app` is empty.

## Failing run before the implementation (task 1.10)

Command (from `backend/`): `uv run --no-sync python -m pytest tests/unit/test_evaluation_cases.py tests/unit/test_evaluation_metrics.py tests/unit/test_evaluation_attribution.py tests/unit/test_evaluation_guards_and_report.py tests/integration/test_evaluation_harness.py -q`

Result: **5 files failed at collection (5 errors, 0 tests ran)**: `ModuleNotFoundError: No module named 'tests.evaluation.cases'` (and the other modules of the package). Output kept in `_failing_run.txt`.

Later groups were also written first and failed before their code existed:
- `test_evaluation_llm.py` (no-retry client, request recording): collection error, `tests.evaluation.llm` missing; the pause test of the counting wrapper failed (no `pause_seconds`).
- `select_cases` tests: 2 failed before the function existed.
- `test_evaluation_cli.py` was written with the CLI; it passed on its first run (6 tests), so its guarantees are covered by the mutations below rather than by a failing run (deviation, compensated).

## Passing run after the implementation

`pytest tests/unit/test_evaluation_*.py tests/integration/test_evaluation_harness.py`: **70 passed**. Corrections found by the first runs themselves: the report test looked for a Spanish word in an English report (test typo); `_status_code` of the application reads the attribute `code`, not `status_code` (the test double was changed to the real contract); `Settings` rejects a low-variety JWT secret (the test uses the shared test constant); `ruff` import order and a long line; `mypy --strict` and the `type: ignore` placement.

## Mutation checks (task 2.5)

Each guarded behaviour was broken in turn, the evaluation tests were run with `-x`, and the code was restored. First round: 17 of 17 detected. After the independent review (see its report) eight more were added; the final run of the whole list is **36 of 36 detected** (`_mutations.txt`; 25 after the first review, six more for the request ledger, five more after the second review). The first round:

| Mutation | Result |
|---|---|
| isolation check always passes | 1 failed |
| not enrolled students not required to be denied | 1 failed |
| call cap never exceeded | 1 failed |
| MRR off by one | 1 failed |
| secrets not scrubbed | 1 failed |
| URL passwords not scrubbed | 1 failed |
| database guard removed | 1 failed |
| real model allowed without the flag | 1 failed |
| subjects not cleaned | 1 failed |
| users not cleaned | 1 failed |
| generation bypasses the production phase | 1 failed |
| citation selection reimplemented | 1 failed |
| follow-up history not stored | 1 failed |
| forbidden access treated as empty retrieval | 1 failed |
| counting wrapper without cap | 1 failed |
| model asked in retrieval mode | 1 failed |
| fallback not detected | 1 failed |

The first attempt of the mutation script did not find five anchors (the files use CRLF); the script was fixed to normalise line endings and rerun, and the table above is the rerun. Mutations added after the first run (pacing, no-retry client) are covered by their own failing-first tests.

Added after the review (all detected): one event loop per case; the 50-request ceiling removed; the passage-in-one-chunk check removed; the catch-all with scrubbing removed; the enrolled-elsewhere student replaced by one with access; stale markers never reported; a fallback counted as a wrong citation; the abort after two failures disabled.

## Failing-first for the review fixes

The tests of the corrections were added before the code: `pytest tests/unit/test_evaluation_*.py tests/integration/test_evaluation_harness.py` stopped at collection (`ImportError: cannot import name 'require_cap_within_ceiling'`), and after that import was provided the new behaviours failed until implemented (`max_retries == 1`, one event loop, abort after two failures, catch-all with no password, stale markers, fallback not a wrong citation, enrolled-elsewhere student, passage inside one chunk, `--only`). Final run: **84 passed** (70 unit, 14 integration of the harness).

## Request ledger and second review

Failing-first: `test_evaluation_budget.py` failed at collection (`tests.evaluation.budget` missing); after the second review the tests of `reserve_run`, `settle_run`, the in-place fallback and the unwritable ledger failed (8 failed) before the code existed. Added mutations (all detected): budget check removed, ledger not required, early check removed, wrong comparison, calls not reserved, reservation never settled, in-place fallback removed, unwritable ledger ignored, settle failure hides the report, settling replaces instead of adjusting, password forms not registered (the last survived once and led to a direct test). Final evaluation tests: **107 passed** (85 unit, 22 integration).
