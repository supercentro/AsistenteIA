# Round 8: closing corrections of PR #14 (2026-11-17)

Source: incremental independent review of `682633d..1959721` (read-only; verdict PASS WITH GAPS, no Blocker or Major) and the owner's decision of the same day. Procedure: `/opsx:update` (spec scenario, design D5b, tasks section 19), then the test, then the code, then the documentation.

## Corrections

| Finding | Verified | Action | Evidence |
|---|---|---|---|
| Minor: a 429 wrapped by `langchain-google-genai` (`GoogleRateLimitError`) has no `code`, so the text rule could turn "blocked" or "safety" in its message into `LLM_BLOCKED` | yes, in the installed library: the wrapper has no `code` attribute and the original error is its `__cause__` | `_status_code` reads the status from the error and then from its `__cause__` chain (at most 5 links); `_is_safety_block` uses it. The contract of round 7 ("the status code decides first") now also holds for the real, wrapped path. | Failing run first: 1 failed (wrapped 429) of 4 new tests in `test_llm_service.py`; then 43 passed. Mutation (the chain is not followed) makes 1 test fail; restored and green. A wrapped 5xx already passed because `GoogleAPIError` carries `code`. |
| Minor: stale markers from the history and markers repeated from a document | yes (by reading) | Added to TD-062 and to design D5b; TD-062 stays open, priority Low-Medium, accepted provisionally for the merge, not for deployment. No code change: both only select chunks already retrieved for this student and subject. | `docs/technical-debt.md`, `design.md` |
| Trivial: `rank (1 = most relevant)` against ranks with gaps | yes | `docs/data-model.md` says it is the retrieval rank and can have gaps | `docs/data-model.md` |

## Not done, on purpose

- `\d` accepting non-ASCII digits in the marker pattern: no bypass (the range 1..N still applies), and the owner limited this round to the confirmed finding and documentation.
- A prompt sentence telling the model to use only the numbers of the current context, and escaping `[n]` in chunk text: improvements outside the finding.
- 400 errors caused by an invalid request that name a safety setting, and the finish reasons `RECITATION` and `SPAM`: a known limit of the heuristic, unchanged.
- No real Gemini call was made; the wrapped errors are built from the classes of the installed library.
- TD-003, TD-057 and TD-058 are unchanged.

## Gates after the last change (Windows host)

- `ruff check --no-cache`, `ruff format --check`, `mypy --strict app tests`, `uv lock --check`, `openspec validate chat-rag-endpoint --strict`: clean.
- Unit: 1342 passed, 4 failed (the known Windows-only tests), 110 skipped.
- Integration, incremental (the seven chat files, disposable PostgreSQL): 56 passed. The complete integration run of round 7 (949 passed) is not repeated: the change touches only the error classification of `llm_service.py`.
- Linux suites, role-bound and roles mode, privilege gate: CI of the PR.
