# Design

## Context

See `proposal.md` for motivation. The backend has the full ingestion pipeline operational: documents are chunked, embedded (384-dim, `paraphrase-multilingual-MiniLM-L12-v2`) and stored in pgvector. `ChunkRepository.find_similar` provides authorized, subject-scoped vector search with `SearchActor`. The `Embedder` protocol (`build_embedder`) loads the model from local files. `has_current_consent()` in `services/consent_service.py` checks consent. `commit_or_rollback(db)` in `api/transaction.py` provides the explicit commit pattern. The `AppError` hierarchy, rate limiter, and auth deps (`CurrentUser`, `require_student`, `DbSession`, `AppSettings`) are established.

`docs/api-spec.yml` already defines the full REST contract for chat and conversations. `docs/data-model.md` already defines the three tables. No contract changes are needed.

The `Settings` class extends `WorkerSettings`, which already has `embedding_model_path`, `embedding_threads`, and `embedder_backend`. The API process inherits these and can reuse `build_embedder`.

No LLM dependency exists today. Only `langchain-text-splitters` is in `pyproject.toml`. The Gemini client is a new addition.

## Goals / Non-Goals

**Goals:**
- Implement the complete `POST /chat` RAG pipeline per `docs/backend-standards.md` §6
- Implement conversation CRUD endpoints per `docs/api-spec.yml`
- Enforce consent on chat (close TD-003)
- Persist conversations with traceable citations (snapshot fields survive document deletion)
- Prompt-injection defenses per `docs/backend-standards.md` §6
- Explicit commit before 200 (TD-039 pattern)
- Least-privilege grants for three new tables
- TDD with FakeLLM and FakeEmbedder; Gemini never called in CI

**Non-Goals:**
- Frontend UI (separate change)
- Streaming responses
- Advanced retrieval (reranking, HyDE, query expansion)
- Conversation titles or summaries
- Token-level cost tracking

## Decisions

### D1: LLM client — `langchain-google-genai` per `docs/backend-standards.md`

**Choice**: Use `langchain-google-genai` (`ChatGoogleGenerativeAI`), wrapped behind an `LLMService` protocol with `FakeLLMService` for tests.

**Rationale**: `docs/backend-standards.md` §1 defines the LLM integration as "Gemini 2.5 Flash via `langchain-google-genai`" and the RAG stack as "LangChain (text splitters, prompt templates, Gemini chat model wrapper)". This is the canonical standard (precedence level 3 per `docs/base-standards.md` §0) and was confirmed as an architectural decision in `prompts.md` §2.1. Additionally, `langchain-core==1.7.6` is already installed as a transitive dependency of `langchain-text-splitters==1.1.3` (verified in `uv.lock`), so adding `langchain-google-genai` brings only `google-generativeai` and its direct dependencies — not ~30 new packages.

**Protocol**: `LLMService` with a single method `generate(system_prompt: str, user_messages: list[dict]) -> str`. Implementations:
- `GeminiLLMService`: wraps `ChatGoogleGenerativeAI` from `langchain-google-genai`. The wrapper isolates the LangChain API surface to a single module (`services/llm_service.py`), so the rest of the codebase depends on the protocol, not on LangChain types.
- `FakeLLMService`: returns a deterministic string containing chunk references (for citation verification in tests).

Factory: `build_llm_service(settings)` follows the same pattern as `build_embedder`.

**Alternative considered**: `google-generativeai` (direct SDK) — lighter dependency, but contradicts `docs/backend-standards.md` §1 and breaks coherence with the existing LangChain components (`langchain-text-splitters`, `langchain-core`).

**Configuration** (all new, in `Settings`):
- `GOOGLE_API_KEY`: `SecretStr`, mandatory when `LLM_BACKEND` is `gemini`, git-ignored
- `LLM_BACKEND`: `Literal["gemini", "fake"]`, default `"gemini"`; `"fake"` accepted only with `APP_ENV=test` or `ALLOW_FAKE_LLM=true` outside production (same pattern as `EMBEDDER_BACKEND`)
- `CHAT_LLM_MODEL`: `str`, default `"gemini-2.5-flash"` (the model identifier passed to the SDK)
- `CHAT_LLM_TIMEOUT_SECONDS`: `int`, default 30, range 5-120
- `CHAT_TOP_K`: `int`, default 5, range 1-50 (passed to `find_similar`)
- `CHAT_RELEVANCE_THRESHOLD`: `float`, default 0.3, range 0.0-1.0 (cosine similarity)
- `CHAT_HISTORY_MESSAGES`: `int`, default 10, range 0-50 (how many previous messages to include in the LLM prompt)
- `CHAT_RATE_LIMIT`: `str`, default `"20/minute"` (parsed by `limits`)

