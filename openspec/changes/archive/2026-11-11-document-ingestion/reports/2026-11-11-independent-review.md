# Independent adversarial review: change `document-ingestion` (task 16.1)

Branch `feature/document-ingestion`, HEAD `172288a`. Reviewer: a separate subagent with a clean context and read-only instructions (not the implementing session), using the `adversarial-review` skill. The text below is the reviewer's report, condensed only in wording; the implementer added the "Checks by the implementer" section at the end. Task 16.1 is the review; **16.2 (fixes) has not been run** and needs the user's decision.

**Headline: no Critical and no High finding, no blocker. Two Medium findings (R-01, R-02) are "major" in the vocabulary of 16.1 and must be fixed, or formally accepted by the user, before the change closes. Verdict: PASS WITH GAPS.**

## 1. Scope and method
- **Read:** OpenSpec proposal, design, tasks and specs; `backend/app` (documents endpoints and dependencies, `upload_guard`, `upload_inspection`, document and ingestion services, repositories, `worker`, `loaders`, `pdf_child`, `embedder`, `chunker`, `normalizer`, `config`, `database`, errors, `main`, `chunk_repository`, vector validation, models); migration `0005`; `Dockerfile`, `docker-compose.yml`, `.dockerignore`, `.gitignore`, CI workflow, `pyproject.toml`; the diffs of `docs/api-spec.yml` and `docs/data-model.md`; `docs/technical-debt.md`; the generated frontend types (the only frontend change); lock files; the branch history (secret scan). The seven reference documents were not read.
- **Environment:** disposable Docker resources `g16r-*` (internal network, pgvector 0.8.7-pg15 on tmpfs with a random password, the real API with the production arguments minus `--reload`, the real worker with the real MiniLM model), image `asistenteia-worker:latest` (built 2026-11-09, so it predates the last hardening commit) with the repository mounted read-only.
- **Ran:** the full suite (1,750 passed, 8 skipped, 16 deselected in 280 s) and `-m realmodel` (16 passed); `alembic upgrade head`, `check`, `downgrade 0004`, `upgrade head`; black-box HTTP attacks (authorization matrix, 17 filename variants, content/extension mismatches, multipart fuzz with 1,000 parts, a 2 MB header and a 5,000-character boundary, oversize and exact-limit files, declared 1 GB, chunked 12 MB, lying/duplicate/negative `Content-Length`, stalled clients, four stalled slots plus a fifth upload, disconnects); admission races (40 threads); 10 hostile PDFs; worker kill and recovery; delete during processing; a stress run of claim/complete/fail/delete/sweep with 8 workers and a 1 s lease; five throwaway mutations on a copy.
- **Limitations:** coverage was not re-measured (`pytest-cov` unavailable offline; the 99 % is unverified by the reviewer; `app` has one `pragma: no cover`, `ingestion_job_repository.py:129`); `pip-audit`, `npm audit`, `ruff` and `mypy` were not re-run (no network), dependency remarks come from the lock files only; seven tests are skipped in the container (no `git`), replaced by manual `git ls-files` and history greps; kernel-level behaviour of Docker Desktop was not examined; no browser or UI run.

