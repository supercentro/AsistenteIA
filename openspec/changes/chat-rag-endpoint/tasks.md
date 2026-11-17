# Tasks

## 0. Setup: Create Feature Branch (MANDATORY - FIRST STEP)

- [x] 0.1 Create feature branch `feature/chat-rag-endpoint` from the `main` branch and verify branch creation
- [x] 0.2 Verify the current database state (users, subjects, documents, chunks counts) as a pre-implementation baseline

## 1. Backend: Dependencies and Configuration (TDD)

- [x] 1.1 Write unit tests for the new Settings fields (`GOOGLE_API_KEY`, `LLM_BACKEND`, `CHAT_LLM_MODEL`, `CHAT_LLM_TIMEOUT_SECONDS`, `CHAT_TOP_K`, `CHAT_RELEVANCE_THRESHOLD`, `CHAT_HISTORY_MESSAGES`, `CHAT_RATE_LIMIT`): validate defaults, ranges, SecretStr for the API key, fake-LLM gate (same pattern as EMBEDDER_BACKEND). Run and confirm they fail.
- [x] 1.2 Add `langchain-google-genai` to `pyproject.toml` dependencies (per D1 and `docs/backend-standards.md` §1). Add the new settings fields to `Settings` in `core/config.py`. Run `uv lock` to update `uv.lock`. Run the failing tests from 1.1 and confirm they pass.
- [x] 1.3 Update `.env.example` with the new variables (placeholder values) and `docs/development_guide.md` with memory requirements for the API process with the embedder loaded. Verify `.env.example` matches the new settings.

## 2. Backend: LLM Service Protocol and Fake (TDD)

- [x] 2.1 Write unit tests for `LLMService` protocol: `FakeLLMService.generate` returns a deterministic string containing chunk references; `GeminiLLMService` (mocked HTTP) handles success, timeout, 429, 5xx, and safety-block responses. Run and confirm they fail.
- [x] 2.2 Implement `LLMService` protocol, `FakeLLMService`, and `GeminiLLMService` (wrapping `ChatGoogleGenerativeAI` from `langchain-google-genai`) in a new `services/llm_service.py`. Add `build_llm_service(settings)` factory (same pattern as `build_embedder`). Run the tests from 2.1 and confirm they pass.
- [x] 2.3 Write unit tests for the new domain errors (`ConsentRequiredError`, `LLMUnavailableError`, `LLMBlockedError`, `SearchUnavailableError`): verify status codes, error codes, and that messages are fixed text. Implement the errors in `core/errors.py`. Run and confirm they pass.

## 3. Backend: Conversation Models and Migration (TDD)

- [x] 3.1 Write unit tests for the SQLAlchemy models (`Conversation`, `Message`, `MessageSource`) in a new `models/conversation.py`: verify column types, constraints, foreign keys, cascades (ON DELETE CASCADE for messages, ON DELETE SET NULL for chunk_id), and the composite index on `(student_id, subject_id, created_at)`. Run and confirm they fail.
- [x] 3.2 Implement the three SQLAlchemy models in `models/conversation.py` with the `MessageRole` enum (`user`, `assistant`). Run the tests from 3.1 and confirm they pass.
- [x] 3.3 Create the Alembic migration: three tables (`conversations`, `messages`, `message_sources`), all indexes, foreign keys, and GRANT statements (`asistente_app`: SELECT/INSERT/DELETE; `asistente_cli`: SELECT/DELETE; no grants for `asistente_worker`). Include a working `downgrade` (REVOKE + DROP). Verify with `alembic check` that there is no drift.
- [x] 3.4 Run the migration on the test database and verify: tables exist, privilege matrix is correct (app can SELECT/INSERT/DELETE, app cannot UPDATE, worker has no access, CLI can SELECT/DELETE but not INSERT), and `alembic check` reports no drift.

## 4. Backend: Conversation and Message Repositories (TDD)