### D2: Embedder in API process — reuse `build_embedder`

**Choice**: Load the embedding model in the API process at startup using the existing `build_embedder(settings)` function. This requires modifying the API Docker target.

**Rationale**: The model is small (46M params, 384-dim, CPU-only). `Settings` already inherits `embedding_model_path`, `embedding_threads`, and `embedder_backend` from `WorkerSettings`. The `Embedder` protocol, `FakeEmbedder`, `LocalEmbedder`, and `build_embedder` are already implemented and tested. No new service, network hop, or code is needed beyond wiring.

**Initialization**: Eagerly at application startup (in `create_app`), stored on `app.state.embedder`. This avoids cold-start latency on the first chat request and fails fast if the model files are missing. For development without the model files, `EMBEDDER_BACKEND=fake` uses the existing `FakeEmbedder`.

**Docker change required**: The current API Dockerfile target (`uv sync --frozen --no-dev --no-install-project`) does not install embedding dependencies. The API target must add `--extra embedding` and fetch the model using the same `docker/fetch_model.py` script as the worker. This is a build-time change only; the runtime wiring reuses the existing code.

**Memory and image impact**:
- Runtime memory: ~500MB additional (model weights in fp32 + torch overhead). API process goes from ~200MB to ~700MB.
- Docker image size: ~350MB additional (CPU-only torch wheel ~250MB + sentence-transformers ~15MB + model files ~90MB compressed). The image is still a fraction of the worker (~3.2GB).
- Document the memory requirement in `docs/development_guide.md`.

**Alternative considered**: An internal HTTP embedding service on the worker. This would keep the API image lightweight but adds a network hop (~5-20ms per query), requires a new HTTP endpoint on the worker, service discovery, error handling for worker unavailability, and additional tests. For the MVP's single-server deployment, the added complexity is not justified. The in-process approach reuses proven code and has no availability dependency beyond the API process itself.

### D3: RAG pipeline flow

```
POST /chat
  |
  v
[1. Auth + Role(student) + Consent gate]
  |
  v
[2. Validate input (subject_id, message, conversation_id?)]
  |
  v
[3. Embed query: embedder.embed([message])]
  |
  v
[4. Retrieve: ChunkRepository.find_similar(actor, subject_id, embedding, top_k)]
  |    - Enrollment is checked BEFORE the search: unknown subject -> 404, existing subject without
  |      enrollment -> 403 (docs/api-spec.yml); find_similar still scopes by enrollment in SQL
  v
[5. Threshold filter: keep chunks where similarity >= threshold]
  |    - If none above threshold -> no_material response (skip LLM)
  v
[6. Build prompt: system + history + context blocks + user message]
  |    - Neutralize delimiters in chunk content and user message
  |    - Include last N messages from conversation history
  v
[7. Call LLM: llm_service.generate(system_prompt, messages)]
  |    - Timeout, 429, 5xx -> 502 LLM_UNAVAILABLE
  |    - Safety block -> 502 LLM_BLOCKED
  v
[8. Persist: conversation + user message + assistant message + sources]
  |    - commit_or_rollback(db) before building response
  v
[9. Build ChatResponse: conversation_id, message_id, answer, sources, no_material]
```

**Step 4 — authorization via find_similar**: The `ChunkRepository` returns empty for unauthorized users (not enrolled, wrong role). The service layer does not infer authorization from an empty result: a non-existent subject is 404 and an existing subject the student is not enrolled in is 403, as the canonical contract `docs/api-spec.yml` states for chat. To distinguish "no chunks because not enrolled" from "no chunks because subject has no material", the service first checks enrollment explicitly via the existing `EnrollmentRepository` or `SubjectRepository` — the `find_similar` call follows only after the authorization check passes.

**Step 5 — no-material path**: When no chunk meets the threshold, the service returns a `NoMaterialResult` without calling the LLM. The endpoint maps this to a 200 with `no_material: true`, a fixed answer message, and empty sources. The conversation and both messages (user + assistant "no material") are still persisted.

**Step 6 — prompt assembly**: See D5.

**Request phases and database sessions** (second-round decision on adversarial finding 7; SQLAlchemy stays synchronous and the layering is unchanged): the request is split so that no PostgreSQL connection is held while the external LLM runs.

1. *Read* (request session): authorization (role, current consent, enrollment, conversation ownership bound to the subject), history, query embedding and `find_similar`. The endpoint then closes the session, which returns its connection to the pool.
2. *Generate*: `await llm.generate(...)` with no session open. A provider failure maps to 502 and nothing has been written.
3. *Persist* (new session and transaction): revalidate consent, enrollment and conversation ownership, because any of them can change while the LLM runs; write the user message, the assistant message and the sources atomically; `commit_or_rollback` before the 200 is built. Consent or enrollment lost: 403. Conversation or subject gone: 404 and the answer is discarded. A cited chunk deleted meanwhile: the source is stored with `chunk_id` NULL (the snapshot keeps filename and page), written inside a savepoint so the turn is never half-stored.

