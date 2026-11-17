# Round 2: resolution of the open adversarial findings

**Change**: chat-rag-endpoint, branch `feature/chat-rag-endpoint` (uncommitted)
**Date**: 2026-11-17
**Rules followed**: OpenSpec artifacts edited through the `/opsx:update` procedure, only after the owner approved the exact revisions (A: 403 for non-enrolled, B: privilege requirement aligned with the real matrix); `openspec validate chat-rag-endpoint --strict` passes. No schema change, no migration, no privilege widened, no persistent database or existing container touched. Every code fix has a test recorded failing first, plus a mutation check.

## Findings matrix

| # | Finding | Root cause | Fix | Tests / evidence | Status |
|---|---|---|---|---|---|
| 5 | Source contract differed from `docs/api-spec.yml` (`document_filename`, no `document_id`, extra `score`, no `snippet` in history) | The service and schemas were written from the design's internal model (`message_sources` columns) instead of the canonical `Source` | One `SourceSchema` (`chunk_id`, `document_id`, `filename`, `page_number`, `rank`, `snippet`) for chat and history. `document_id` and `snippet` come from the chunk at answer time; in history from the surviving chunk via `MessageRepository.citation_details`, scoped by conversation, student, the conversation's subject and the student's current enrolment. **No migration**: after the document is deleted `chunk_id` is NULL, so `document_id` is `null` and `snippet` is `""` (documented in `docs/data-model.md`; the OpenSpec specs already required these fields, so no artifact edit) | 6 tests failing first; `test_history_sources_follow_the_canonical_source_contract`, `test_citation_snapshot_survives_document_deletion`, snippet cap, real-server and role-bound scenarios; mutations caught | **Fixed** |
| 5b | (round 2) history returned chunk text/ids to a student no longer enrolled | New join read chunks without checking current enrolment (base-standards 9.4) | `citation_details` joins `Enrollment`; unenrolled student gets `null`/`""` | `test_history_hides_chunk_text_once_the_student_is_unenrolled` (failing first; mutation of the student scoping caught) | **Fixed**. Spec scenario for it not written: needs `/opsx:update` approval |
| 6 | Spec said the migration grants app/cli SELECT, INSERT, DELETE on all three tables; real privileges come from `db_privileges.MATRIX` | OpenSpec text written before the matrix design (grants are applied by `db-migrate` from the matrix, not by the migration) | No privilege widened. The matrix is narrower (app: DELETE only on `conversations`; cli: no `message_sources`) and agrees with `docs/data-model.md`. `specs/conversation-history/spec.md` requirement and scenarios rewritten to the matrix (children removed by `ON DELETE CASCADE`) | Disposable PostgreSQL 15 + pgvector 0.8.7 cluster: `test_db_roles_effective` (catalog privileges equal the matrix), `db-verify` tests, role-bound scenario `test_chat_and_conversations_are_persisted_and_cascade` deleting a conversation and all conversations as the application role with no DELETE on children | **Fixed (artifact)** |
| 4 | Non-enrolled student got 404; canonical contract says 403 | OpenSpec spec and design said 404, contradicting `docs/api-spec.yml` ("for chat also not enrolled or consent missing") and the readme acceptance criterion (401/403 for non-enrolled) | Precedence: docs/ technical contract over the OpenSpec text. Enrolled? no -> subject exists? yes -> `ForbiddenError` 403; no -> `NotFoundError` 404. Checked before embedding, search or LLM. Spec, design D3 and tasks 6.1/7.1/13.3 updated | Unit, integration and real-server tests failing first (16 failures), role-bound check under the app role (403 and 404), mutation 403->404 caught | **Fixed** |
| 7 | DB connection held during the LLM call; sync work inside `async` endpoint; LLM client built per request | Design D3 persists after the LLM call inside one request session | Not changed: changes the approved transaction model | none | **OPEN: architectural decision** |
| 6b | Prompt: chunk filename and history content not neutralised (round-2 review) | Only chunk text and the user message went through `neutralize_delimiters` | Both are neutralised | 2 unit tests failing first, mutations caught | **Fixed** |
| TD-003 | see audit below | | Row restored to its original open text | | **OPEN by design** |

Also fixed in this round: `test_db_admin_grants` and `test_db_roles_lifecycle` pinned head `0006` (now `0007`); the five new routes had no role-bound scenario (`test_least_privilege_coverage` failed): scenario added; `SubjectRepository.subject_exists` registered as an anticipated root of the privilege inventory (same convention as `find_similar`, `is_enrolled`; no privilege added); the chat HTTP test modules were added to roles mode (`tests/conftest.py`), so they now run as the production application role.

## Independent reviews