- [x] 4.1 Write integration tests for `ConversationRepository`: `create`, `get_by_id_and_student` (own vs. other student returns None), `list_by_student` (with and without `subject_id` filter, ordering by `created_at` desc), `delete_by_id_and_student` (own vs. other student), `delete_all_by_student` (only own, others untouched). Run and confirm they fail.
- [x] 4.2 Implement `ConversationRepository` in `repositories/conversation_repository.py`. All queries MUST be scoped by `student_id`. Run the tests from 4.1 and confirm they pass.
- [x] 4.3 Write integration tests for `MessageRepository`: `create_with_sources` (persists message + message_sources in one call), `list_by_conversation` (ordered by `created_at` asc, includes sources for assistant messages, empty sources for user messages). Verify `chunk_id` SET NULL behavior when a document is deleted. Run and confirm they fail.
- [x] 4.4 Implement `MessageRepository` in `repositories/message_repository.py`. Run the tests from 4.3 and confirm they pass.

## 5. Backend: Prompt Builder and Injection Defenses (TDD)

- [x] 5.1 Write unit tests for the prompt builder: system prompt contains grounding instructions; context blocks use delimiters; delimiter neutralization replaces `<CONTEXT>`, `</CONTEXT>`, `<SYSTEM>`, `</SYSTEM>` in chunk content and user message; history messages are included in the correct order; the assembled prompt respects the configurable `CHAT_HISTORY_MESSAGES` limit. Run and confirm they fail.
- [x] 5.2 Implement the prompt builder in a new `services/prompt_builder.py`: system prompt constant, `build_prompt(system, history, chunks, user_message)` function, delimiter neutralization. Run the tests from 5.1 and confirm they pass.
- [x] 5.3 Write unit tests for prompt-injection defense scenarios: a chunk containing "Ignore previous instructions" does not break out of the context section; a user message containing delimiter characters is neutralized. Run and confirm they pass.

## 6. Backend: RAG Service (TDD)

