# Round 6: review of PR #14 before the merge decision (2026-11-17)

Sources: the automated Codex review of `ac3e6e6` (2 findings), and an independent read-only review of the whole PR by a separate agent (12 findings, verdict FAIL for merge until three Majors were fixed). Each claim below was checked against the repository before acting.

## Findings and disposition

| # | Severity | Finding | Verified | Disposition |
|---|---|---|---|---|
| Codex 1 | Major (P2) | An empty provider answer was returned as 200 instead of 502 `LLM_BLOCKED` (`docs/backend-standards.md` error table) | yes | Fixed (tasks 8.4, 8.5). Spec scenario added. |
| Codex 2 | Minor (P2) | The whole conversation was loaded before the prompt trimmed it | yes | Fixed (tasks 6.8, 6.9): bounded query, no query when the window is 0. Design updated. |
| F1 | Major | `uv.lock` lost the `pytorch-cpu` source (43 nvidia packages, CUDA torch in both Linux images; `main` has 0). CI did not detect it | yes (main lock 0 nvidia and 4 CPU-index lines; PR lock 43 and 0) | Fixed by `uv lock` (17.1); guard test fails on the old lock and passes on the new one. Image size not measured. |
| F2 | Major | The system prompt did not forbid URLs, tool calls, code and revealing itself, which the spec requires | yes | Fixed (17.2), test first. |
| F3 | Major | `development_guide.md` said the API image has no torch and that migration 0007 holds grants; both false | yes | Fixed (17.3). |
| F6 | Minor | `api-spec.yml` lacked 401/403 on conversation routes and `Retry-After` on the chat 429 | yes | Fixed, types regenerated (17.4). |
| F7 | Minor | No tests for a teacher on two conversation routes or anonymous callers | yes | Tests added (17.5); they passed at once, so they close gaps. |
| F5, F8, F9 (part), F11, F12, F4 (part) | Minor / Question | `last_message_preview` always null; no indexes on the new foreign keys; `_is_safety_block` matches any "blocked" or "safety" text; `sources` lists every retrieved chunk; 404 vs 403 reveals subject existence; rate limit counts unauthenticated traffic and has no forwarded-for test | partly | Not applied and not accepted: owner decisions (17.6). |
| F10 | Minor | `--reload` removal and Windows test-support edits are unrelated to chat | yes | Documented in the PR; no action. |

## Evidence after the fixes

- Failing runs first: 13 unit tests (history and empty answer), 1 prompt test, and the lock guard against the previous lock. Repository tests were written with the code; compensated by a mutation check (five mutations, each detected).
- `ruff check --no-cache`, `ruff format --check`, `mypy --strict app tests`: clean. `openspec validate chat-rag-endpoint --strict`: valid.
- Windows host, disposable PostgreSQL: unit 1310 passed, 4 failed (the known environment-only tests), 110 skipped; integration 949 passed, 35 skipped. The first integration run reported one error that did not reproduce in two further runs; its cause was not identified.
- Frontend: lint, format, typecheck, `check:api-types`, 236 tests pass.
- Not re-run: the Linux suites, role-bound and roles mode, the privilege gate and the isolated Compose project. The changes do not touch grants, queries on new tables or the stack, but CI on the PR is the check.