- Round 1 (original code): FAIL, Majors 1-7 (see `2026-11-17-adversarial-review.md`).
- Round 2 (this round's fixes, clean-context subagent, read-only): **PASS WITH GAPS**, no blocker. Its Major (history after unenrolment) and finding 6 are fixed above. Left open on purpose: bare unclosed `<CONTEXT` and cross-script homoglyphs are not neutralised (minor); the 403/404 split lets a consented student test whether a subject UUID exists (accepted by the contract; propose to list in `docs/technical-debt.md`, not done without authorisation); stored message keeps format characters (cosmetic).

## The 443 tests that did not run

- **Cause**: `MissingTestDatabaseError: TEST_CLUSTER_IS_DISPOSABLE=true is required`. Those tests bootstrap roles and close `PUBLIC` on every database of the cluster, so the guard refuses the development cluster (which also hosts the persistent database). The flag was never set there.
- **How they were completed**: the documented procedure (`docs/development_guide.md`, "Role-bound mode", and `.github/scripts/privilege_gate.sh`). `run_gate_local.sh` refused to start (4.3 GB free memory, it needs 6 GB), so its two pytest steps were run by hand against one new throwaway container (`pgvector/pgvector:0.8.7-pg15`, tmpfs, 1 GB, loopback port, random password), after `assert_disposable_cluster.py check` accepted it. The container and credentials were removed afterwards; existing containers kept their uptimes.
- **Results after the last code change**: `-m role_bound`: 446 passed, 4 failed; `--least-privilege -m least_privilege`: 531 passed (gate minimum 480). The 4 failures are all `tests/integration/test_db_roles_startup.py` with `OSError: [WinError 10106]` (subprocess started with a stripped environment on Windows); identical (4 failed, 8 passed) on a clean `main` extract.
- Not run: the full `run_gate_local.sh` (memory), the CI steps `flow`/`drift-selfcheck`, and anything Linux-only (real worker, PDF child). A Linux run (CI or the worker image) is still needed to see the gate fully green.

## TD-003 audit (kept open)

- **Technical evidence for the consent gate**: missing consent and outdated consent return 403 `CONSENT_REQUIRED`: unit, integration, real Uvicorn process, and role-bound path. `has_current_consent` is the single comparison.
- **What is not verified**: the repository contains only the policy **version** (`PRIVACY_POLICY_VERSION=2026-10-v1`, `frontend/src/lib/privacyPolicy.ts`), not the policy text, and no consent screen yet. `docs/data-model.md` and `readme.md` require that the processing by Gemini (questions, history, retrieved chunks) be disclosed when consent is given; that cannot be verified because the text does not exist in the repo. Request content sent to Gemini: system prompt, retrieved chunk text and filenames, history, question; no name, email or id. The Gemini tier/terms in use (data retention or training use) are unknown.
- `docs/api-spec.yml` still says "recorded consent" in the chat summary, while the code requires consent for the **current** version.
- **Recommendation for the owner**: keep TD-003 open until (1) the policy text with the Gemini disclosure exists and its version is bumped, (2) the API summary is aligned, (3) the owner confirms the Gemini tier/terms. Then close it with the tests above as evidence; the UI re-acceptance flow belongs to the later frontend change.

## Verification summary (after the last code change)

| Check | Result |
|---|---|
| `ruff check --no-cache`, `ruff format --check`, `mypy --strict app` | clean (261 files, 92 source files) |
| Unit | 1438 passed, 4 failed (Windows environment; same on clean `main`) |
| Integration, not role-bound (isolated test DB) | 903 passed, 26 skipped (Linux-only), 0 failed; `test_real_processes.py` deselected in this last pass (it ran in the earlier full run) |
| Role-bound gate step on disposable cluster | 446 passed, 4 failed (environment) |
| Roles mode on disposable cluster | 531 passed |
| `alembic check`; 0007 downgrade then upgrade | no drift; ok (earlier in the session, migration unchanged since) |
| `openspec validate chat-rag-endpoint --strict` | valid |

## GO / NO-GO

**NO-GO for the PR.** Open: Major 7 (transaction model, needs an owner decision), a Linux run of the privilege gate, TD-003, and approval to add the unenrolled-history scenario to the spec. Everything else from the matrix is fixed and verified.

## Correction (round 3, 2026-11-17)

The statement above that the four `test_db_roles_startup.py` failures are "all environment" is **superseded**. A Linux run of the gate showed they also failed for a real reason (the API now refuses to start without LLM and embedder settings); the tests were fixed and the Linux gate passes. See `2026-11-17-round3-transactions-and-gate.md`, sections 4 and 5. The instruction to treat a failure as environmental only with comparative evidence applies.