## 2. Checklist of task 16.1
| Item | Verdict | Evidence |
|---|---|---|
| Authorization and the `404` rule | OK | anonymous 401; student 403 (also malformed or unknown subject); foreign teacher 404; unknown or malformed subject 404; IDOR delete via wrong subject, as a foreign teacher, and with a malformed id all 404; student list and delete 403. Mutation M1 (removing `owns_subject`) is caught by one test; a foreign teacher still gets 404 under M1 because `add_with_job` re-checks ownership |
| Quota and queue races | OK | 80 concurrent admissions into a subject with 22 documents: exactly 28 ok and 52 `DOCUMENT_QUOTA_EXCEEDED`; 100-job limit exact; 10 MB files stopped at exactly 200 MiB; M3 (advisory lock removed) caught |
| Lease and fencing | OK | stress run: 124 ready, 64 failed, 0 errors or deadlocks, 79 fenced writes rejected, no terminal row kept bytes or a lease, `chunks_count` equal to chunk rows, no chunks on non-ready documents, attempts max 3; M2 (token removed from the confirm query) caught |
| Double processing | OK | `SKIP LOCKED` plus fencing; no job claimed more than 3 times |
| Deletion during processing | OK | 204, worker logged `lost`, 0 chunks, 0 jobs, 0 orphans |
| Recovery | OK with a gap | `docker kill` mid-job: after the lease expired and the worker restarted, attempt 2 ended in a terminal state with payload NULL; poison jobs end `PROCESSING_INTERRUPTED`. Nothing restarts the worker (R-02) |
| PDF isolation and limits | OK for resource abuse; weak against code execution in the child | hostile PDFs all ended with fixed codes, worker healthy at 662 MiB; see R-05 |
| Decompression and resource exhaustion | OK for PDF; gap for text | 1.5 GB flate bomb ended `NO_EXTRACTABLE_TEXT` in seconds; count-lie, page-tree loop, 200,000-deep nesting, truncated and garbage PDFs gave fixed codes; 400 pages `TOO_MANY_PAGES`; 2M-character page `TEXT_TOO_LARGE`; text path is a CPU gap (R-01) |
| Filename and content handling | OK | traversal, backslash, NUL, control, RLO and `<script>` names reduced to the last component with controls and bidi characters removed; 300-character name 422; `..`, empty and `.txt` 422/415; NTFS-stream and trailing dot 415; invalid UTF-8 and NUL 415; client Content-Type ignored; filename never used as a path; see R-09 |
| Temporary bytes in every path | OK | ~60 hostile requests left 0 files and 0 descriptors in `/tmp`; every terminal path left payload NULL; M4 (keep bytes on failure) caught; dead tuples and WAL remain (TD-029) |
| Log and error leakage | OK | API and worker logs hold ids, sizes, error types and codes; greps for the injection filename, `passwd`, `script`, password and `Bearer`: 0 hits |
| Explicit commit before `202` | OK | `_store` commits before the response; DELETE calls `db.commit()`; with FastAPI 0.162 the yield-dependency exit runs after the response. Informational: a commit that succeeds with a dropped connection gives the client a 503 with a stored document |
| Migration reversibility | PASS with a defect | upgrade, `alembic check` clean, downgrade, re-upgrade clean; `0004` untouched; defect R-04 |
| Contract versus implementation | OK | live `/openapi.json` codes for the three routes equal `docs/api-spec.yml`; schema fields and `details.reason` values match; only undocumented behaviour is the 307 on a trailing slash (informational) |
| Mutation and TDD evidence | OK | the reviewer's 5 of 5 mutations were killed; the red-first history of each group was not replayed |
| Secret separation worker/db | OK | `.env.worker` has only worker names; `.env.db` only the three `POSTGRES_*`; compose gives each service only its file; worker container has no JWT or POSTGRES variable; image contains only `.env.example`; no tracked `.env*` besides examples; `git log --all -- .env .env.worker .env.db` empty; no real credentials in the branch diff. Remaining: R-05, R-06 |
| Docker exposure | Acceptable for development, gaps listed | db, backend and frontend published on 127.0.0.1 only; the worker publishes nothing; gaps R-05, R-06 |
| Dependencies / Dependabot #1 | PASS with an open decision | `minimatch` 10.2.6 under `typescript-estree` 8.72.1 (development only, in the advisory range); copies 3.1.5 and 5.1.9 out of range; agrees with TD-036; task 17.3 still needs a decision. Pins: pypdf 7.0.0, python-multipart 0.0.33, torch 2.15.0, sentence-transformers 6.2.0, starlette 1.10.0, fastapi 0.162.0, pyjwt 2.15.1 (no CVE status confirmed offline) |

## 3. Findings (most severe first)

### R-01 Pathological text keeps the single worker busy for minutes
- **Severity:** Medium (vocabulary: **major**). **Category:** confirmed; fairness is TD-034, the amplification is not recorded.
- **Where:** `backend/app/rag/chunker.py` (`chunk_pages`: `splitter.split_text(page.text)` runs to completion before the `max_chunks` check); `ingestion_service.py` (`_run`; checkpoints only between phases).
- **Evidence:** a 2,000,000-character `.txt` (`"a"` x 2M, `"字"` x 2M or `". "` x 1M) is accepted (about 2 MB). Chunking alone took 58 s, 60 s and 30 s on 2 CPUs before `TooManyChunksError`. Three such files followed by a harmless one made the harmless document wait about 3 minutes. At 50 documents per subject one teacher can occupy the worker for about 50 minutes; the global cap is 100 jobs.
- **Impact:** availability of ingestion for every teacher; the design claim that deadlines bound a job fails, because the deadline is checked only at checkpoints (the heartbeat kept the lease alive).
- **Reproduction:** upload `b"a"*2_000_000` as `x.txt` three times, then a small file; read the worker log timestamps.
- **Mitigation today:** only the 3-attempt cap.
- **Recommendation:** fix before closing. Options: check `max_chunks` incrementally or reject early from the text length, run chunking under a wall-clock cap, or lower `MAX_EXTRACTED_CHARS` for text. At minimum record the amplification in TD-034.

