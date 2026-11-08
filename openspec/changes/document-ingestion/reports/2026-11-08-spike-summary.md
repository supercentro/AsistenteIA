# Spike summary (H10): results, recommendations and decisions for the user

Date: 2026-11-08. Task 1.10. Branch `feature/document-ingestion`, planning commit `67f950c`, PR #8 (open, not merged). The spike changed nothing in the repository except these reports and `reports/spike-scripts/`. Detailed evidence: `2026-11-08-spike-h1-h2-h7-dependencies-images-model.md`, `2026-11-08-spike-h3-h4-h5-embedding.md`, `2026-11-08-spike-h6-pdf-limits.md`, `2026-11-08-spike-h8-h9-bytea-and-http.md`.

## Result per hypothesis

| H | Result | Note |
|---|---|---|
| H1 dependencies and images | **Holds** | Everything installs together; `api` image 362 MB, `worker` image 2.8 GB with the model baked (CPU `torch`); the default `torch` makes it 9.4 GB; `uv lock` resolves with a Linux-only CPU index |
| H2 model | **Holds** | Fixed revision `e8f8c211226b894fcb81acc59f3b34ba3efd5f42`, identical hashes in two downloads, loads and runs with no network, 384 dimensions, `max_seq_length` 128, Apache-2.0 |
| H3 CPU and RAM | **Holds, with a mandatory rule** | 40, 27 and 17 chunks/s with 4, 2 and 1 CPUs (2,000 chunks in 50, 74 and 116 s); peak 1.2 to 1.3 GB; torch threads must equal the CPU quota or it is 33 times slower |
| H4 Spanish retrieval | **Reported; acceptance is the user's** | Dense Hit@3 0.889 (0.80 to 0.98) against BM25 0.756 and random 0.178; Hit@1 0.689; wide intervals, one-author corpus |
| H5 vector compatibility | **Holds** | 112 of 112 embeddings pass `validate_embedding` and the database check; the model ignores everything after 126 tokens (cosine 1.000000 with the truncated text) |
| H6 hostile PDFs | **Holds** | 18 fixtures, same outcome with both `pypdf` versions; limits work; a 163 KB page with 60,000 text lines needs the CPU limit (it burns 20 s) |
| H7 versions and audits | **Holds, with a caveat** | `pip-audit` clean; `pypdf` 7.0.0 contains the November fixes that 6.21.4 lacks; audit data lags |
| H8 `bytea` | **Holds, with measured costs** | 136 ms per 10 MB insert, about 21 MB of WAL per job, bytes persist in data files until a table rewrite and in WAL and base backups; locks held 63 to 75 ms |
| H9 multipart, timeouts | **Holds** | Early `413` with and without `Content-Length`, `408` delivered to connected clients, no side effects on disconnect; confirms the explicit commit before `202` |

No hypothesis failed and none requires changing the approved architecture. The findings below adjust implementation details and settings; they are proposed as `/opsx:update` edits after the user's approval and are **not** applied to the specs or the design in this group.

## Recommended values for the open numeric decisions

| Item | Recommendation | Evidence |
|---|---|---|
| `pypdf` | `==7.0.0` (fallback 6.21.4) | contains the 2026-11-06 fixes; same behaviour on 18 fixtures |
| Other pins | `python-multipart==0.0.33`, `sentence-transformers==6.2.0`, `langchain-text-splitters==1.1.3`, `torch` 2.15.0 CPU wheel on Linux | H1, H7 |
| Model | `paraphrase-multilingual-MiniLM-L12-v2` at revision `e8f8c211…`, baked into the `worker` image at build, hub offline at runtime | H2 |
| Embedding batch size | 16 | H3 |
| Torch threads | new setting `EMBEDDING_THREADS`, defaulting to the cgroup CPU quota | H3 |
| Worker limits (container) | at least 4 CPUs recommended, 2 GB memory validated | H3 |
| `INGESTION_LEASE_SECONDS` | 120, renewed before the PDF child and after every batch of 16 (about 0.4 s) | H3, H6 |
| `INGESTION_JOB_DEADLINE_SECONDS` | 600 (worst case measured about 2 minutes at 1 CPU) | H3 |
| PDF child | memory 768 MB, CPU 20 s, wall clock 30 s, output cap 8 MB, pages 300 | H6 |
| `MAX_EXTRACTED_CHARS` | 2,000,000 (2,000 chunks of 100 tokens hold about 0.9 million characters of Spanish) | H6, H4 |
| `INGESTION_PENDING_BYTES_MAX_MB` | 200; `INGESTION_QUEUE_MAX` 100; `UPLOAD_MAX_IN_FLIGHT` 4 | H8 |
| `INGESTION_JOB_MAX_AGE_HOURS` | 24 (kept) | design |
| Body guard | limit 10 MB + 64 KiB overhead; total deadline 120 s; idle gap 20 s | H9 |
| `statement_timeout` / `idle_in_transaction_session_timeout` | API 15 s, worker 60 s / 30 s | H8 |
| Cleanup after clearing a payload | `VACUUM FULL ingestion_jobs` in the sweep (about 30 ms) | H8 |
| Chunk size | keep 100/20 for now; test 60/12 again on a larger corpus | H4 |

