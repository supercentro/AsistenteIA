# Design

## Context

Change 5 left the tables `documents` and `document_chunks` (migration `0004`), the actor-scoped `ChunkRepository.find_similar`, and the shared vector validation (`app/core/vector_validation.py`: 384 finite numbers, norm measured on the single-precision values with a `1e-12` margin, bind the returned values). Nothing writes to those tables yet. Facts of the current code that shape this design (verified in the repository):

- The backend is synchronous SQLAlchemy 2 with psycopg 3; `get_db` opens one session per request and commits **after** the endpoint returns. A single Uvicorn process runs the API (`--no-proxy-headers`).
- `docs/api-spec.yml` already defines the three endpoints, `Document` without a `required` list and without a failure code, and only the responses `403`, `404`, `413` and `415` for the upload.
- `rag/` is an empty package; there is no lifespan, no `MAX_UPLOAD_MB`, and none of `python-multipart`, `pypdf`, `sentence-transformers`, `torch` or `langchain-text-splitters` is installed (FastAPI cannot register a route with `File` without `python-multipart`).
- `documents` has `error_message` but no code, and the database does not enforce status transitions.
- The model card (read on 2026-11-08) states 384 dimensions, `max_seq_length` 128, Apache-2.0, 50 languages; it does not list Spanish explicitly and gives no weight size. The spike verifies both.
- PyPI (read on 2026-11-08, partly through summaries; the spike installed and audited them together): `pypdf` 7.0.0 published two days earlier (6.21.4 before it), `python-multipart` 0.0.33 (needs Python 3.11+), `sentence-transformers` 6.2.0 (needs `transformers` 5, `torch` 2.2+), `langchain-text-splitters` 1.1.3. They are verified again when added to the project (task 2.2).

Standards followed (by reference, not copied): `docs/backend-standards.md` (layers, "Ingestion", errors, security), `docs/base-standards.md` section 9, lessons L01 to L17 and the debt register. This document records the decisions D1 to D10 and the additional decisions approved by the user on 2026-11-08, and the choices made to carry them out.

## Goals / Non-Goals

**Goals:**
- A teacher uploads a file and gets a `202` that is a promise: the document and its job are durable, and the work finishes or fails with a stable code, even across restarts.
- An untrusted file can neither stall the API, exhaust the worker, leak into logs or errors, nor leave bytes behind.
- Chunks are searchable only when complete, and always fit the embedding model without silent truncation.
- The embedder is the real model; a fake one cannot appear by accident.

**Non-Goals:**
- Any user interface, chat or RAG (changes 7, 9, 10), conversation storage (8), personal-data erasure (11), index or planner changes (12).
- Permanent storage of originals, a reprocess endpoint, OCR of scanned PDFs, formats beyond PDF, plain text and Markdown, horizontal scaling beyond what the queue makes safe, and exactly-once deduplication of the same content.

## Architecture

```
 Teacher
   | multipart POST
   v
+---------------- API process (Uvicorn) ----------------+          +------------- PostgreSQL ------------+
| auth + role + ownership (404/403/401)  [before body]   |          | documents        (pending..ready)   |
| body-size guard (ASGI) + rate limit + in-flight cap    |  1 tx    | ingestion_jobs   (bytea, lease)     |
| validate name / extension / content (415, 422, 413)    |--------->| document_chunks  (vector(384))      |
| subject row lock -> quota -> queue depth -> INSERT     |  COMMIT  +-------------------------------------+
| COMMIT, then 202 {Document pending}                    |                 ^   |
+--------------------------------------------------------+                 |   | claim (SKIP LOCKED + lease)
                                                                           |   v
+---------------- Worker process (own Compose service) --------------------+--------------------------+
| loop: sweep -> claim -> renew lease at every phase -> process -> fenced final transaction            |
|   PDF:  child process (stdin bytes -> stdout bounded text; timeout, CPU, memory limits)               |
|   text: strict UTF-8 decode in-process                                                                |
|   normalise -> chunk by model tokens (100/20, re-measured <= 128) -> embed in batches (local CPU model)|
|   validate_embedding -> ONE transaction: chunks + chunks_count + status=ready + bytes erased          |
|   any failure: fenced UPDATE status=failed + error_code + fixed message + bytes erased                |
+--------------------------------------------------------------------------------------------------------+
```

Layers keep the dependency direction of the standards: `api` (`documents.py`, size guard) → `services` (`DocumentService`, `IngestionService`) → `repositories` (`DocumentRepository`, `IngestionJobRepository`; chunk writes live in `DocumentRepository`, reads stay in `ChunkRepository`) → `models`. `rag/` holds the pieces without database access: `embedder`, `chunker`, `normalizer`, `loaders` and the PDF child entry point. The worker entry point is `python -m app.worker`.

## Decisions

