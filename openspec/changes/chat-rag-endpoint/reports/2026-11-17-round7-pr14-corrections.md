# Round 7: corrections ordered by the owner after the review of PR #14 (2026-11-17)

Owner decisions applied: `682633d` published after checking its content (18 files, no secrets, no local paths); TD-057 accepted as residual risk for the merge (no deployment authorised); TD-058 and TD-003 unchanged; `last_message_preview`, extra indexes and CLI privilege reduction deferred and registered; the 403/404 contract kept and its implication documented. Procedure: `/opsx:update` first (spec, design, tasks 18.x), then tests, then code, then documentation.

## Results by item

| Item | Finding | Action | Evidence |
|---|---|---|---|
| Citation attribution | `docs/api-spec.yml` defines `Source` as the citation of a chunk *used* for an answer; the code returned and stored every retrieved chunk | Blocks are numbered `[n]` with their retrieval rank, the prompt asks the model to cite them, `select_cited` keeps the chunks whose valid marker appears in the answer (out-of-range markers ignored; with no valid marker every retrieved chunk is kept, because section 9.5 requires sources on every answer). The response and `message_sources` use the same selection. Design D5b, spec requirement "The sources of an answer are the chunks it cites". | Failing run first: 10 failed (`test_prompt_builder.py`, `test_rag_service.py`); then green. Residual: TD-062 (answers without markers), open, pending owner decision. |
| Rate limiting and `X-Forwarded-For` | No test proved the forwarded headers are ignored on `/chat`; unauthenticated requests use the budget of the address | Verified against a real Uvicorn process with the production arguments: with three different values of `X-Forwarded-For`, `X-Real-IP` and `Forwarded`, requests 4 and 5 are 429 with `Retry-After`. The per-address key is the project convention and was kept; the shared-address and anonymous-traffic effect is added to TD-007. | `tests/integration/test_chat_rate_limit_real_server.py`. Mutation: taking the client key from the header makes it fail; restored and green. |
| Provider block classification | `"safety"` or `"blocked"` anywhere in any exception text meant `LLM_BLOCKED`, even for a 429 or an unrelated exception | Status code first (429 and 5xx are never a block); structured signals of the response (finish reason `SAFETY`, `PROHIBITED_CONTENT`, `BLOCKLIST`, prompt block reason, read in the installed `langchain-google-genai`); text only for a provider exception with status 400. Real Gemini was not called: the cases are simulated. | Failing run first: 10 failed in `test_llm_service.py`; then 39 passed. One integration test encoded the old rule (a `RuntimeError` with those words was a block); it now uses a provider 400 and gained the two new non-block cases. This deviation follows the updated spec. |
| Local paths in scripts | `round4-tools/iso_compose.sh` held an absolute user path | The scratch directory comes from `ISO_SCRATCH` and the script refuses to run without it; the README says so. | `grep` finds no local path or user name in the change; `bash -n` and the refusal were checked. |
| F3 of the independent review | Guide said the API image has no torch and that 0007 holds grants | Already corrected in `682633d`; re-read against the Dockerfile stages, the lock and migration 0007 | `docs/development_guide.md`; `test_deployment_files.py` (40 tests, including the lock guard). The image size has not been measured. |
| Deferred and registered | `last_message_preview` always null; no indexes on the 0007 foreign keys; 403/404 existence signal; CLI grants | TD-059, TD-060, TD-061 (accepted by the owner's contract decision), TD-058 unchanged | `docs/technical-debt.md` |

## Documents changed

`docs/technical-debt.md` (TD-057 status, TD-007, TD-059 to TD-062), `docs/lessons-learned.md` (L48 lock regeneration, L49 contract wording), `docs/data-model.md` and `docs/api-spec.yml` (meaning of `sources`, the 403/404 note), regenerated `frontend/src/types/api.generated.ts`. Standards, skills and hooks were not touched. `readme.md` and `prompts.md` were not touched.

## Gates after the last change (Windows host, disposable PostgreSQL 15 container)

- `ruff check --no-cache`, `ruff format --check`, `mypy --strict app tests`: clean; `uv lock --check` consistent; `openspec validate chat-rag-endpoint --strict`: valid.
- Unit: 1338 passed, 4 failed (the known Windows-only tests), 110 skipped.
- Integration (not role-bound): 949 passed and 1 failed in the first run, the test described above; after the update the file passes (11 passed). The remaining integration tests did not change after that run.
- Frontend: lint, format, typecheck, `check:api-types`, 236 tests, build.
- Not run locally: Linux suites, role-bound and roles mode, privilege gate, isolated Compose. The corrections add no statement, grant or migration; the `backend` and `privileges` jobs of CI on the PR are the check.