### R-02 No restart policy or liveness for the worker
- **Severity:** Medium (vocabulary: **major**). **Category:** confirmed (configuration and design gap).
- **Where:** `docker-compose.yml`, `worker` service: no `restart:` and no healthcheck. The worker exits with code 2 on refusal; an out-of-memory kill (`mem_limit: 2g`) ends it for good.
- **Evidence:** after `docker kill` nothing brought the worker back; documents stayed `pending` and `processing`. `JOB_EXPIRED` and `PROCESSING_INTERRUPTED` are written only by the worker's sweep, so with the worker dead no document leaves `pending` and after 100 jobs the API answers 503. The design promises that a document "finishes or fails with a stable code, even across restarts".
- **Impact:** endless `pending` for teachers and a full queue with no operator signal.
- **Reproduction:** `docker kill` the worker under Compose; upload; watch the status.
- **Recommendation:** fix before closing: `restart: unless-stopped` plus a healthcheck, or state the operational requirement and its limit in the spec.

### R-03 One authenticated teacher can monopolise the upload slots; the refusal reuses the queue-full code
- **Severity:** Low (**minor**). **Category:** confirmed. **Where:** `documents.py` (`slots.try_acquire`), `upload_guard.py`.
- **Evidence:** four connections that send headers and a few bytes and then stall hold all four slots for 19-20 s (idle limit); a drip of 1 byte per under 20 s extends it to 120 s. A fifth upload got `503 INGESTION_QUEUE_FULL` with the same text as a full queue.
- **Impact:** a teacher account can block uploads for all teachers; the per-address limit (10/min) does not stop it. Authentication precedes the body, so anonymous clients cannot do it; reads and health stayed fine.
- **Recommendation:** accept as debt: extend TD-035 with the slot starvation and the identical code.

### R-04 Downgrade then upgrade of `0005` leaves `pending` documents that never progress
- **Severity:** Low (**minor**). **Category:** confirmed. **Where:** `alembic/versions/0005_create_ingestion_jobs.py`, `downgrade`; `docs/data-model.md`.
- **Evidence:** a `pending` document with a job, then downgrade to 0004 and upgrade: the document stayed `pending` after 70 s with the worker running (claim and sweep both join `ingestion_jobs`), 0 jobs, and it still counts toward the 50-document quota. `failed` documents also lose `error_code` (the message stays), so "failed has a stable code" does not hold for them. The downgrade comment already says in-flight jobs are lost "by design".
- **Impact:** a stuck document until the teacher deletes it; only when downgrading with data in flight.
- **Recommendation:** fix before closing if cheap (the downgrade should mark `pending` and `processing` documents `failed`, or delete them, and document it); otherwise accept.

### R-05 The PDF child is a resource-limited process, not a sandbox
- **Severity:** Medium, conditional on a `pypdf` code-execution flaw (vocabulary: **acceptable risk** now). **Category:** known debt (TD-030), partly under-stated. **Where:** `loaders.py` (`load_pdf`), `pdf_child.py` (`apply_limits`).
- **Evidence:** from a process under the child's rlimits, in the worker container as uid 10001, the reviewer read the worker's `/proc/1/environ` (names include `DATABASE_URL`), opened a TCP connection to `db:5432`, spawned a subprocess and read the application source. TD-030 already says the child can read what the worker user can read. What it under-states: there is no `RLIMIT_NPROC` and no `pids_limit`; `_stop` kills the process group only if the leader is still running (a detached grandchild survives); the worker has unrestricted outbound network; the database user is the superuser `asistente`, shared by the API and the worker.
- **Impact:** only after a `pypdf` exploit; then the attacker holds the database credentials.
- **Mitigation:** exact pin of `pypdf` 7.0.0, no secret in the worker other than the database URL, non-root user, limits proved by real-process tests.
- **Recommendation:** accept as debt but add to TD-030 the four omissions above; close in change 13.