### D1. Separate worker and a persistent PostgreSQL queue (approved)
A second process, started as its own Compose service from the same image, polls `ingestion_jobs`. Alternatives rejected: `BackgroundTasks` or a thread pool inside the API (work lost on restart, shares memory and CPU with request handling, no recovery), and an external broker (Redis, Celery) which adds infrastructure that a single-worker MVP does not need.
- **Complexity assessment (requested):** one table, one claim query, one lease/fence rule and one loop. About 300 lines plus tests; no new infrastructure. The same table supports N workers without redesign.
- **Claim:** one statement picks the oldest job that still holds bytes, whose document is `pending` or `processing`, whose `available_at` has passed and whose lease is empty or expired, with `FOR UPDATE SKIP LOCKED`, and sets `locked_by` to a fresh random **claim token**, extends `locked_until` and increments `attempts`; in the same transaction the document becomes `processing`.
- **Polling** every 1 to 2 seconds with exponential back-off up to 10 seconds when idle. `LISTEN/NOTIFY` is a later optimisation (TD proposal).

### D2. Durable before `202`; one transaction (approved)
The document row, the job row and the bytes are inserted in one transaction and **committed explicitly inside the request** before the `202` is built. `get_db` would commit after the handler returns, which can fail after a `202` has been sent; the upload therefore calls `commit()` itself (a documented, narrow deviation from "services do not commit": only this endpoint, only through a unit-of-work helper in the API layer, never inside a service). If the commit fails the client receives `503` and nothing exists. Whether FastAPI 0.162 runs the dependency exit before or after the response is not assumed: a test against a real server pins the behaviour.

### D3. CPU inference and an isolated spike (approved; confirmed by the spike)
CPU-only `torch` through the PyTorch CPU index (explicit in `pyproject.toml`, Linux only through an environment marker so Windows and macOS keep their normal wheels), model loaded once. `paraphrase-multilingual-MiniLM-L12-v2` is **approved for the MVP** at the fixed revision `e8f8c211226b894fcb81acc59f3b34ba3efd5f42` (Apache-2.0): two downloads gave identical hashes, it runs with the network disabled, gives 384 real dimensions and every vector passed `validate_embedding` (see "Spike results and approved values"). Its quality is judged by calibrated numbers (A11), never by a fixed pass mark, and it is evaluated again on real course material in change 12. The model is fetched **at image build** from the pinned revision into `/opt/models` in one layer (463 MB) and the worker runs with the hub offline; the volume alternative was not needed. The API image does not need `torch`: Docker targets `api` (362 MB measured) and `worker` (2.80 GB measured, reference value accepted by the user), and optional dependency groups (`ingestion`: `pypdf`, `langchain-text-splitters`; `embedding`: `sentence-transformers`) keep CI light. CI installs `ingestion` only; the real model is exercised in the spike, in a marked opt-in test and in the manual verification. Docker rules from the spike: the default `torch` wheel makes the image 9.4 GB, so the CPU index is mandatory; `UV_NO_CACHE`; one `RUN` per install step to avoid duplicated layers; non-root user `10001`.

**`EMBEDDING_THREADS` (new setting).** `torch` must use as many threads as the CPU quota of the container; with the default thread count on a limited container inference was about 33 times slower. `EMBEDDING_THREADS` defaults to the effective quota (cgroup CPU quota when present, otherwise the CPUs the process may use, never below 1), may be set explicitly, is validated as a positive integer and is applied (`torch.set_num_threads`) before the first inference. The recommended worker resources are at least 4 CPUs and 2 GB of memory (validated); 1 CPU also works at about 17 chunks per second.

### D4. Real model; the fake only where declared (approved)
`EMBEDDER_BACKEND` is `local` (default) or `fake`. `fake` is accepted only when `APP_ENV=test` or when `ALLOW_FAKE_EMBEDDER=true` is set explicitly together with a non-production environment; the settings validator rejects it otherwise. There is no `try/except` that falls back: if the local model fails to load, the worker exits non-zero before claiming a job (text-embedding spec). At start the worker embeds a probe string, checks 384 components and runs `validate_embedding`.

