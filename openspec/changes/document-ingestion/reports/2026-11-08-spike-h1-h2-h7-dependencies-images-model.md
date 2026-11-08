# Spike H1, H2 and H7: dependencies, images, model download and advisories

Date: 2026-11-08. Spike executed for tasks 1.1, 1.2 and 1.7 of `tasks.md`. Everything ran outside the repository in disposable containers (label `spike=document-ingestion`, names `f6spike-*`), with no ports published and without touching the Compose services, the databases `asistenteia` and `asistenteia_test`, or ports 8000, 5173 and 5442. Scripts are in `reports/spike-scripts/`. Environment: Docker Desktop 29.8.0 (16 CPUs, 16 GB), base image `python:3.12-slim` (177 MB), `uv` 0.12.9.

## H1. Dependencies and image sizes

Versions that installed together on Python 3.12 (Linux): `fastapi` 0.162.0, `starlette` 1.10.0, `uvicorn` 0.54.0 (the project lock), `python-multipart` 0.0.33, `pypdf` 6.21.4 and 7.0.0 (two separate images), `sentence-transformers` 6.2.0, `transformers` 5.22.2, `tokenizers` 0.23.3, `torch` 2.15.0+cpu, `numpy` 2.5.4, `scipy` 1.18.1, `scikit-learn` 1.9.1, `safetensors` 0.8.0, `langchain-text-splitters` (1.1.3 in the lock experiment).

| Image | Content | Size (`docker image inspect`) | Cold build |
|---|---|---|---|
| `api` | project lock + `python-multipart`, no ML | **362 MB** | 9 s |
| `worker`, CPU `torch` from the PyTorch CPU index | + `pypdf`, splitters, `sentence-transformers` | **1.91 GB** (layers: `torch` 844 MB, `sentence-transformers` and dependencies 383 MB) | 2 min 12 s |
| `worker`, default PyPI `torch` (CUDA wheels) | same | **9.38 GB** (one layer of 5.99 GB) | 20 min 40 s |
| `worker` final candidate: no `uv` cache, `pypdf` 7.0.0, model baked at build, non-root user 10001 | see `Dockerfile.worker-final` | **2.80 GB** reported; contents measured with `du`: virtual environment 1.2 GB, model 463 MB, base 177 MB | 2 min 1 s including the model download |

Findings:
- The CPU `torch` index is **mandatory**: the default wheel makes the worker image five times larger and the build ten times slower, and it pulls CUDA packages that the CPU-only worker never uses.
- Without `UV_NO_CACHE`, the first worker images kept a 1.3 GB `uv` cache in `/root/.cache`; the final Dockerfile removes it. The remaining gap between the reported size (2.80 GB) and the measured contents (about 1.9 GB) comes from layers that are written twice (two `uv pip install` steps); merging the steps into one `RUN` is a possible reduction that was not measured.
- Lock resolution (copy of `pyproject.toml` with `python-multipart==0.0.33`, optional groups `ingestion` and `embedding`, and the index mapped for Linux only): `uv lock` took 3 s; `uv.lock` grew from 156,295 to 239,358 bytes; the lock holds `torch` 2.15.0 wheels for Windows (`win_amd64`) and macOS (`arm64`) and `2.15.0+cpu` for Linux. `uv sync --frozen --no-dev` without extras installs none of `torch`, `pypdf` or `sentence-transformers` (the API target stays light); with the extras it installs `pypdf==7.0.0`, `sentence-transformers==6.2.0` and `torch==2.15.0+cpu`. Not tested: PEP 735 dependency groups instead of optional dependencies.

Gate for the user: image sizes (362 MB and 2.8 GB) and build times are presented in the summary.

## H2. Model: fixed revision, reproducibility, offline run

