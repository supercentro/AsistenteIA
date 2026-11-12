# Two targets share the base: `api` (light, no machine learning) and `worker` (ingestion with the
# CPU-only torch wheel and the embedding model baked in). Build one with `--target api|worker`.
FROM python:3.12-slim AS base

COPY --from=ghcr.io/astral-sh/uv:0.12.9 /uv /usr/local/bin/uv

# The virtualenv lives outside /app so a bind-mounted source tree never shadows it.
# UV_NO_CACHE keeps the package cache (about 1.3 GB with torch) out of the image layers.
ENV UV_PROJECT_ENVIRONMENT=/opt/venv \
    UV_PYTHON_DOWNLOADS=never \
    UV_COMPILE_BYTECODE=1 \
    UV_NO_CACHE=1 \
    PYTHONUNBUFFERED=1 \
    PATH="/opt/venv/bin:$PATH"

WORKDIR /app

COPY pyproject.toml uv.lock .python-version ./


FROM base AS api

RUN uv sync --frozen --no-dev --no-install-project

COPY . .

RUN useradd --create-home --uid 10001 appuser
USER appuser

EXPOSE 8000
CMD ["uvicorn", "app.main:app_factory", "--factory", "--no-proxy-headers", "--host", "0.0.0.0", "--port", "8000"]


FROM base AS worker

# One RUN per install step: a repeated install would write the same files into two layers.
# The lock maps torch to the CPU-only index on Linux, so no CUDA packages are installed.
# Fewer parallel downloads (the default is 50) avoid intermittent DNS failures of Docker Desktop.
ENV UV_CONCURRENT_DOWNLOADS=4     UV_HTTP_TIMEOUT=120
RUN uv sync --frozen --no-dev --no-install-project --extra ingestion --extra embedding

# The model is fetched once, from a pinned revision and verified by hash, in its own layer. The
# worker then runs with the hub offline: nothing is downloaded at runtime.
COPY docker/fetch_model.py /opt/fetch_model.py
RUN python /opt/fetch_model.py /opt/models/paraphrase-multilingual-MiniLM-L12-v2 \
    && rm /opt/fetch_model.py

ENV HF_HUB_OFFLINE=1 \
    TRANSFORMERS_OFFLINE=1 \
    EMBEDDING_MODEL_PATH=/opt/models/paraphrase-multilingual-MiniLM-L12-v2

COPY . .

RUN useradd --create-home --uid 10001 appuser
USER appuser

CMD ["python", "-m", "app.worker"]