### D5. Limits, quotas and status codes (approved)
| Setting | Default | Failure |
|---|---|---|
| `MAX_UPLOAD_MB` | 10 | `413` |
| `MAX_PDF_PAGES` | 300 | document `TOO_MANY_PAGES` |
| `MAX_EXTRACTED_CHARS` | 2,000,000 | document `TEXT_TOO_LARGE` |
| `MAX_CHUNKS_PER_DOCUMENT` | 2,000 | document `TOO_MANY_CHUNKS` |
| `MAX_DOCUMENTS_PER_SUBJECT` | 50, counting every status | `409` `DOCUMENT_QUOTA_EXCEEDED` |
| `INGESTION_QUEUE_MAX` | 100 unfinished jobs | `503` `INGESTION_QUEUE_FULL` + `Retry-After` |
| `INGESTION_PENDING_BYTES_MAX_MB` | 200 (sum of the sizes of unfinished jobs) | same `503` |
| `INGESTION_JOB_MAX_AGE_HOURS` | 24 | document `JOB_EXPIRED` |
| `UPLOAD_MAX_IN_FLIGHT` | 4 uploads being received | same `503` |
| `UPLOAD_RATE_LIMIT` | `10/minute` per address (in memory, TD-002 limits apply) | `429` + `Retry-After` |
| `UPLOAD_BODY_TIMEOUT_SECONDS` | 120 total deadline for the whole body | the body is abandoned; `408` `REQUEST_TIMEOUT` to a client that is still connected |
| `UPLOAD_BODY_IDLE_SECONDS` | 20 maximum time without receiving any byte (separate from the total) | same `408` |
| `INGESTION_BATCH_SIZE` | 16 | n/a |
| `INGESTION_LEASE_SECONDS` / `INGESTION_JOB_DEADLINE_SECONDS` | 120 / 600 per attempt (see A2) | `PROCESSING_TIMEOUT` |
| `EMBEDDING_THREADS` | effective CPU quota (see D3) | n/a |
| `PDF_CHILD_MAX_MEMORY_MB` / `PDF_CHILD_CPU_SECONDS` / `PDF_CHILD_TIMEOUT_SECONDS` / `PDF_CHILD_MAX_OUTPUT_MB` | 768 / 20 / 30 / 8 (see D9) | `RESOURCE_LIMIT_EXCEEDED` or `PROCESSING_TIMEOUT` |
| `DB_STATEMENT_TIMEOUT_API_SECONDS` / `DB_STATEMENT_TIMEOUT_WORKER_SECONDS` / `DB_IDLE_IN_TRANSACTION_TIMEOUT_SECONDS` | 15 / 60 / 30 (see A10) | `503` in the API, retry or failure in the worker |

All the values of this table are settings with these defaults, read only through `core/config.py` and documented in `.env.example`; the upload deadlines in particular are configurable (a teacher on a slow connection needs about 80 s for 10 MB at 1 Mbit/s).

`415` is used when the type is not allowed or the content does not match it (including invalid UTF-8 and NUL for text); `422` when the multipart structure or the filename is invalid (no `file`, several files, empty file, empty or oversized cleaned name). The checks of `409`, queue depth and pending bytes and the insert happen under locks (A5), so they are hard limits under concurrency and are tested with simultaneous uploads. The existing `RateLimiter` is reused. The compatibility with `docs/api-spec.yml` is additive (see "API contract").

### D6. Duplicates allowed; no double processing of one job (approved)
Two uploads of the same file are two documents and two jobs; this is documented as accepted debt (a client retry after a lost `202` creates a duplicate the teacher can delete; it also consumes quota). What is guaranteed is that **one job is never processed twice at once**: one job per document (`UNIQUE (document_id)`), the claim with `SKIP LOCKED`, the lease, the claim token and the fenced final write (A3). Content deduplication by hash and an `Idempotency-Key` header were considered and left out of the MVP.

### D7. Strict UTF-8; Markdown is data (approved)
`.txt` and `.md` are decoded with `errors="strict"`; a BOM is accepted and removed; NUL is rejected. Markdown is never parsed, converted or sanitised as HTML: it is stored as text and the contract states that consumers must not render chunk text as HTML (change 9 neutralises delimiters when it builds the prompt).

### D8. Token-based chunking with a runtime guard (approved)
`RecursiveCharacterTextSplitter` (from `langchain-text-splitters`, as the standards say) with `length_function` = the model tokenizer count **without** special tokens, `chunk_size=100`, `chunk_overlap=20` (20 %), separators paragraph, line, sentence, space, character. Each page is split on its own so `page_number` stays exact; blank pages are skipped; `chunk_index` is global and consecutive. After splitting, every chunk is **re-measured with special tokens**; one above 128 is re-split by tokens; if that is not possible the document fails with `PROCESSING_FAILED`. The margin of 28 tokens covers the two special tokens and differences between the splitter's measurement and the model's. Tests: a fake counter (CI) proves the splitter respects whatever counter it receives and the guard triggers; the real tokenizer (spike and opt-in test) proves the 128 limit on Spanish prose, very long words, URLs, digits, emoji, CJK and right-to-left text.

