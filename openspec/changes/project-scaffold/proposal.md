# Proposal

## Why

The repository contains only documentation (readme, `docs/`, `ai-specs/`); there is no backend, frontend or database to build the approved MVP on. Every later change (auth, subjects, documents, RAG chat, GDPR deletion) needs a runnable, tested and reproducible base: layered backend skeleton, frontend skeleton, a pgvector-enabled database with a migration pipeline, and automated quality gates. This change creates that base and nothing else, so the following 12 changes can be small and verifiable.

## What Changes

- Backend skeleton (`backend/`): FastAPI app following the layered structure of `docs/backend-standards.md` §2, typed settings from environment variables, domain errors mapped to the common `Error` schema, CORS restricted to configured origins, secure response headers, a per-request transaction dependency, and `GET /api/v1/health`.
- Database foundation: PostgreSQL 15 with `pgvector`, synchronous SQLAlchemy 2.x, Alembic with a first migration that enables the `vector` extension (working `downgrade`).
- Frontend skeleton (`frontend/`): React 18 + TypeScript strict + Vite + Tailwind, the folder layout of `docs/frontend-standards.md` §2, routing and server-state providers, a Spanish UI-strings module, and the expected npm scripts.
- Tooling and gates: ruff, mypy `--strict`, pytest (unit + integration against real PostgreSQL), ESLint, Prettier, Vitest + React Testing Library + MSW, Playwright Test configured with a smoke spec, lock files committed.
- Safety: environment-aware settings (no open CORS in production) and a guard that restricts migrations and destructive cleanup in tests to a dedicated `*_test` database.
- Reproducibility: `docker compose up` starts `db`, `backend` and `frontend`; `.env.example` files with placeholder values.
- GitHub Actions workflow running lint, type-check, tests and build on push/PR, with no call to Gemini.
- Docs updated where this change makes them true or more precise (`docs/development_guide.md`, `docs/api-spec.yml` for `/health`).

**Out of scope** (belongs to later changes, confirmed inside the approved MVP): users/auth/JWT, any business table, subjects, enrollments, documents, chunks, embeddings, LangChain, Gemini integration, chat, conversations, consent, GDPR deletion, seed/CLI commands, the committed end-to-end flow, and deployment to Vercel/Render/Supabase. No features beyond the approved MVP are added.

## Capabilities

### New Capabilities
- `service-health`: public liveness and database-connectivity endpoint.
- `api-error-handling`: uniform error body, no leakage of internals, CORS and secure-header behaviour of the HTTP API.
- `dev-environment`: reproducible local stack (`docker compose up`), environment configuration, and a database migration pipeline that works on a clean pgvector database.
- `continuous-integration`: automated quality gates on every push/PR without external services.

### Modified Capabilities
<!-- None: openspec/specs is empty. -->

## Impact

- **New code**: `backend/`, `frontend/`, `docker-compose.yml`, `.github/workflows/ci.yml`, `.env.example` files.
- **Authorization / data isolation / GDPR / Gemini**: no impact yet. No user data, no auth and no external service exist after this change. The scaffold only lays the foundations that later changes rely on (per-request transaction, error mapping, no content in logs, env-only secrets).
- **`docs/api-spec.yml`**: document `GET /health` failure response (503) and the generic `Error.code` values; see design D8.
- **`docs/data-model.md`**: unchanged (no tables yet; the first migration only enables the `vector` extension).
- **`docs/development_guide.md`**: adjust commands that become real (and note that the embedding model is not part of this change's image).
- **Dependencies**: Python runtime/tooling packages and frontend tooling listed in the design; heavy ML dependencies (sentence-transformers, torch, LangChain, Gemini client) are deliberately deferred.
- **Architecture-affecting decisions to approve**: see `design.md` (D1–D10), notably sync SQLAlchemy (already approved), `psycopg` 3 driver, deferral of ML dependencies, and the 503 behaviour of `/health`.