- Repository `sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2`, revision **`e8f8c211226b894fcb81acc59f3b34ba3efd5f42`**, license **Apache-2.0** (from the hub metadata).
- Files needed (11 files, 484,798,061 bytes): `model.safetensors` 470,641,600 bytes, `tokenizer.json` 9,081,518, `sentencepiece.bpe.model` 5,069,051 and small configuration files. Not downloaded: the ONNX, OpenVINO, TensorFlow and `pytorch_model.bin` copies (each 118 to 471 MB).
- **Reproducible:** two downloads of the pinned revision into different directories gave identical SHA-256 for every file (132 s and 413 s; the time depends on the network). SHA-256 of the files (size, hash): `model.safetensors` (470,641,600) `eaa086f0ffee582aeb45b36e34cdd1fe2d6de2bef61f8a559a1bbc9bd955917b`; `tokenizer.json` (9,081,518) `2c3387be76557bd40970cec13153b3bbf80407865484b209e655e5e4729076b8`; `sentencepiece.bpe.model` (5,069,051) `cfc8146abe2a0488e9e2a0c56de7952f7c11ab059eca145a0a727afce0db2865`; `1_Pooling/config.json` `4be450dde3b0273bb9787637cfbd28fe04a7ba6ab9d36ac48e92b11e350ffc23`; `config.json` `6300193cb75e01cf80c96decef7187dfb33094d97cc1490b7ead6ff134476e4e`; `config_sentence_transformers.json` `b8c64b5cece00d8424b4896ea75b512b6008576088497609dfeb6bd63e6d36b8`; `modules.json` `8f4b264b80206c830bebbdcae377e137925650a433b689343a63bdc9b3145460`; `sentence_bert_config.json` `70f4448f31320443fe3557cacea5abf2dcc4915dda8c80646bec9f3bb0aa5a1f`; `special_tokens_map.json` `378eb3bf733eb16e65792d7e3fda5b8a4631387ca04d2015199c4d4f22ae554d`; `tokenizer_config.json` `5036ea374ffedd706e3bef33e2e0d6953cb868ef8a490e76e32ba0faa37a6b9b`; `README.md` `1e98ea05b0de579fcaad3d625b62ea55647142ed674d5f5ebf1440e4bbbb6f23`.
- **Offline:** in a container with `--network none` and the hub set offline, a connection attempt failed (`gaierror`) and the model loaded and embedded text. Load time 4.4 s (RSS 449 to 797 MB, peak 850 MB); in the final non-root image 10.4 s the first time (cold file cache). First `encode` 5.0 s (warm-up). `get_sentence_embedding_dimension()` = **384**, `max_seq_length` = **128**; the probe vector norm was 4.62.
- Tokenizer: special tokens add exactly 2 to every count (Spanish prose 20 and 22; a long word 35 and 37; URL 34 and 36; digits 32 and 34; emoji 20 and 22; CJK 18 and 20; right-to-left 16 and 18).
- The model card states 50 languages without listing them; Spanish retrieval was measured in H4 (not assumed).

## H7. Versions, changelogs and security audits

Read on 2026-11-08 (through fetched pages; partly summaries, so figures to be re-verified when the dependencies are added):

| Package | Version | Published | Notes |
|---|---|---|---|
| `pypdf` | 7.0.0 | 2026-11-06 | major; changelog lists security work: non-deterministic file identifiers, blocking non-increasing offsets in object streams, limiting XFA decoding work, stricter image size limits; drops Python 3.9, requires `cryptography>=43` for the `crypto` extra; no removed API named |
| `pypdf` | 6.21.4 | 2026-10-28 | last 6.x; security items: limit copied page attributes, EOF detection in xref trailer, loop detection when cloning dictionaries |
| `python-multipart` | 0.0.33 | 2026-10-31 | requires Python 3.11+; the project's advisories list (9 entries, latest 2026-06-04) names memory or CPU denial of service issues, ranges not read |
| `sentence-transformers` | 6.2.0 | 2026-10-21 | no published advisories |
| `langchain-text-splitters` | 1.1.3 | 2026-10-02 | depends on `langchain-core` |

- `pypdf` published ten advisories between 2026-10-17 and 2026-11-06 (first page of eight read): infinite loops (xref EOF, cloning dictionaries), memory use (xref streams with identical offsets, XFA, images, page tree, strict-mode exceptions), long runtimes (page labels). Four were published on 2026-11-06 together with 7.0.0.
- `pip-audit` (run inside each image, vulnerability service reachable): **no known vulnerabilities** for the `api` image, for the `worker` with `pypdf` 6.21.4 and for the `worker` with `pypdf` 7.0.0. `torch 2.15.0+cpu` cannot be audited because the local version does not exist on PyPI (reported as skipped). `pip-audit` does not flag 6.21.4 although the advisories above were published two days earlier: the audit data lags behind, so the audit alone is not a reason to stay on 6.x.
- Behaviour of both `pypdf` versions on the hostile corpus is identical (see `2026-11-08-spike-h6-pdf-limits.md`).

Recommendation: pin `pypdf==7.0.0` (contains the published fixes; verify again when the dependency is added, and read advisories 11 to 80), `python-multipart==0.0.33`, `sentence-transformers==6.2.0`, `langchain-text-splitters==1.1.3`, `torch` 2.15.0 CPU wheel for Linux. Risk: a major published two days earlier; fall back to 6.21.4 (same behaviour on the corpus) if a regression appears.