### D9. Isolated PDF parsing (approved)
The worker starts `python -I -m app.rag.pdf_child` for each PDF with a minimal environment, no inherited descriptors, `stdin` = the bytes, `stdout` = JSON lines `{"page": n, "text": "..."}`, `stderr` discarded. The child applies its own limits first thing, on Linux: `RLIMIT_AS`, `RLIMIT_CPU`, `RLIMIT_FSIZE=0` (cannot write files), `RLIMIT_NOFILE`, `RLIMIT_CORE=0`; the parent adds a wall-clock timeout (`PDF_CHILD_TIMEOUT_SECONDS`, 30), caps the total bytes read from `stdout` (8 MB) and kills the child on any breach. Initial limits, validated by the spike: memory 768 MB, CPU 20 s, wall clock 30 s, output 8 MB, 300 pages, 2,000,000 characters. A child stopped by `SIGXCPU` or by the wall-clock timeout maps to `PROCESSING_TIMEOUT`; a memory breach to `RESOURCE_LIMIT_EXCEEDED`. The most realistic abuse measured was a 163 KB file with one page of 60,000 text lines, which burns the whole CPU limit and is stopped by it. The child checks `is_encrypted` (fail even when it opens without a password), the page count before extracting, and caps characters. It uses `pypdf` only, with `strict=False`, no images and no crypto extras. Because the limits rely on Linux, the worker refuses to parse PDFs outside a Linux container (the supported way to run it is Compose); there is no in-process fallback.
- **Library review (requested):** `pypdf` 7.0.0 (a major published on 2026-11-06, with the November security fixes that 6.21.4 lacks) is the **selected candidate**; 6.21.4 behaved identically on the 18 hostile fixtures and is the fallback if a regression appears. The definitive choice is made when the dependency is added (task 2.2): re-read the changelog and the advisories (the spike read the first page of eight), run `pip-audit` (its data lags the advisories) and check compatibility; pin the exact version in `uv.lock` and record the decision and the upgrade rule in `docs/development_guide.md`.
- **What the spike did not cover:** the 18 fixtures do not represent every PDF variant. Not reproduced: crafted cross-reference streams with identical offsets, XFA forms, malicious JPEG data and PDFs that really use AES encryption (RC4 was used; `is_encrypted` is true either way). The generic limits above are the defence. PDFs are never parsed in the HTTP process.
- Residual risk (TD proposal): a PDF that stays below every limit can still use up to the limits per job; the container memory and CPU limits are the outer bound.

### D10. Stable `error_code` with safe messages (approved)
`documents.error_code` (new nullable `varchar(40)`) holds one code from the closed catalogue in the `document-ingestion` spec; `error_message` holds a fixed English sentence per code, defined once in code and in the API contract. The frontend (change 7) translates by code and never depends on the sentence. The catalogue (12 codes, including `JOB_EXPIRED`) is an enum in code; the database only enforces "a code exists only on a failed document". Adding a code later is a contract change.

## Additional decisions

### A1. Where the file lives between `POST` and processing
In `ingestion_jobs.payload` (`bytea`), in the same transaction as the document. This makes the `202` promise atomic (no orphan files, no file without a job), needs no shared volume between API and worker, and lets cascades erase it. Rejected: a shared filesystem volume (not atomic with the database, needs reconciliation, a durable location for hostile files) and object storage (new infrastructure). Cost: up to 10 MB per pending job in the database until the terminal state. **Setting `payload` to `NULL` or deleting the row does not erase the bytes immediately**: copies stay in dead tuples (and in TOAST) until vacuum, in the write-ahead log and in any base backup, logical dump or replica made while the job existed. This is documented in `docs/development_guide.md` and registered as debt; it is bounded by the 10 MB file limit, the per-subject quota, the queue cap and the pending-bytes cap, and shortened by the cleanup of A7 and by autovacuum. The spike measured it: each 10 MB job writes about 21 MB of WAL (10.7 MB on insert and 10.5 MB on clearing); after clearing, the bytes stay in the table files (also after `VACUUM`, which does not overwrite free pages) until a table rewrite, stay in WAL segments after a checkpoint (recycled segments are not zeroed) and stay in any base backup taken before the rewrite; a logical dump taken after clearing contains none. Operators must treat database backups and WAL archives as containing teachers' files for their retention period. Starlette parses large parts into a temporary file in the API container; it is closed in a `finally` and the tests assert that nothing remains in the temporary directory after success, `413`, `415` and `422`.

### A2. Recovery after restarts
Leases expire: a job whose worker died becomes claimable by `locked_until < now()`, with no startup special case. The worker also runs a **sweep** at start and every 60 seconds: (1) jobs whose lease expired and whose `attempts` reached `INGESTION_MAX_ATTEMPTS` (3) are failed with `PROCESSING_INTERRUPTED` and their bytes erased; (2) jobs holding bytes whose document is already terminal lose the bytes. Lease length `INGESTION_LEASE_SECONDS` = 120 and per-attempt deadline `INGESTION_JOB_DEADLINE_SECONDS` = 600, after which the job fails with `PROCESSING_TIMEOUT` (worst measured case: about 2 minutes for 2,000 chunks on 1 CPU). **Lease renewal never keeps a transaction open.** The lease is renewed (a) at every phase boundary and after every embedding batch of 16 (about 0.4 to 0.9 s apart), and (b) by a heartbeat thread of the worker that renews every `INGESTION_LEASE_SECONDS / 3` seconds with its own short transaction (one fenced `UPDATE` in autocommit, then the connection returns to the pool), so a legitimate job that runs longer than 120 s (a long wait for the PDF child, a slow CPU) keeps its lease while inference blocks the main thread. The heartbeat stops renewing when the deadline has passed. If a renewal updates no row (job deleted, claimed by another worker or the lease already expired) the heartbeat sets a *lease lost* flag that the main thread checks between phases and batches, and the worker stops without writing anything. An expired lease cannot be revived by a late renewal. A job that has waited longer than `INGESTION_JOB_MAX_AGE_HOURS` without being finished (for example because no worker runs) is failed by the sweep with `JOB_EXPIRED` and its bytes are erased, so unfinished work cannot accumulate indefinitely.