## Findings that adjust the design (to apply with `/opsx:update` after approval)

1. **New setting `EMBEDDING_THREADS`** (default: the cgroup quota) and a test that the worker sets `torch` threads before the first inference (H3).
2. **Contract: `408` is confirmed**, not conditional (H9); `docs/api-spec.yml` keeps it with the wording "client still connected"; multipart parse errors are answered `422`, not Starlette's default `400` (H9).
3. **Guard details**: absorb `ClientDisconnect` after answering; count received bytes; total deadline and idle gap as separate settings (`UPLOAD_BODY_IDLE_SECONDS` added to `UPLOAD_BODY_TIMEOUT_SECONDS`) (H9).
4. **WAL and backups numbers** for `docs/development_guide.md` and the debt entry: about 21 MB of WAL per 10 MB job, bytes in table files until a rewrite, in WAL files after a checkpoint, and in base backups; a logical dump after clearing has none (H8).
5. **CPU-bound hostile PDF**: the child's CPU limit (`SIGXCPU`) is what stops a small file with a huge page; its exit maps to `PROCESSING_TIMEOUT` (H6).
6. **Docker**: `UV_NO_CACHE`, one `RUN` per install step, model baked in one layer (463 MB), non-root user 10001 (H1).
7. **Embedding quality**: a `MIN_SIMILARITY` is not set here; the distributions are in the H4 report for change 9.

## Decisions that need the user's approval

1. **Model acceptance (H4):** is Hit@3 0.889 with a Hit@1 of 0.689 on this one-author corpus enough to keep the model as is, or should a larger corpus (from the user's own course material) or an alternative model be tried before change 6 is built? Nothing was fixed in advance.
2. **Chunk size:** keep the approved 100/20, or re-test 60/12 first.
3. **Image size:** accept a 2.8 GB `worker` image (versus 362 MB `api`) with the model baked in.
4. **Upload deadlines:** total 120 s and idle gap 20 s (a decision on teachers with slow connections), and the in-flight cap of 4.
5. **`pypdf` 7.0.0** (a major from 2026-11-06) instead of 6.21.4.
6. **Apply the adjustments above** to the design, specs and tasks with `/opsx:update` (no architecture change).

## Risks and limits of this spike

- The corpus and questions were written by the assistant; confidence intervals are wide and passages are shorter than a chunk (the long-document test covers the chunking effect with 45 questions only).
- Only one memory ceiling (2 GB) was tried for the embedding process; 1.5 GB is untested.
- `pypdf` advisories 11 to 80 were not read; the November advisories (XFA, cross-reference streams, JPEG) were not reproduced with purpose-made files; AES-encrypted PDFs were not generated.
- The advisory ranges for `python-multipart` were not read (only titles and dates); `pip-audit` reported nothing.
- HTTP/2, a reverse proxy and the `h11` parser were not tested.
- The Docker build cache of this spike (built layers, about 15 GB of the 23.5 GB shown by `docker system df`) cannot be pruned selectively by Docker's command line; it was left in place and can be reclaimed with `docker builder prune`.

## Cleanup performed and verified

- Removed: the database container `f6spike-pg`, the network `f6spike-net`, the volume `f6spike-models`, one anonymous volume that the database container created, and the six images `f6spike-*` (API, worker variants and the final candidate).
- Comparison with the lists taken before the first command: containers, volumes and networks identical; images identical except the two base images pulled for the spike (`python:3.12-slim`, `uv` 0.12.9), which were left.
- The development database `asistenteia` is identical to the snapshot of 2026-11-08 (revision `0004`, same tables, 0 rows, same schema and constraint hashes); `asistenteia_test` was not touched; the Compose service `asistenteia-db-1` stayed healthy; ports 5173, 8000 and 5442 kept their owners; nothing listened on the spike's port.
- The temporary directory of the spike (outside the repository) is deleted after these reports were written. Scripts and the corpus are kept in `reports/spike-scripts/`.