### R-06 Writable bind mount `./backend/app:/app/app` in `backend` and `worker`
- **Severity:** Low-Medium, development only (**minor**). **Category:** potential. **Where:** `docker-compose.yml`.
- **Evidence:** no `:ro`, so a compromised worker (R-05) could write into the host source tree that a developer later runs. Not exploited (the child's `RLIMIT_FSIZE=0` stops direct writes; the parent could write).
- **Recommendation:** mount `:ro` for the worker (it has no reason to write) or accept as debt; production images copy the code.

### R-07 Unsupported claims: see section 4. Severity Low.

### R-08 HNSW plus subject filter behaviour is deferred
- **Severity:** Informational. **Category:** known debt (TD-022, TD-025, TD-026). The isolation query in `chunk_repository.py` is scoped by subject and actor in SQL; mutation M5 (removing the subject filter) is caught. Not part of this change's code.

### R-09 Filenames are not normalised for look-alike and zero-width characters
- **Severity:** Informational. **Category:** potential. Only controls and bidi characters are stripped (compare TD-018); display-only spoofing inside a teacher's own subject. No UI was run; React escaping is the control.

### R-10 The upload guard path regex is hard-coded to `/api/v1/...`
- **Severity:** Informational. **Category:** potential. `is_upload_request` matches `^/api/v1/subjects/[^/]+/documents/?$` on `scope["path"]`; under a root path or prefix the guard would silently not apply. Not reproducible today; add a startup assertion or a test with a prefix.

## 4. Unsupported or overstated claims
- `tests/unit/test_pdf_child.py` docstring says CI and the worker image run its tests; the AES test never runs anywhere (`cryptography` is not in `uv.lock` nor any extra). TD-031 mentions one skipped test, not that it can never run.
- "Coverage 99 %" could not be reproduced by the reviewer offline.
- Spec and design "finishes or fails ... even across restarts" holds only if something restarts the worker (R-02).
- `docs/data-model.md` on the downgrade omits that documents stay `pending` forever (R-04).
- TD-034 does not record the measured amplification (R-01).
- TD-030 "remaining container hardening" omits outbound network, the pids limit, the writable source mount and the shared superuser database role (R-05, R-06).
- The seven tests skipped in the reviewer's container (no `git`) are the checks that no `.env*` is tracked; they run in CI.

## 5. Verified correct (what was attacked)
The `404` rule and all role and ownership paths; pre-body decisions (unauthenticated or student requests with a declared 1 GB get 401/403/413 without reading the body, chunked 12 MB gives 413, exactly 10 MB gives 202 and 10 MB + 1 byte gives 413); idle timeout 408 at 20.0 s; disconnects leave no 500; lying `Content-Length` gives 400; multipart limits answer 422 with fixed reasons and no 500; admission locks, fencing, `SKIP LOCKED`, lock order, attempts cap, sweep and erasure of bytes on every terminal path; the Alembic round trip and drift check; worker and database secret separation, image contents, branch history and log hygiene; the frontend change is only the generated types (no UI, so no XSS or authorization surface).

## 6. Verdict: PASS WITH GAPS
**Blocking:** none. **Major (fix before closing, or the user's explicit acceptance recorded in the debt register):** R-01, R-02. **Minor:** R-03, R-04, R-06. **Acceptable risk or debt:** R-05, R-08. **Informational:** R-09, R-10. Task 17.3 (Dependabot #1) remains open.

Recommended order: (1) R-02, the cheapest; (2) R-01 with a test that a 2M-character single-token text fails or finishes within a bound; (3) R-04; (4) extend TD-030, TD-034 and TD-035 for R-03, R-05, R-06; (5) re-run the gates after the last change, including `ruff check --no-cache`; (6) decide Dependabot #1.

## 7. Side effects and cleanup (reviewer)
Created the Docker network `g16r-net` and the containers `g16r-db`, `g16r-api`, `g16r-worker`, `g16r-tests` and short-lived `--rm` clients; `docker kill`, `start` and `stop` only on `g16r-worker`; scratch files under the session scratchpad, with the ones holding the throwaway password removed. All `g16r-*` resources were removed. Ports 8000, 5173 and 5442 and the development database `asistenteia` (0004) were not touched.

## 8. Checks by the implementer after receiving the report
The review was delivered as text and saved here by the implementer. Independently confirmed: `git status` shows only the seven untracked reference files and HEAD is still `172288a`; no `g16r-*` container or network remains; `docker-compose.yml` has no `restart` entry for any service and the only healthcheck is the database's (R-02); the `0005` downgrade drops `ingestion_jobs` and `error_code` and does not touch the status of in-flight documents (R-04); the only `pragma: no cover` in `app` is the one named. R-01 and the other experiments were not repeated by the implementer. No finding has been fixed and no technical-debt entry has been changed.