### A3. Two workers, one document
Claim with `SKIP LOCKED`; the claim token (random, stored in `locked_by`) is the fencing token. Every write of a worker (renewal, heartbeat, every status transition, chunk insert, final commit, failure marking, byte erasure) is conditioned on `locked_by = :token AND locked_until > now()` and is made while holding `FOR UPDATE` on the job row; a stale worker finds no row and aborts without writing. Terminal documents are never updated (`WHERE status IN ('pending','processing')`). The rule covers **failure marking too**: a worker whose job was deleted, claimed by another worker or expired cannot mark the document `failed`, store chunks, renew a lease or clear bytes; each of those is a conditional statement whose zero-row result means "stop". Tests force a lease into the past with SQL, run two real sessions and two real processes, and assert that the loser writes nothing.

### A4. `DELETE` during ingestion
The delete does not wait for the worker (the worker holds no lock while it works). The cascade removes the document, chunks, job and bytes. The worker notices at the next renewal (no row for its token) or at its final transaction (`FOR UPDATE` finds nothing, or the composite foreign key rejects the chunk insert) and stops quietly, writing nothing. Subject deletion behaves the same.

### A5. Quota under concurrency
The upload transaction first runs `SELECT ... FROM subjects WHERE id = :s AND teacher_id = :t FOR UPDATE` (this also yields the `404`), then counts the documents of the subject and inserts only below the cap. Concurrent uploads to one subject serialise on that row for the few milliseconds of the transaction; other subjects are unaffected. After the subject lock the transaction takes a second, global transaction-level advisory lock (`pg_advisory_xact_lock`, always in the order subject then global, so no deadlock), counts unfinished jobs and sums their sizes, and inserts only below `INGESTION_QUEUE_MAX` and `INGESTION_PENDING_BYTES_MAX_MB`. The locks are held only for the insert, so the limits are hard under concurrency; the spike measures how long a 10 MB insert holds them. A cheap, lock-free count before the body is read lets an obviously full service answer `503` early (an optimisation, not the guarantee).

### A6. `202` only if the job can be recovered
Because the job and the bytes are part of the same committed transaction (D2, A1), a `202` implies a recoverable job. A commit failure maps to `503`; a crash after the commit leaves a `pending` document that a worker will claim.

### A7. Cleanup of temporary bytes
`payload` is set to `NULL` in the same transaction that sets `ready` or `failed` and when attempts are exhausted; deletion cascades; the sweep (A2) removes bytes of terminal documents. Nothing is written to disk by the worker (the PDF child reads from a pipe; text is decoded from memory).

**Vacuum strategy (decided after the spike).** The worker and its sweep never run `VACUUM FULL`. Autovacuum stays on with the default settings: in the spike it removed the dead TOAST tuples of a cleared payload within 100 s, so no per-table setting is required. `VACUUM FULL ingestion_jobs` (about 30 ms for this small table, with a short exclusive lock, and the only way to remove the bytes from the data files) is reserved for manual maintenance approved by the operator, for example before a base backup is taken or after a sensitive upload. The development guide documents how to follow the cost: dead tuples and `last_autovacuum` of `ingestion_jobs` and its TOAST table (`pg_stat_user_tables`), the table and TOAST size (`pg_total_relation_size`), and the WAL volume (`pg_stat_wal` and the size of the WAL directory), plus the residual persistence of bytes in WAL and backups.

### A8. Reading the body safely
Authentication, role and ownership are resolved by dependencies **before** the body is read (the handler does not declare `File` parameters; it reads the form itself with `request.form(max_files=1, ...)`). The database transaction of that first check is closed before the body is read so a slow client does not hold a pooled connection. A pure-ASGI guard on the upload route counts body bytes and answers `413` as soon as `MAX_UPLOAD_MB` plus a small multipart overhead is exceeded (declared or undeclared length), and enforces two deadlines, `UPLOAD_BODY_TIMEOUT_SECONDS` for the whole body and `UPLOAD_BODY_IDLE_SECONDS` for the time without progress. For a client that is still connected the guard answers `408` itself and then reports a disconnect to the application; it absorbs `ClientDisconnect` after answering (otherwise Uvicorn logs error traces). It promises nothing to a client that already closed the connection. The multipart field and file limits are set to one file and no extra fields. The OpenAPI description of the multipart body is provided with `openapi_extra`. **Limits apply to the bytes actually received**, never to `Content-Length` alone: the guard counts every body byte, the stored `size_bytes` is the length of the bytes in `payload`, and a client that declares a small length and sends more (or declares a large one and sends less) is judged by what arrives. The effective limits of `python-multipart` and Starlette were measured at the spike (a 10 MB upload adds about 9 MB of server memory; abusive multipart structures are rejected in under 10 ms), and tests cover chunked bodies, bodies without `Content-Length`, a lying `Content-Length` and reception interrupted by the client (nothing stored, nothing left in the temporary directory, no rows). When the connection is cut no response can be sent; the guarantee is only that nothing is persisted.

