# Development Guide

How to set up the environment, run the stack and run quality checks for AsistenteIA.

> Status: **target workflow**. The repository has no application code yet; commands below become valid as the scaffolding tickets are implemented. When a command changes, update this guide in the same change.

## Prerequisites

- Docker and Docker Compose (primary, evaluated way to run the stack)
- Git
- For running tools outside Docker: Python 3.12 + `uv`, Node.js LTS + npm

## 1. Clone and configure

```bash
git clone https://github.com/supercentro/AsistenteIA.git
cd AsistenteIA
cp backend/.env.example backend/.env
cp frontend/.env.example frontend/.env
```

`.env.example` files document every variable with **placeholder** values. Generate real secrets locally and never commit them:

```env
# backend/.env  (example variables)
DATABASE_URL=postgresql+psycopg://asistente:CHANGE_ME@db:5432/asistenteia
JWT_SECRET=CHANGE_ME_32_BYTES_MINIMUM        # e.g. python -c "import secrets; print(secrets.token_urlsafe(48))"
JWT_EXPIRE_MINUTES=60
GEMINI_API_KEY=CHANGE_ME
GEMINI_MODEL=gemini-2.5-flash
EMBEDDING_MODEL=sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2
MAX_UPLOAD_MB=10
MIN_SIMILARITY=0.35
CORS_ORIGINS=http://localhost:5173
LLM_PROVIDER=gemini            # "fake" in tests/E2E

# frontend/.env
VITE_API_URL=http://localhost:8000/api/v1
```

## 2. Run the full stack

```bash
docker compose up --build
```

Services: `db` (PostgreSQL 15 + pgvector), `backend` (FastAPI, :8000, docs at `/docs`), `frontend` (Vite, :5173).
The first build downloads the embedding model (large image; expect several minutes). The model cache is a Docker volume so it is downloaded once.

## 3. Database

```bash
docker compose exec backend alembic upgrade head      # apply migrations
docker compose exec backend alembic downgrade -1      # revert last migration
docker compose exec backend python -m app.cli seed    # demo teacher, student, subject (development only)
docker compose exec backend python -m app.cli create-teacher --email you@example.com   # prompts for a password
```

Create migrations with `alembic revision --autogenerate -m "describe change"` and **review** the generated file; every migration needs a working `downgrade`.

## 4. Quality commands

Backend (from `backend/`):

```bash
uv sync
uv run ruff check . && uv run ruff format --check .
uv run mypy --strict app
uv run pytest tests/unit
uv run pytest tests/integration --cov=app --cov-report=term-missing   # needs the db service
```

Frontend (from `frontend/`):

```bash
npm ci
npm run lint && npm run format:check && npm run typecheck
npm test
npm run test:e2e        # Playwright Test (committed suite); starts backend with LLM_PROVIDER=fake
```

## 5. Branching and commits

- `main` is the integration branch and is never committed to directly once implementation starts.
- Implementation: one branch `feature/<change-name>` per OpenSpec change, created from `main` and merged back through a Pull Request. Conventional commits (`feat:`, `fix:`, `docs:`, `test:`, `chore:`) in English.
- Course delivery branches (`feature/entrega-N-AN`, `final-project-AN`) are cut from `main` only when submitting a delivery; see `academic-requirements.md` §3 and §9.
- Before committing, review which docs must be updated (see `documentation-standards.md`).

## 6. Continuous integration (planned)

GitHub Actions: lint + type-check + unit and integration tests (PostgreSQL service with pgvector) + frontend tests + build. Gemini is never called in CI.

## 7. Troubleshooting

- `extension "vector" is not available`: the database image must be a pgvector-enabled image (e.g. `pgvector/pgvector:pg15`).
- Backend starts slowly the first time: embedding model download; check the model cache volume.
- Gemini 429/blocked responses locally: switch `LLM_PROVIDER=fake` to keep developing without the API.