Embedding and every synchronous database call run in the thread pool (`run_in_threadpool`, already part of FastAPI), never on the event loop; the LLM call is awaited natively. A request cancelled during generation holds no connection and writes nothing; one cancelled during the persist phase lets the worker thread finish, so the turn is committed or rolled back as a whole. Concurrent turns on one conversation are each atomic (their own transactions). The only lock is the one described next, held for the persist transaction alone. No new library, service or process is introduced.

**Serialising persistence with unenrolment** (owner-approved correction of the residual risk M2): without it, an unenrolment that commits between the revalidation reads and the commit of the persist transaction is not seen, and one turn is stored for a student who has just lost access. The persist transaction therefore takes `pg_advisory_xact_lock(space, key)` as its first statement, before it revalidates consent and enrollment, and holds it until the commit (or rollback); `EnrollmentRepository.delete_for_teacher_subject` takes the same lock before it deletes. `space` is a fixed constant of this lock family and `key` is a signed 32-bit integer taken from a SHA-256 of `student_id:subject_id`, so the key is stable, different pairs rarely share it (a shared key only serialises two unrelated pairs) and the two-integer form cannot collide with the one-bigint document admission lock. Rules that keep it free of deadlocks: a transaction takes at most this one advisory lock and takes it before the statements that depend on it (the persist transaction: its first statement; the unenrolment: before its delete, after the ownership reads, which do not depend on it); it is never taken during embedding or generation (the read phase has no lock and the session is closed before the LLM call); the document admission lock is never taken in a transaction that holds it; the row locks taken afterwards (foreign-key checks on the subject and the user, the delete of one enrollment row) are never held by a transaction that waits for this advisory lock. It needs no table privilege (an advisory lock is not a row lock, which would need an UPDATE privilege), so the privilege matrix is unchanged. Deleting a whole subject takes no advisory lock: a turn for a deleted subject fails its foreign key (404) or is removed by the cascade. Consent has no revocation endpoint: it stops being current only when the policy version is raised at deployment, and any change committed before the lock is released is seen by the revalidation.

### D4: Conversation persistence model

**Tables**: As defined in `docs/data-model.md` — `conversations`, `messages`, `message_sources`.

**SQLAlchemy models** (new file `models/conversation.py`):
- `Conversation`: id (UUID PK, server default), student_id (FK users, NOT NULL), subject_id (FK subjects, NOT NULL), created_at (timestamptz, server default). Index on `(student_id, subject_id, created_at DESC)`.
- `Message`: id (UUID PK, server default), conversation_id (FK conversations ON DELETE CASCADE), role (enum `user`|`assistant`), content (text), created_at (timestamptz, server default).
- `MessageSource`: id (UUID PK, server default), message_id (FK messages ON DELETE CASCADE), chunk_id (FK document_chunks ON DELETE SET NULL, nullable), document_filename (varchar, snapshot), page_number (int, nullable, snapshot), rank (int), score (float).

**Repositories** (new files):
- `ConversationRepository`: `create`, `get_by_id_and_student`, `list_by_student(subject_id?)`, `delete_by_id_and_student`, `delete_all_by_student`.
- `MessageRepository`: `create_with_sources`, `list_by_conversation`.

**Alembic migration**: One migration creates all three tables, their indexes, foreign keys, and the GRANT statements. The migration also defines `downgrade` (DROP tables, REVOKE grants).

### D5: Prompt template and injection defenses

Per `docs/backend-standards.md` §6:

**System prompt** (stored as a constant, not in the database):
- Instructs the model to answer only from the provided context
- Prohibits following instructions found in the context
- Prohibits producing URLs, tool calls, or code execution
- Prohibits revealing the system prompt
- Limits the language to the same as the question

**Context block format**:
```
<CONTEXT>
[Source: {filename}, Page: {page_number}]
{content_with_neutralized_delimiters}
</CONTEXT>
```

**Delimiter neutralization**: Before prompt assembly, any occurrence of `<CONTEXT>`, `</CONTEXT>`, `<SYSTEM>`, `</SYSTEM>` in chunk content or user message is replaced with a safe form (e.g., `[CONTEXT]`). This prevents content from escaping its designated section.