**Differentiated, controlled errors.** Starlette answers every multipart parsing error with `400`, which the contract does not list; the handler catches the multipart exception and answers with the standard error body: `413` (`PAYLOAD_TOO_LARGE`) for too many bytes; `408` (`REQUEST_TIMEOUT`) for a stalled body of a connected client; `422` (code `VALIDATION_ERROR`) with a fixed `details.reason` of `MALFORMED_MULTIPART` (invalid structure or limits of parts, fields or headers exceeded), `FILE_PART_MISSING` (no part named `file`), `UNEXPECTED_FIELDS` (several files or extra fields), `EMPTY_FILE` or `INVALID_FILENAME`; and `415` for a type that is not allowed or does not match its content. The reasons are fixed strings and never include parser text, names or content.

### A9. Logs, paths, filenames and parser errors
Only identifiers, counts, durations and codes are logged (document id, job id, attempt, phase, code). Filenames are neither logged nor placed in paths or errors; they are cleaned (last path component, no control, line-separator or bidirectional characters, at most 255 characters) with the shared validator family of TD-018. Parser and database exception text is never stored or logged: exceptions are mapped by type to a code. The engine keeps `hide_parameters=True` and the error middleware keeps logging only type, method and path. Leak tests use markers in the filename, content and PDF metadata with log spies and mutations, as in change 5.

### A10. No database resources held while working
Parsing and embedding never run inside a database transaction or while holding a row lock, an advisory lock or a pooled connection. The worker uses short transactions only for the claim, each renewal, and the final write; between them its session is closed. Both engines set `statement_timeout` and `idle_in_transaction_session_timeout` as connection options: API 15 s and worker 60 s for statements, 30 s for idle transactions in both (the measured statements are two orders of magnitude below them: a 10 MB insert 150 ms, the final write of 2,000 chunks by `COPY` 121 ms). The timeouts are not applied to Alembic. This resolves the `statement_timeout` part of TD-023 for these paths; a bug can no longer leave a transaction open. A test with a deliberately slow fake embedder checks `pg_stat_activity` and `pg_locks` while it runs: no open transaction and no lock belonging to the worker.

### A11. Calibrated model evaluation (spike)
The Spanish retrieval check reports, on a corpus written for the spike, hit rate at 1 and at 3 and the mean reciprocal rank with their uncertainty (a bootstrap interval; the corpus size is stated), the same measures for a lexical baseline and for random order, the distribution of cosine similarity of relevant versus irrelevant passages, and the effect of the 100-token chunking on the result. No absolute pass mark is fixed in advance: the numbers are presented to the user, who decides acceptance. The similarity distributions also inform the `MIN_SIMILARITY` of change 9 but do not set it.

## Spike results and approved values

Executed on 2026-11-08 and approved by the user; evidence in `reports/2026-11-08-spike-*.md` (summary: `reports/2026-11-08-spike-summary.md`). None of the nine hypotheses failed and the architecture is unchanged.

| Area | Result |
|---|---|
| Images (reference, not a gate) | `api` 362 MB; `worker` 2.80 GB with the model (CPU `torch`); default `torch` 9.38 GB; builds 9 s, 2 min 1 s and 20 min 40 s |
| Model | revision `e8f8c211226b894fcb81acc59f3b34ba3efd5f42`; `model.safetensors` 470,641,600 bytes; identical hashes in two downloads; offline load 4.4 s; resident memory about 800 MB (peak 850 MB); 384 dimensions; `max_seq_length` 128; the model ignores tokens beyond 126 (cosine 1.000000 with the truncated text), so the chunk guard is mandatory |
| Throughput (batch 16) | 4 CPUs 40 chunks/s (2,000 chunks in about 50 s); 2 CPUs about 27; 1 CPU 17.3 (about 116 s); memory peak 1.16 to 1.32 GB under a 2 GB ceiling (lower ceilings untested) |
| Vector compatibility | 112 of 112 embeddings pass `validate_embedding` and the database check; norms 2.56 to 6.74 |
| Spanish retrieval (45 questions, 60 passages, one subject at a time) | Hit@1 **0.689**, Hit@3 **0.889** (interval 0.80 to 0.98), MRR **0.798**; lexical BM25 Hit@1 0.622, Hit@3 0.756 (0.62 to 0.89), MRR 0.732; random order Hit@3 0.178 |
| Chunking on long documents | Hit@3 with 60/12 0.889, 100/20 0.800, 200/40 0.667, 400/40 0.378; 100/20 is kept |
| Hostile PDFs | 18 fixtures, same outcome with `pypdf` 6.21.4 and 7.0.0; the limits of D9 hold |
| `bytea` | insert 136 ms; about 21 MB of WAL per 10 MB job; locks held 63 to 75 ms (8 simultaneous uploads: worst wait 848 ms; with 4 in flight below 0.3 s) |
| HTTP | early `413` with and without `Content-Length`; `408` delivered to connected clients (idle and slow-drip); 20 stalled uploads did not slow other requests (0.5 ms pings); no temporary file left; FastAPI 0.162 sends the response **before** the `yield` dependency exits (explicit commit before `202` confirmed) |

