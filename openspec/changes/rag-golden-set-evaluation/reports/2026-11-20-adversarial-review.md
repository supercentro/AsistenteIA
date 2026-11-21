# rag-golden-set-evaluation: independent adversarial review (task 3.6)

Date: 2026-11-20. Reviewer: a separate read-only subagent (skill `adversarial-review`), clean context, on the uncommitted tree. It read the artifacts, the code, the tests, the reports and the installed library sources; it ran nothing.

**Verdict of the first pass: FAIL** (seven Major, seven Minor). Dispositions by the implementing session:

| # | Sev | Finding | Disposition |
|---|---|---|---|
| 1 | Major | The first real run spent 44 calls, 22 failed without a recorded cause; the cap is per run with no ledger; `--max-calls` accepted any value | Fixed: ceiling of 50 enforced (test), abort after two failures in a row, error kinds recorded; the budget spent is recorded here, in the step 3.3 report and in TD-067. No further real call is made without the owner's confirmation |
| 2 | Major | One `asyncio.run` per case on a pooled async client probably caused the alternating failures | Fixed: the whole answers loop runs in one event loop (`asyncio.Runner`); test that all answers share one loop; mutation detected |
| 3 | Major | "Exact request accounting" not proven; `max_retries=0` means the library default | Fixed: `max_retries=1` (one attempt; the library passes it as `HttpRetryOptions(attempts=1)`), test asserts it; the documentation no longer claims HTTP-level accounting |
| 4 | Major | An unexpected library error could print the database password | Fixed: catch-all in `main` printing only the type and a scrubbed, shortened message; test with a missing key; mutation detected |
| 5 | Major | A fallback counted as a wrong citation; stale/repeated markers not reported | Fixed: fallback is not a wrong citation; stale/repeated markers listed by case; traps not exercised listed; cases without expected sources left out of the shares; tests and mutations |
| 6 | Major | The spec said cross-subject cases must "retrieve nothing" but the code (rightly) only forbids chunks of another subject | Fixed in the spec and the design (D14), reported as a divergence |
| 7 | Major | The change was not closable (tasks, debts, roadmap, gates) | Done except what needs the owner or a push (see below) |
| 8 | Minor | A passage straddling chunks can never match | Fixed: check after chunking, reported by case; on the real run it found none |
| 9 | Minor | No case for a student enrolled in another subject | Fixed: case `noenr-03` and the `enrolled_elsewhere` student; test and mutation |
| 10 | Minor | Cleanup stops at the first failing DELETE; no test for a failure during setup | Fixed: every DELETE attempted, failure reported; test with a failure while loading documents. A killed container can still leave `eval-*` rows (documented in TD-067; no sweep, to avoid deleting similarly named rows of the owner) |
| 11 | Minor | No tests for `--create-schema`, `--db-host/port`; concurrent use with pytest | Partly: documented (not concurrently with the integration suite); the schema cycle was exercised for real three times (empty before and after) but has no automated test (accepted, TD-067) |
| 12 | Minor | Traps pass vacuously when the target chunk is not retrieved | Fixed: "not exercised" notes |
| 13 | Minor | Refusals counted as fallbacks | Fixed with finding 5 |
| 14 | Minor | Private imports (`_CITATION_PATTERN`, `_status_code`) | Accepted: `app/` must not change in this change |

Held under attack: the runner calls the production functions; the sweep derivation equals production; the database guard, the cleanup by own ids and the FK order; metrics and empty groups; the golden set counts and README honesty.

State: all Major findings fixed with failing-first tests and mutation checks; a **second short review has not been run**. It is the remaining condition of task 3.6 before the pull request, together with the answers baseline that needs the owner's confirmation.


## Second pass (incremental, 2026-11-21)

A second independent read-only subagent re-checked the 14 dispositions and the new request ledger (reading the library sources for the retry defaults). Dispositions verified: TRUE for 2, 3, 5, 6, 8, 9, 10, 12, 13, 14; PARTIAL for 1, 4, 7, 11 (the ledger and secrets holes below). **Verdict: FAIL** because the ledger, the owner's only protection against overspending, had three Major gaps. All are now fixed with failing-first tests and mutation checks:

| Sev | Finding | Disposition |
|---|---|---|
| Major | The ledger was written only at the end: a killed process (SIGTERM, SIGKILL) left the calls unrecorded | Fixed: the calls are **reserved** before the first request and settled at the end; test that the ledger already holds them during the first call; mutations "not reserved" and "never settled" detected |
| Major | `os.replace` onto a single bind-mounted file fails in Docker; the first documented run would have spent requests and crashed | Fixed: fall back to writing in place; a ledger that cannot be written stops the run **before** any call; the guide says to mount the directory; tests with a busy `os.replace` and a read-only path; mutations detected |
| Major | An exception while recording or cleaning up replaced the original error and lost the report | Fixed: settling and cleanup never raise; their failures go into the report's problems (or stderr when the run already failed); tests for an unsettleable ledger and a failed cleanup; mutation detected |
| Minor | "Conservative" estimate of 154 was below the maximum of 264 | Fixed: called the midpoint estimate; the owner sets the total at or above `spent` plus the planned requests |
| Minor | Evidence counts (25 of 25) out of date | Fixed: 36 mutations, all detected; test counts below |
| Minor | Catch-all scrubbed only registered secrets; `drop_everything` could escape with a traceback | Fixed: the decoded and the URL-quoted password are registered; the schema drop failure is printed scrubbed |
| Minor | The early budget check also blocked retrieval mode with `--llm gemini` | Fixed: only the answers mode needs the ledger |
| Minor | The ledger is unlocked and only conventionally the owner's | Documented: real runs are serial; a guard against mistakes, not a security boundary |
| Minor | `RecordingModel.requests` never compared with the counted calls | Fixed: a test asserts they agree |

Reviewer's honest limits: it did not run the tests and did not re-read `metrics.py`, `report.py`, `cases.py` or the 76 cases in the second pass. A **third short look** at the three ledger fixes has not been run; it is the remaining condition of task 3.6.

## Third pass (short, 2026-11-21): verdict PASS WITH GAPS

Independent read-only subagent, scope: the three ledger fixes. All three hold (reserve before the first call, in-place fallback and refusal when unwritable, settle/cleanup never mask the original error). No Blocker, no Major. It ran the 24 unit tests of budget and CLI; it did not run integration tests and did not read design D12. Minors, tracked and not fixed (no behaviour change needed before the real run; each is safe-side):

1. `settle_run` does not cap `calls` at `reserved`; correct today because each case makes one model call (`runner.py`).
2. Budget check and reservation are separate unlocked reads; two interleaved runs could both pass (documented: real runs are serial).
3. The in-place fallback is not atomic; a kill mid-write truncates the ledger and the next run refuses to start (safe side, history lost).
4. `engine.dispose()` in `_finish` is outside a try.
5. `KeyboardInterrupt`/`SystemExit` during `_finish` are not caught by `except Exception`.
6. Spec wording: an unwritable ledger is detected at reservation time (after DB setup, before any model call), not by the early CLI check.
7. Test gaps: BaseException path, settle with fewer calls than reserved after an abort, ledger unwritable after reservation, owner edit between reserve and settle.

Reviewer's limit: `test_evaluation_llm.py` checks only the `max_retries` attribute, not the real request count; the single-attempt behaviour rests on the library source.
