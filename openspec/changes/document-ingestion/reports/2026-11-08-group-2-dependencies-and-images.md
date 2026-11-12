# Group 2: configuration, dependencies and images

Date: 2026-11-08. Branch `feature/document-ingestion`. Tasks 2.1, 2.2 and 2.3. Settings evidence: `2026-11-08-tdd-evidence.md`.

## Definitive versions (task 2.2)

Re-verified on 2026-11-08 against the PyPI metadata (including its vulnerability field) and the GitHub security advisories of both projects, not from summaries.

| Package | Pin | Published | Evidence |
|---|---|---|---|
| `pypdf` | `==7.0.0` (**definitive**; 6.21.4 stays the fallback) | 2026-11-06 | The full advisory list (all published entries) was read. Every entry is patched in 7.0.0 or earlier. Five entries are patched only in 7.0.0 (GHSA-mwj3-fpmc-hjcv file identifier, GHSA-rfv5-695j-j993 image formats, GHSA-59jv-x5x2-gg4c cross-reference streams, GHSA-cmpx-464x-82c3 XFA forms, GHSA-g7p9-v9rc-c6rj image operations), so 6.21.4 is still affected by them. PyPI lists no vulnerability for 7.0.0. Python 3.12 is supported. Same behaviour as 6.21.4 on the 18 hostile fixtures of the spike |
| `python-multipart` | `==0.0.33` | 2026-10-31 | 9 advisories, the latest patched in 0.0.31 (negative `Content-Length`); 0.0.33 is above all of them |
| `langchain-text-splitters` | `==1.1.3` | 2026-10-02 | no advisories; brings `langchain-core` (and through it `langsmith` and `httpx2`) |
| `sentence-transformers` | `==6.2.0` | 2026-10-21 | no advisories; needs `transformers` 5 (locked 5.22.2) |
| `torch` | `==2.15.0` (CPU wheel `2.15.0+cpu` on Linux, PyPI wheel elsewhere) | 2026-10-28 | no advisories on PyPI; the local `+cpu` version cannot be audited by `pip-audit` |

Layout in `backend/pyproject.toml`: `python-multipart` in the main dependencies (FastAPI cannot register a file route without it); optional groups `ingestion` (`pypdf`, `langchain-text-splitters`) and `embedding` (`sentence-transformers`, `torch`); `torch` mapped to the PyTorch CPU index only for `sys_platform == 'linux'`; mypy overrides for `sentence_transformers`, `torch` and `transformers`.

Lock (`uv lock`): **additive only** (no existing package changed version or was removed); 126 packages resolved; **no occurrence of `nvidia` or `cuda`** in `uv.lock`; the lock holds both `torch 2.15.0` (Windows, macOS) and `2.15.0+cpu` (Linux).

### Finding: `httpx2` changes the test client types
`langchain-core` brings `langsmith`, which brings `httpx2`. Starlette 1.10's `TestClient` uses `httpx2` when it is installed and `httpx` only as a deprecated fallback, so `mypy --strict` reported 6 errors (`httpx2.Response` against `httpx.Response`) as soon as the `ingestion` group was installed. Fix: `httpx2>=2.16` joins the `dev` group so the test client does not depend on which optional group is installed, and four test files import `Response` from `httpx2`. The unit suite warnings went from 2 to 1; the full suite (795 passed) still reports 2 warnings, both pre-existing.

## Audit

- `uv run pip-audit` on the synced environment: no known vulnerabilities.
- `uv export` of the whole lock with both groups (359 lines, platform markers included), audited with `pip-audit --no-deps --disable-pip` without the `+cpu` line: no known vulnerabilities. That line is the same upstream release as the audited `torch 2.15.0`.
- Limit: `pip-audit` data lags the advisories (it did not flag `pypdf` 6.21.4 in the spike), which is why the GitHub advisories were read directly.

## Images (task 2.3)

Built with `docker compose build backend` and `docker compose --profile worker build worker`. Sizes from `docker images`:

| Image | Size | Build |
|---|---|---|
| `asistenteia-backend` (target `api`) | **397 MB** (spike reference 362 MB) | 1 min 14 s |
| `asistenteia-worker` (target `worker`) | **3.22 GB** (spike reference 2.80 GB) | 7 min 43 s, after two failed attempts (see below) |

Worker layers: base `python:3.12-slim` and `uv` about 230 MB, virtual environment 1.6 GB (`torch` 809 MB, `scipy` 109 MB, `transformers` 120 MB, `sympy` 74 MB), model layer 488 MB (463 MB on disk, 11 files verified by SHA-256 at build), project 0.7 MB. The reported size exceeds the spike value by about 0.4 GB; the difference is attributed to `UV_COMPILE_BYTECODE=1` (bytecode next to every module), which the spike image did not use, and to `langchain-core` with its dependencies. It is a reference, not a gate (user decision); dropping the bytecode compilation would be the first reduction to try.

Checks in the images:
- `worker`, started with `--network none --cpus 2 --memory 2g`: runs as uid 10001; `HF_HUB_OFFLINE=1`; `detect_cpu_quota()` returns **2** under `--cpus 2` and `torch` is set to 2 threads; the model loads offline in 1.0 s, returns shape `(2, 384)` and `max_seq_length` 128; `torch 2.15.0+cpu` with no CUDA; `pypdf 7.0.0`; no `nvidia` package.
- `api`: `torch`, `pypdf`, `sentence_transformers` and `langchain_text_splitters` are **absent**; `multipart` is present. A container from this image on the Compose network (free port 18080, removed afterwards) answered `GET /api/v1/health` with `200`.
- `docker compose config` is valid with and without the `worker` profile.

Build incidents: the first two `worker` builds failed with `dns error: failed to lookup address information` in the middle of `uv sync` (50 parallel downloads by default); host and container DNS resolved normally afterwards. `UV_CONCURRENT_DOWNLOADS=4` and `UV_HTTP_TIMEOUT=120` were added to the `worker` stage and the third build succeeded.

## Deviations and decisions

1. **Compose `worker` service behind the `worker` profile.** The command `python -m app.worker` does not exist until group 8; without the profile `docker compose up` would start a container that exits in a loop. The profile is removed in group 8 (task 8.2 records it); until then `docker compose --profile worker up -d worker` starts it. The service has `cpus: 4` and `mem_limit: 2g`, `EMBEDDING_THREADS` unset, the same env file, no ports and a dependency on a healthy `db`.
2. **No failing-first test for 2.2 and 2.3** (configuration and build files); compensated by the checks above.
3. The Compose `backend` service now names `target: api`; its command and environment are unchanged. The Windows development flow (`uv sync` without the extras) is unaffected.
4. CI installs the `ingestion` group only (`uv sync --frozen --extra ingestion`), as designed; the real model is not installed in CI.
5. **The full stack was not started with `docker compose up`** (the frontend and the Compose `backend` publish ports 8000 and 5173, which this group must not use). Instead, the `db` service stayed up and healthy, the `api` image was started through `docker compose run` on port 18080 and answered `/api/v1/health` with `200`, and the `worker` image was exercised with `docker run`. Starting the whole stack with the worker belongs to group 17 (task 17.5).
6. Group 0 (tasks 0.1 to 0.3: branch check, baseline report, verbatim prompt record) has not been authorised or executed; this group did not depend on it.

## Verification

- `ruff check`, `ruff format --check`, `mypy --strict app tests`: clean (110 source files).
- Unit suite: 372 passed. Full backend suite against the real test database: **795 passed** (712 previous plus 83 new), `asistenteia_test` left empty.
- Not touched: `readme.md`, `prompts.md`, migrations, the databases (no migration was run; the tests use `asistenteia_test`), archived specs, skills, agents, and the OpenSpec and SpecBoot configuration.