**Limits of the evidence (do not overstate).** The corpus and the questions were written by the assistant, with one author and 45 questions: the intervals are wide, they overlap with the lexical baseline, and **no statistical superiority over BM25 is claimed**; the dense model is reported as clearly better than random order and as adequate for the MVP by the user's decision. The model is evaluated again on real educational material in change 12. Only one memory ceiling (2 GB) was tried. HTTP/2, a reverse proxy and the `h11` parser were not tested. The versions were read partly from summaries.

**Approved values** (settings with these defaults): batch 16; lease 120 s and deadline 600 s per attempt with heartbeat and fencing (A2, A3); PDF child 768 MB, 20 s CPU, 30 s wall clock, 8 MB output, 300 pages, 2,000,000 characters; queue 100, pending bytes 200 MB, 4 uploads in flight; upload deadlines 120 s total and 20 s without progress; `statement_timeout` 15 s (API) and 60 s (worker); `idle_in_transaction_session_timeout` 30 s; `EMBEDDING_THREADS` from the CPU quota; chunk size 100 with overlap 20.

## Data model (migration `0005`)

`ingestion_jobs`: `id uuid` PK (`gen_random_uuid()`), `document_id uuid` NOT NULL UNIQUE FK → `documents(id)` ON DELETE CASCADE, `payload bytea` NULL, `attempts integer` NOT NULL default 0 (CHECK ≥ 0), `locked_by varchar(64)` NULL, `locked_until timestamptz` NULL (CHECK both null or both set), `available_at timestamptz` NOT NULL default `now()`, `created_at`, `updated_at`; partial index `(available_at) WHERE payload IS NOT NULL` for the claim. `documents.error_code varchar(40)` NULL with CHECK `error_code IS NULL OR status = 'failed'` (the reverse, "failed has a code", is enforced by the service and tests so that existing test fixtures that insert failed documents keep working). `0004` is not edited; the downgrade drops the table and the column; catalog tests in the style of change 5 check constraints, index and cascades (I1 of change 5: `alembic check` does not see them).

## API contract (additive; `docs/api-spec.yml` and `docs/data-model.md` change in this change)
- `POST /subjects/{id}/documents`: adds `401`, `408` (`REQUEST_TIMEOUT`, only for a client that stays connected; confirmed with a real server), `409` (`DOCUMENT_QUOTA_EXCEEDED`), `422`, `429`, `503` (`INGESTION_QUEUE_FULL` or storage failure) to the existing `202`, `403`, `404`, `413`, `415`; `422` keeps the generic code `VALIDATION_ERROR` and distinguishes the cases with a fixed `details.reason` (A8) so that the existing `Error` schema does not change; documents the field `file` (exactly one, non-empty) and the allowed types.
- `GET` and `DELETE`: add `401`.
- `Document`: new nullable `error_code` (enum of the catalogue) and a `required` list (`id`, `subject_id`, `filename`, `content_type`, `size_bytes`, `status`, `chunks_count`, `created_at`; the nullable fields stay optional-nullable), which closes divergence 5 of change 5.
- Compatibility: nothing is removed or renamed; clients of the previous contract keep working. `npm run generate:api` regenerates `frontend/src/api` types (the CI check `check:api-types` fails otherwise); no UI code changes.
- Settings and `.env.example`: all values above, with placeholders.