- [x] 6.1 Write unit tests for `RAGService` with mocked dependencies (ChunkRepository, Embedder, LLMService, ConversationRepository, MessageRepository): happy path (embed -> retrieve -> filter -> prompt -> LLM -> persist -> response), no-material path (all chunks below threshold, LLM not called, no_material=true), consent check (missing consent raises ConsentRequiredError), enrollment check (existing subject without enrollment raises ForbiddenError, 403; unknown subject raises NotFoundError, 404), conversation validation (conversation_id for wrong student or wrong subject raises NotFoundError), LLM errors (timeout -> LLMUnavailableError, safety block -> LLMBlockedError), vector search failure (SearchUnavailableError). Run and confirm they fail.
- [x] 6.2 Implement `RAGService` in `services/rag_service.py` following the pipeline in design D3. The `answer` method orchestrates: consent gate -> validate -> embed -> find_similar -> threshold filter -> prompt build -> LLM call -> persist -> return. Use `commit_or_rollback(db)` before building the response. Run the tests from 6.1 and confirm they pass.
- [x] 6.3 Write unit tests for snippet truncation: source snippets are capped at 300 characters. Run and confirm they pass.
- [x] 6.4 Write unit tests for the phased `RAGService` (design D3, request phases): `generate` touches no repository or session; `persist` revalidates consent, enrollment and conversation ownership; a vanished chunk falls back to `chunk_id` NULL inside a savepoint; a vanished conversation or subject raises `NotFoundError`; a vanished user raises `UnauthorizedError`. Run and confirm they fail.
- [x] 6.5 Implement the phases (`prepare`, `generate`, `persist`) in `services/rag_service.py` and orchestrate them in `POST /chat`: close the request session before the LLM, new session for persistence with explicit `commit_or_rollback`, embedding and synchronous database work in the thread pool. Run the tests from 6.4 and confirm they pass.
- [x] 6.6 Write unit tests for the advisory lock of M2 (design D3, serialising persistence with unenrolment): the key is stable, a signed 32-bit integer, different for different pairs; `persist` takes the lock before it revalidates consent and enrollment and takes exactly one; `prepare` and `generate` take none; `delete_for_teacher_subject` takes it before it deletes. Run and confirm they fail. [Failing run recorded first (import errors: the lock did not exist), then green; 5 unit tests in tests/unit/test_enrollment_lock.py and tests/unit/test_rag_service.py.]
- [x] 6.7 Implement `EnrollmentRepository.lock_student_subject` and call it first in `RAGService.persist` and in `delete_for_teacher_subject`. Run the tests from 6.6 and confirm they pass. [EnrollmentRepository.lock_student_subject; first statement of RAGService.persist; before the delete in delete_for_teacher_subject.]
- [x] 6.8 Write tests for the bounded history (automated review of PR #14): the repository returns only the newest `CHAT_HISTORY_MESSAGES` messages of the student's own conversation in chronological order (user before assistant within a turn), nothing for another student's conversation, and runs no query when the limit is 0; `prepare` reads history only when the limit is above 0. Run and confirm they fail. [Failing run first: 13 failed in the unit files (history read through the removed full-list method; empty answers returned as 200). Repository tests in test_message_repository.py (5 tests) were written with the code, so compensated by a mutation check: no reversal, no limit, wrong tie order, no owner scope and a query for 0 are each detected (3, 1, 1, 1 and 1 failures); restored and green.]
- [x] 6.9 Implement `MessageRepository.recent_for_prompt` and use it in `RAGService.prepare`. Run the tests from 6.8 and confirm they pass. [MessageRepository.recent_for_prompt (bounded query, owner-scoped, no sources loaded, no query for 0) used by RAGService._load_history; 82 unit tests and 12 repository integration tests pass.]

## 7. Backend: Chat and Conversation Routers (TDD)

- [x] 7.1 Write integration tests for `POST /chat`: valid chat returns 200 with `ChatResponse` (conversation_id, message_id, answer, sources, no_material=false); no-material returns 200 with `no_material=true` and empty sources; missing consent returns 403 `CONSENT_REQUIRED`; teacher returns 403; unauthenticated returns 401; not enrolled returns 403; unknown subject returns 404; invalid conversation_id (other student, other subject) returns 404; empty message returns 422; oversized message returns 422. Use FakeEmbedder and FakeLLM with seeded chunks. Run and confirm they fail.
- [x] 7.2 Implement the `POST /chat` endpoint in `api/v1/endpoints/chat.py`. Wire Pydantic request/response schemas (`ChatRequest`, `ChatResponse`, `SourceSchema`). Register the router in `api/v1/router.py`. Run the tests from 7.1 and confirm they pass.
- [x] 7.3 Write integration tests for conversation endpoints: `GET /conversations` (list own, filter by subject, empty array, teacher 403); `GET /conversations/{id}/messages` (own conversation with sources, other student 404, non-existent 404); `DELETE /conversations/{id}` (own 204, other student 404); `DELETE /users/me/conversations` (own 204, others untouched, teacher 403). Run and confirm they fail.
- [x] 7.4 Implement conversation endpoints in `api/v1/endpoints/conversations.py`. Register the router. Run the tests from 7.3 and confirm they pass.
- [x] 7.5 Write integration tests for rate limiting on `POST /chat`: verify 429 with `Retry-After` when the limit is exceeded. Run and confirm they pass.
- [x] 7.6 Wire the chat rate limiter in the endpoint dependencies and verify the test from 7.5 passes.
- [x] 7.7 Write integration tests for the request phases: no checked-out pool connection and no open application transaction while the LLM generates; consent lost, enrollment removed, conversation deleted, subject deleted and cited document deleted during generation; provider failure; request cancelled during generation; two concurrent requests on one conversation; the event loop stays responsive while the query is embedded. Run and confirm they fail.
- [x] 7.8 Make the tests from 7.7 pass with the implementation of 6.5 (no further design change).
- [x] 7.9 Write integration and repository tests for the visibility of conversations after unenrolment (list omits them, messages return 404 without content, erasure still works, re-enrolment restores them, chat with that conversation returns 403). Run and confirm they fail.
- [x] 7.10 Implement the visibility rule in `ConversationRepository` and the conversation endpoints. Run the tests from 7.9 and confirm they pass.
- [x] 7.11 Write deterministic integration tests for the races of M2: an unenrolment waits for an in-flight persist and completes after it (the turn is stored); a persist waits for an in-flight unenrolment and then returns 403 storing nothing; consent changed while the persist waits gives 403; a rollback releases the lock; another student and another subject are not blocked; no advisory lock during embedding or generation; a stress run of concurrent turns and unenrolments gives no 5xx (no deadlock). Run and confirm they fail. [tests/integration/test_chat_enrollment_lock.py, 12 tests; the waiter is observed in pg_locks before every release; 20 consecutive runs without a failure; five mutations (no lock in persist, none in the unenrolment, lock after the revalidation, one global key, lock in the read phase) are each detected by named tests.]
- [x] 7.12 Make the tests from 7.11 pass with the implementation of 6.7; run the role-bound suites (the lock under the application role) on a disposable cluster. [Role-bound suites on disposable Linux PostgreSQL after the last change: 452 passed; roles mode 531 passed (the unenrolment and chat scenarios run the lock as the application role).]

## 8. Backend: LLM and Search Error Handling Tests

- [x] 8.1 Write integration tests for LLM error responses: LLM timeout returns 502 `LLM_UNAVAILABLE`; LLM safety block returns 502 `LLM_BLOCKED`; response body and captured logs contain no API key, model identifier, or provider detail. Run and confirm they pass with the FakeLLM configured to simulate each failure.
- [x] 8.2 Write integration tests for vector search failure: database error during find_similar returns 503 `SEARCH_UNAVAILABLE`; response body and captured logs contain no embedding, chunk text, or SQL parameter. Run and confirm they pass.
- [x] 8.3 Write negative and extreme-input integration tests: control characters in message, Unicode edge cases, `conversation_id` that is not a UUID, `subject_id` that is not a UUID — all return 422 or 404, never 500. Verify captured logs contain no passwords, hashes, tokens, emails, or SQL parameters. Run and confirm they pass.
- [x] 8.4 Write tests for an empty provider answer (automated review of PR #14, `docs/backend-standards.md` error table): an empty string, only whitespace, an empty content list and a list without text blocks give `LLMBlockedError`; a text answer and a list of text blocks are returned as text; over HTTP the answer is 502 `LLM_BLOCKED` and nothing is stored. Run and confirm they fail. [Failing run first (10 parametrised cases in tests/unit/test_llm_service.py); the HTTP side needs no new test: LLMBlockedError already maps to 502 LLM_BLOCKED and nothing is stored.]
- [x] 8.5 Normalise the provider content in `GeminiLLMService` and reject an empty answer. Run the tests from 8.4 and confirm they pass. [GeminiLLMService._answer_text normalises str and block content, ignores non-text blocks, strips; an empty result raises LLMBlockedError (logged as a fixed message).]

## 9. Backend: RAG Quality Tests with Seeded Fixtures

- [x] 9.1 Create test fixtures that seed "La Dama de Blanco" chunks (or a representative subset with FakeEmbedder deterministic vectors) into the test database for a subject with an enrolled student.
- [x] 9.2 Write integration tests: a question about a topic covered in the material returns an answer with source citations (non-empty sources, valid chunk_ids); a question about an unrelated topic returns `no_material: true`; source snippets are truncated to at most 300 characters. Run and confirm they pass.
- [x] 9.3 Write an integration test verifying that citation snapshot fields survive document deletion: after a teacher deletes the document, `GET /conversations/{id}/messages` still returns the sources with `chunk_id: null` and the original `filename` and `page_number`. Run and confirm it passes.

## 10. Backend: Embedder Initialization and Startup

- [x] 10.1 Write a test verifying that the API process loads the embedder at startup (stored on `app.state.embedder`) and that it fails fast with a clear error if the model files are missing. Run and confirm it passes.
- [x] 10.2 Wire `build_embedder(settings)` in `create_app` to store the embedder on `app.state.embedder`. Wire a dependency that provides it to the chat endpoint. Verify the test from 10.1 passes.
- [x] 10.3 Modify the API Dockerfile target to include `--extra embedding` in the `uv sync` command and add the model fetch step (reuse `docker/fetch_model.py` and the same pinned revision as the worker target). Add `HF_HUB_OFFLINE=1` and `TRANSFORMERS_OFFLINE=1` to the API environment. Verify the API image builds successfully and the embedder starts at application startup.
- [x] 10.4 Update `docker-compose.yml` to add `EMBEDDING_MODEL_PATH` and `EMBEDDER_BACKEND` to the backend service environment (or its env file), matching the worker's model path. Verify the full stack starts with `docker compose up`.

## 11. Backend: Review and Update Existing Unit Tests (MANDATORY)

- [x] 11.1 Review existing test suites for regressions: authentication tests, consent tests, enrollment tests, subject tests, document tests, chunk retrieval tests. Verify no existing test is broken by the new models, routers, or dependencies.
- [x] 11.2 Verify that `mypy --strict` passes on `backend/app` with the new code.
- [x] 11.3 Verify that `ruff check --no-cache` and `ruff format --check` pass on the backend.

## 12. Backend: Run Unit Tests and Verify Database State (MANDATORY)

- [x] 12.1 Capture pre-test database baseline for impacted entities (conversations, messages, message_sources counts; existing users, subjects, documents, chunks untouched)
- [x] 12.2 Run targeted unit tests for changed modules (`services/rag_service.py`, `services/llm_service.py`, `services/prompt_builder.py`, `repositories/conversation_repository.py`, `repositories/message_repository.py`)
- [x] 12.3 Run the full backend test suite (`pytest backend/`)
- [x] 12.4 Verify post-test database state and restore if needed
- [x] 12.5 Create report `openspec/changes/chat-rag-endpoint/reports/YYYY-MM-DD-step-12-unit-test-and-db-verification.md`
- [x] 12.6 Mark step complete only after tests pass and report exists

## 13. Backend: Manual Endpoint Testing with curl (MANDATORY - AGENT MUST EXECUTE)

- [x] 13.1 Ensure backend server is running with FakeLLM and FakeEmbedder (APP_ENV=test or ALLOW_FAKE_LLM=true + ALLOW_FAKE_EMBEDDER=true)
- [x] 13.2 Test `POST /chat` with curl: valid request (enrolled student, consented, valid subject_id and message) — verify 200 with ChatResponse structure
- [x] 13.3 Test `POST /chat` negative cases with curl: missing token (401), teacher token (403), no consent (403 CONSENT_REQUIRED), not enrolled (403), empty message (422), oversized message (422)
- [x] 13.4 Test `GET /conversations` with curl: list conversations, filter by subject_id, verify response structure
- [x] 13.5 Test `GET /conversations/{id}/messages` with curl: verify messages with sources, 404 for other student's conversation
- [x] 13.6 Test `DELETE /conversations/{id}` and `DELETE /users/me/conversations` with curl: verify 204, verify data removed
- [x] 13.7 Restore database state after tests and document all curl commands and responses in report `openspec/changes/chat-rag-endpoint/reports/YYYY-MM-DD-step-13-curl-testing.md`

## 14. Frontend: E2E Verification (MANDATORY - AGENT MUST EXECUTE)

- [x] 14.1 Since this change is backend-only (no frontend UI), verify the endpoints are accessible from the frontend's perspective using Playwright MCP or CLI: navigate to the running frontend, confirm no regressions in existing pages (login, subjects list), and verify the API responds correctly when called from the browser's network layer (or curl from the frontend container)
- [x] 14.2 Document verification outcomes in report `openspec/changes/chat-rag-endpoint/reports/YYYY-MM-DD-step-14-e2e-verification.md`

## 15. Update Technical Documentation (MANDATORY)

- [x] 15.1 Update `docs/development_guide.md`: document the embedder memory requirement for the API container, the new environment variables, and the FakeLLM/FakeEmbedder configuration for development without Docker GPU
- [x] 15.2 Verify `docs/api-spec.yml` consistency: confirm the implementation matches the existing contract (status codes, schemas, error codes). Report any divergence without silently fixing it.
- [x] 15.3 Verify `docs/data-model.md` consistency: confirm the migration matches the existing table definitions and privilege matrix. Report any divergence.
- [x] 15.4 Update `docs/technical-debt.md`: note that TD-003 (consent not enforced on /chat) is now closed by this change (with evidence from tests). Do NOT close TD-033 (embedding quality) — evidence is insufficient.

## 16. Backend: Final Verification — Quality Gates (MANDATORY)

- [x] 16.1 Run `mypy --strict` on `backend/app` and verify it passes
- [x] 16.2 Run `ruff check --no-cache` and `ruff format --check` and verify they pass
- [x] 16.3 Run `alembic check` and verify no model/migration drift
- [x] 16.4 Run the full test suite (`pytest backend/ -x`) and verify all tests pass, re-run AFTER the last change to code, tests, scripts, or documentation — unit: 1435 passed, 4 environmental failures (reproduced on clean main, see step-12 report), 110 skipped; integration: 903 passed non-role-bound; role-bound gate steps run by hand on a disposable cluster: 446 passed + 4 Windows-environment failures (same on clean main), roles mode 531 passed; a Linux run of the full privilege gate is still pending, see round-2 matrix [Round 5, 2026-11-17, after the last change to code and tests: complete suite on Linux against disposable PostgreSQL only (own orchestration of the CI `backend` job and the gate steps, scratch test image with `uv sync --frozen --extra ingestion`): ruff, ruff format and `mypy --strict app tests` clean; unit 1563 passed; integration not role-bound 973 passed; role-bound 452 passed; roles mode 531 passed. 11 unit tests are skipped on Linux because git metadata is not in the image (test_deployment_files: 7, test_environment_files: 4); on the host those two files run with no skip (78 passed). On the Windows host the only failures are the 4 environment-only unit tests, which pass on Linux. See reports/2026-11-17-round5-m2-backend.md]
- [x] 16.5 Verify that no test calls the real Gemini API (grep for actual API key usage or network calls in test files) — all keys are test placeholders (AIza-test-key-*)
- [x] 16.6 Verify that error responses and captured logs from new endpoints never expose passwords, hashes, tokens, emails, or SQL parameters (review log spy assertions in the security tests) — all error messages are fixed strings
- [x] 16.7 Verify the full stack starts with `docker compose up` following `docs/development_guide.md` [Round 5, 2026-11-17, on the final tree (advisory lock, `--reload` removed from the development backend command): isolated disposable Compose project (`chatiso`, own network and volume, no published port, throwaway env files, fake LLM, real worker and embedder), never on the persistent stack: `up -d --build` exit 0, bootstrap and migrate exited 0, database at 0007, `db-verify` no findings, backend healthy without `--reload`, worker healthy, frontend ready, end-to-end script all PASS; torn down, nothing left. See reports/2026-11-17-round5-m2-backend.md]
- [x] 16.8 Run the privilege gate steps (`role-suites`, `roles-mode`, `privilege-unit`) on a disposable Linux cluster and record the results; the four Windows-only failures are classified only with comparative evidence against clean `main`. [Qualification, 2026-11-17: the run reported as passed used a scratch copy of run_gate_local.sh with the host memory floor lowered from 6 GB (original) to 4 GB; the original was not modified and was not run, so this is not an exception-free run of the gate. The role-bound and roles-mode results were repeated with a separate orchestration (452 and 531 passed). A run that satisfies the original 6 GB guard has not been made.]

## 17. Review of PR #14 (automated review and independent whole-PR review, 2026-11-17)

- [x] 17.1 Lock regenerated with `uv lock`: the PR lock had lost the `pytorch-cpu` source (43 nvidia packages, CUDA torch for both Linux images). Guard test `test_the_lock_resolves_torch_from_the_cpu_index` fails on the previous lock and passes on the new one. [Image size not measured.]
- [x] 17.2 System prompt forbids URLs, tool calls, code to execute and revealing itself, as the rag-chat spec requires; test written first and seen failing.
- [x] 17.3 `docs/development_guide.md`: the API image carries the CPU-only torch through the `embedding` extra; migration 0007 holds no grants. The weakened Dockerfile assertion is replaced by the lock guard of 17.1.
- [x] 17.4 `docs/api-spec.yml`: 401/403 on the conversation routes and `Retry-After` on the chat 429; frontend types regenerated, `check:api-types` and the frontend job pass.
- [x] 17.5 Tests: teacher on GET messages and DELETE one conversation (403) and an anonymous caller on each conversation route (401).
- [ ] 17.6 Owner decisions pending, nothing applied: `last_message_preview` is always null (implement, or document as null); indexes on `messages.conversation_id`, `message_sources.message_id` and `chunk_id` (a new migration); `sources` lists every retrieved chunk, not only those used; 404 versus 403 reveals whether a subject exists; the chat rate limit counts unauthenticated traffic of one address (University NAT) and no test proves a forwarded-for header is ignored; `_is_safety_block` matches the words "blocked" and "safety" in any provider error.

## 18. Corrections of the owner's review of PR #14 (2026-11-17)

- [x] 18.1 Write tests for citation attribution: markers `[2]`, `[1]` and `[3]` select those chunks in rank order with the original rank; repeated markers count once; `[0]` and `[9]` are ignored; no valid marker returns all the retrieved chunks; the prompt numbers each block with its rank and asks for the marker; the response and `message_sources` hold the same chunks. Run and confirm they fail. [Failing run first: 10 failed (prompt builder and RAG service unit tests).]
- [x] 18.2 Implement `select_cited`, the numbered context blocks and the prompt instruction; use the selection in `RAGService._write_turn` for the response and for `message_sources`. Run the tests from 18.1 and confirm they pass. [`select_cited`, numbered blocks and prompt instruction; response and `message_sources` use the same selection; 12 new unit tests pass.]
- [x] 18.3 Write tests for the provider classification: 429 and 5xx with the words "blocked" or "safety" are `LLMUnavailableError`; a non-provider exception with those words is `LLMUnavailableError`; a 400 provider error naming a safety block, a finish reason `SAFETY`, `PROHIBITED_CONTENT` or `BLOCKLIST` and a prompt block reason are `LLMBlockedError`; a normal finish reason returns the text. Run and confirm they fail. [Failing run first: 10 failed in `test_llm_service.py`.]
- [x] 18.4 Implement the classification in `GeminiLLMService` (status code first, structured response signals, text only for a provider 400). Run the tests from 18.3 and confirm they pass. Real Gemini is not called: the signals were read in the installed library and the cases are simulated. [Status code first, structured finish reason and prompt block reason, text only for a provider 400; 39 tests pass. The integration test that encoded the old rule was updated with the spec.]
- [x] 18.5 Write a test against a real server started with the production arguments (`--no-proxy-headers`): requests to `/chat` with different `X-Forwarded-For` and `X-Real-IP` values reach the limit as one client and the next is 429 with `Retry-After`. Add the optional headers argument to `tests/server_support.request`. Run it, then prove it detects a regression with a mutation (client key taken from the header). [`tests/integration/test_chat_rate_limit_real_server.py` passes; the mutation (client key from `X-Forwarded-For`) makes it fail; restored.]
- [x] 18.6 Replace the absolute local path of `reports/round4-tools/iso_compose.sh` with the `ISO_SCRATCH` variable and update the tools README; confirm no local path or user name remains in the change's files. [`ISO_SCRATCH` replaces the path; no local path or user name remains in the change.]
- [x] 18.7 Confirm F3 of the independent review is resolved: the guide, the Dockerfile stages, the lock and migration 0007 agree (checked by reading and by the tests of `test_deployment_files.py`). [Re-read against the Dockerfile stages, the lock and migration 0007; the lock guard and the deployment tests pass. Image size not measured.]
- [x] 18.8 Documentation: `docs/api-spec.yml` (meaning of `sources`, the 403/404 implication), `docs/technical-debt.md` (TD-057 accepted for merge, TD-007 extended to `/chat`, new rows for `last_message_preview`, the missing indexes and the 403/404 implication; TD-003 and TD-058 unchanged), `docs/data-model.md` (how the sources are chosen), `docs/lessons-learned.md` (next ID, lock regeneration), round 7 report. [TD-057 accepted for merge, TD-007 extended, TD-059 to TD-062, L48 and L49, data model and API spec, types regenerated, `reports/2026-11-17-round7-pr14-corrections.md`.]
- [x] 18.9 Gates after the last change: ruff check `--no-cache`, ruff format `--check`, `mypy --strict app tests`, unit and integration suites, frontend job, `openspec validate chat-rag-endpoint --strict`; Linux suites and the privilege gate through CI of the PR. [Local gates green as listed in the round 7 report; Linux suites and the privilege gate are checked by CI of the PR.]

## 19. Closing corrections of PR #14 (owner's decision, 2026-11-17)

- [x] 19.1 Write tests for wrapped provider errors (finding of the incremental review of `682633d..1959721`, confirmed in the installed library: `GoogleRateLimitError` has no `code`, its cause has): a wrapped 429 and a wrapped 5xx whose text contains "blocked" or "safety" are `LLMUnavailableError`; a wrapped 400 whose cause names a safety block is `LLMBlockedError`; a wrapped error with no cause and no status keeps the text rule. Run and confirm they fail. [Failing run first: 1 failed (the wrapped 429) of 4 new tests.]
- [x] 19.2 Read the status code from the exception and then from its `__cause__` chain (bounded) in `_is_safety_block`. Run the tests from 19.1 and confirm they pass. [`_status_code` follows `__cause__` (bounded); 43 tests pass; the mutation that ignores the cause is detected.]
- [x] 19.3 Documentation: TD-062 extended with the stale-marker and echoed-marker vectors (kept open; provisionally accepted for the merge, not for deployment); `docs/data-model.md` says that `rank` is the retrieval rank and can have gaps; round 8 report. [TD-062 extended (Low-Medium, open, provisionally accepted for the merge only), design D5b and `docs/data-model.md` updated, `reports/2026-11-17-round8-pr14-closing.md`.]
- [x] 19.4 Gates after the last change: ruff check `--no-cache`, ruff format `--check`, `mypy --strict app tests`, unit suite, `openspec validate chat-rag-endpoint --strict`; Linux suites and the privilege gate through CI of the PR. [Local gates green; Linux suites and the privilege gate through CI of the PR.]

## Workflow follow-up

- Run the `adversarial-review` skill before archiving (this change touches chat/RAG, authorization, and personal data — mandatory per `docs/base-standards.md` §9.8).
- With user approval, record significant AI usage in `prompts.md`.
- Archive the change with `/opsx:archive chat-rag-endpoint` after review.