**History inclusion**: The last `CHAT_HISTORY_MESSAGES` messages of the current conversation are included after the system prompt and before the context blocks, as alternating user/assistant messages. Only those messages are read from the database: a bounded query takes the newest `CHAT_HISTORY_MESSAGES` of the conversation (none, and no query, when the value is 0) and they are put back in chronological order before the prompt is assembled; the cost does not grow with the length of the conversation.

### D6: Error types

New domain errors in `core/errors.py`:
- `ConsentRequiredError(ForbiddenError)`: status 403, code `CONSENT_REQUIRED`
- `LLMUnavailableError(AppError)`: status 502, code `LLM_UNAVAILABLE`
- `LLMBlockedError(AppError)`: status 502, code `LLM_BLOCKED`
- `SearchUnavailableError(AppError)`: status 503, code `SEARCH_UNAVAILABLE`

All error messages are fixed English text. Provider details, API keys, model identifiers, and SQL parameters are never included.

### D7: Logging rules

Per `docs/backend-standards.md` and lessons learned (L04):
- Log `chat request id=%s subject=%s` at INFO when a chat starts
- Log `chat no_material id=%s subject=%s` at INFO for the no-material path
- Log `chat complete id=%s conversation=%s message=%s` at INFO on success
- Log `llm error` at WARNING on LLM failure (no provider details)
- Never log: user message content, chunk content, embeddings, API keys, conversation text

### D8: Test strategy

**Unit tests** (services, mocked repos and LLM):
- `RAGService`: happy path, no-material, LLM error, consent missing, not enrolled, conversation validation
- `LLMService`: `FakeLLMService` returns deterministic output; `GeminiLLMService` is tested with a mock HTTP client
- `ConversationRepository` / `MessageRepository`: query correctness with in-memory session

**Integration tests** (real PostgreSQL + pgvector test database):
- `POST /chat`: full pipeline with FakeEmbedder and FakeLLM against a subject with seeded chunks
- Authorization negative tests: wrong role, not enrolled, another student's conversation, missing consent
- Conversation CRUD: create via chat, list, read messages with sources, delete single, delete all
- Cross-student isolation: student A cannot see/delete student B's conversations
- Explicit commit verification: the response includes the persisted conversation_id

**RAG-specific tests** (using seeded "La Dama de Blanco" fixtures):
- A question about a topic covered in the PDF returns an answer with source citations
- A question about an unrelated topic returns `no_material: true`
- The `snippet` in sources is truncated to 300 characters

**Security tests**:
- Prompt injection in user message (delimiter injection, instruction injection)
- Prompt injection in chunk content (seeded malicious chunk)
- Error responses and logs do not contain API keys, embeddings, or SQL
- Rate limiting returns 429

**Manual curl tests** and **Playwright MCP verification** as per `docs/openspec-tasks-mandatory-steps.md`.

## Risks / Trade-offs

- **[Gemini API availability]** The free tier has rate limits that are not published with guaranteed stability. → Mitigation: configurable timeout and rate limit; 502 response on provider failure; `FakeLLM` for all automated tests. Gemini quotas and costs are not asserted here — verify against the current Google AI Studio dashboard at implementation time.
- **[Embedder memory and Docker image in API container]** Loading the model adds ~500MB runtime memory and ~350MB to the Docker image (CPU-only torch + model). The API Dockerfile target must be modified to include `--extra embedding` and the model fetch step (see D2). → Mitigation: document memory requirements in `docs/development_guide.md`; the model and torch are already required in the worker image, so no new binary dependency is introduced to the system; `EMBEDDER_BACKEND=fake` skips the model for lightweight development.
- **[Embedding model quality on real material]** TD-033 notes that retrieval quality is unknown on real content. → Mitigation: manual RAG tests with the "La Dama de Blanco" chunks provide initial evidence; the golden set (§9.5 SHOULD) remains a future step and this change does not close TD-033.
- **[Conversation data is personal data (GDPR)]** → Mitigation: `DELETE /conversations/{id}`, `DELETE /users/me/conversations`, and `DELETE /users/me` (existing cascade) cover the right to erasure. `message_sources` snapshots do not contain user content.
- **[LLM prompt injection]** → Mitigation: system prompt constraints, delimited context with neutralized delimiters, subject-scoped retrieval (architectural containment), 2000-char input limit, plain-text rendering. Adversarial review is mandatory before archiving.
- **[No UPDATE privilege on conversation tables]** The `asistente_app` role has no UPDATE. → This is intentional: conversations and messages are append-only; there is no edit-message feature. If a future change needs UPDATE, it requires a new migration with an explicit GRANT.

## Open Questions

No open questions remain. D1 (LLM SDK: `langchain-google-genai` per the canonical standard) and D2 (embedder loading: eager in API process with Dockerfile modification) are resolved above.