## Test strategy (summary; detail in `tasks.md`)
TDD per group with the failing run recorded; unit tests with a fake embedder and a fake token counter; integration tests on PostgreSQL with pgvector (negatives of authorization: `401`, student `403`, other teacher and unknown subject `404`, other subject's document `404`); concurrency tests (quota, two workers, stale worker, delete during processing); recovery tests with a real worker subprocess that is killed; **real-server tests** with the production Uvicorn arguments for the body limit, chunked bodies, slow bodies and commit-before-`202` (lesson L03); PDF fixtures generated in tests (normal, scan, encrypted, corrupt, many pages, decompression-heavy) with limits verified in the real child; leak tests with log spies; mutation checks of every guard; end-to-end ingestion → `find_similar` with the fake embedder; real-model checks only in the spike, an opt-in marked test and the manual verification with `curl`; an independent adversarial review as in change 5 (upload of hostile files, authorization and personal data). Playwright is not applicable (no UI); the reason is recorded in the verification report.

## Risks / Trade-offs
- [Originals sit in the database until processed] → quota, queue cap and 10 MB limit bound the volume; erased in every terminal path and by the sweep; listed as debt.
- [A hostile PDF stays under the limits and still costs CPU or memory] → child process with CPU, memory, time and output caps, container limits, page and character caps; residual risk registered.
- [Limits depend on Linux `rlimit`] → the worker only parses PDFs inside the Linux container; documented; Windows development uses Compose.
- [Image size and slow first build from `torch` and the model] → CPU wheels, separate `api` and `worker` targets, model fetched once at build; the spike measures it before the numbers are fixed.
- [A new `pypdf` major and a new `sentence-transformers` major] → exact pins, advisory review, the spike compares candidates.
- [Polling latency and a single worker] → acceptable for the MVP (seconds); `LISTEN/NOTIFY` and more workers are possible without redesign.
- [Embedding throughput on CPU] → batch size and the 2,000-chunk cap are set from spike measurements; the job deadline bounds the worst case.
- [Duplicates and client retries] → accepted (D6), visible to the teacher, deletable.
- [Slow or abusive clients] → body deadline, in-flight cap, rate limit, early `413`; the in-memory limiter keeps the limits of TD-002.
- [Deleted bytes remain in WAL, dead tuples, table files and backups] → measured (about 21 MB of WAL per 10 MB job; bytes in files until a rewrite; in WAL and base backups), documented, bounded by the limits, shortened by autovacuum and the cleanup; `VACUUM FULL` only as approved manual maintenance; registered as debt.
- [The global admission lock serialises the short insert of every upload] → held only for the insert; measured at the spike (a 10 MB insert); the in-flight cap bounds the queue of waiting uploads.
- [`408` cannot be sent to a client that closed the connection] → the contract promises it only to connected clients; the guarantee for a disconnect is the absence of side effects.
- [A legitimate job outlives the lease] → heartbeat renewal with its own short transaction, fenced writes and per-attempt deadline; tested with a lease shorter than the job.
- [The embedding model is judged on a small corpus written by the assistant] → reported with intervals and no claim over BM25; re-evaluated on real material in change 12.
- [The PDF trials do not cover every variant] → generic limits in a separate process; advisories and versions re-checked when the dependency is added.
- [An absolute accuracy threshold would be arbitrary] → calibrated comparison and the user's decision (A11), taken on 2026-11-08.
- [Tests that depend on a dev server on the default ports] → the real-server tests choose a free port and never touch 8000 or 5173 (see `docs/development_guide.md`, "Ports already in use").

## Migration Plan
1. Implement in this branch; apply `0005` to the isolated test database through the suite and to a scratch database for the round trip; the development database is migrated only in the verification group, after a backup copy, with the user's authorization in that group.
2. Rollback: `alembic downgrade 0004` (drops `ingestion_jobs` and `documents.error_code`); data of in-flight jobs is lost by design; documents already `ready` and their chunks are kept.
3. Deployment (change 13): the worker is a second service; the model layer or volume and the memory limits are part of that change.

## Debt proposed (registered in `docs/technical-debt.md` during the apply, with the user's agreement)
Resolved: TD-023 (quotas, with `statement_timeout` evaluated in the spike) and TD-027 (normalisation). New: bytes of originals live temporarily in the database and can remain in WAL, dead tuples and backups after they are erased; PDF isolation limits are Linux-only and bounded rather than absolute; duplicates and client retries; polling worker without fairness between subjects; the rate limiter remains in memory (TD-002 family); the embedding model validated only on a small assistant-written corpus until change 12; the PDF variants not covered by the spike.

## Items for the user's explicit approval at the review of these artifacts
Architecture-affecting choices beyond D1 to D10: bytes stored in `ingestion_jobs.payload` (A1); migration `0005` with the table and the column; a second Compose service and Docker targets; explicit commit in the upload endpoint (D2); reading the form inside the handler (A8); the additive contract changes including `error_code` and the `408` for connected clients (confirmed by the spike) and the differentiated `422` reasons; the generated frontend types being regenerated; the Linux-only rule for PDF parsing.

## Open Questions
- The numbers listed in "Spike results and approved values" are decided. Still to be confirmed when the dependencies are added (task 2.2): the definitive `pypdf` version (7.0.0 selected, 6.21.4 fallback), the advisories not read in the spike (`pypdf` 11 to 80, the ranges of `python-multipart`) and the lock file with the Linux-only CPU index.
- Whether Windows and macOS developers need the `embedding` group at all (the worker runs in the Linux container) is settled in task 2.2.
