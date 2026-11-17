# Proposal

## Why

The MVP requires enrolled students to ask questions about their subjects and receive answers grounded in the uploaded course material, with verifiable citations. The backend already processes documents into searchable chunks with embeddings (25 chunks from "La Dama de Blanco" are ready), and `ChunkRepository.find_similar` provides authorized, subject-scoped vector search. However, no HTTP endpoint exposes the RAG pipeline and no conversation persistence exists. Without `POST /chat`, the system has material it can search but no way for a student to ask a question — this is the core value proposition of the product.

## What Changes

- **RAG chat endpoint** (`POST /chat`): an authenticated endpoint that embeds the student's query, retrieves the most relevant chunks from the subject's material, checks a configurable relevance threshold, builds a grounded prompt, calls the LLM (Gemini 2.5 Flash via API), persists the conversation and sources, and returns the answer with verifiable citations. When no chunk meets the threshold, a controlled "no material" response is returned without calling the LLM.
- **Consent enforcement**: `POST /chat` gates on current privacy-policy consent (closing TD-003); a student without consent receives 403 `CONSENT_REQUIRED`.
- **Conversation persistence**: three new database tables (`conversations`, `messages`, `message_sources`) as already defined in `docs/data-model.md`, with an Alembic migration and privilege grants following the least-privilege model.
- **Conversation management endpoints**: `GET /conversations`, `GET /conversations/{conversation_id}/messages`, `DELETE /conversations/{conversation_id}`, `DELETE /users/me/conversations` — all student-only, as defined in `docs/api-spec.yml`.
- **LLM integration**: new dependency `langchain-google-genai` (per `docs/backend-standards.md` §1) with `FakeLLM` for tests; `GOOGLE_API_KEY` as a new `SecretStr` setting. External calls to Gemini never happen in CI.
- **Embedder in API process**: the local embedding model (paraphrase-multilingual-MiniLM-L12-v2, 384-dim, CPU) is loaded in the API process for query embedding, reusing the existing `Embedder` protocol and `build_embedder`.
- **Prompt-injection defenses**: system prompt with constraints, delimited context blocks, neutralized delimiters, subject-scoped retrieval, 2000-char user input limit — all per `docs/backend-standards.md` §6.
- **Error handling**: `LLM_UNAVAILABLE` (502) for LLM timeout/429/5xx, `LLM_BLOCKED` (502) for safety blocks, `SEARCH_UNAVAILABLE` (503) for vector-search failures, `CONSENT_REQUIRED` (403) for missing consent.

## Capabilities

### New Capabilities

- `rag-chat`: The core RAG answering pipeline — query embedding, subject-scoped retrieval with relevance threshold, grounded LLM generation with citations, no-material controlled response, consent gate, prompt-injection defenses, and LLM error handling.
- `conversation-history`: Persistence and management of student conversations — creation on first chat message, message listing with sources, conversation listing by subject, single and bulk deletion, data isolation by student.

### Modified Capabilities

_None._ Existing capabilities (`chunk-retrieval`, `privacy-consent`, `role-based-access`) are consumed but their spec-level requirements do not change. The `privacy-consent` spec explicitly states that consent enforcement in chat belongs to this change.

## Impact

- **API contract**: `docs/api-spec.yml` already defines `POST /chat`, `GET /conversations`, `GET /conversations/{id}/messages`, `DELETE /conversations/{id}`, `DELETE /users/me/conversations`, `ChatResponse`, `Conversation`, `Message`, and `Source` schemas. No changes to the API spec are expected; implementation must conform to the existing contract.
- **Data model**: `docs/data-model.md` already defines `conversations`, `messages`, and `message_sources` tables. No changes to the data model are expected. A new Alembic migration creates the tables and grants the appropriate privileges per the least-privilege model (`asistente_app`: SELECT/INSERT/DELETE; `asistente_cli`: SELECT/DELETE; `asistente_worker`: none).
- **Dependencies**: new Python package for Gemini LLM client; the embedder dependencies (`sentence-transformers`, `torch`) must now be available in the API container (they are currently only in the worker).
- **Configuration**: new environment variables — `GOOGLE_API_KEY` (SecretStr), `CHAT_TOP_K`, `CHAT_RELEVANCE_THRESHOLD`, `CHAT_HISTORY_MESSAGES`, `CHAT_LLM_TIMEOUT_SECONDS`, `CHAT_LLM_MODEL`, `CHAT_RATE_LIMIT`.
- **Authorization and data isolation**: chat is student-only with enrollment check (via `find_similar` authorization); conversations are isolated per student; `conversation_id` must match `subject_id`. GDPR: conversations contain personal data; the existing `DELETE /users/me` cascade and the new conversation deletion endpoints cover the right to erasure.
- **External services**: Gemini API (Google) is called on every chat request that passes the relevance threshold. Tests use `FakeLLM`; Gemini is never called in CI.
- **Security**: adversarial review is mandatory before archiving (this change touches chat/RAG, authorization, and personal data).

### Out of scope

- Frontend chat UI, subject management UI, document upload UI (separate changes).
- Streaming responses (future enhancement).
- Advanced retrieval strategies (reranking, HyDE, query expansion).
- Conversation title generation or summarization.
- Multi-subject queries.
- Token-level cost tracking or billing.
- Moodle integration, student-services assistant, advanced teacher analytics.

This change stays inside the approved MVP scope: RAG queries with sources, conversation history, and deletion of conversations.
