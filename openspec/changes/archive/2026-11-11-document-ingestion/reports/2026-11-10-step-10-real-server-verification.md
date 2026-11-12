# Group 10: real-server and real-process verification

Branch `feature/document-ingestion`. Tasks 10.1, 10.2 and 10.3, plus the targeted review of two controls of group 9. No later group; migration `0005` was not applied to the development database (`asistenteia` stays at `0004`; `asistenteia_test` ends without tables).

## Why Playwright does not apply (task 10.3)
This change has no user interface: it adds HTTP endpoints, a queue and a worker. The committed Playwright suite drives a browser against screens, and no screen touches these endpoints until change 7. What Playwright would add (a real client over a real transport) is covered by the tests below, which talk raw HTTP to a real Uvicorn process started with the production arguments (`--factory --no-proxy-headers`) on a free port (never 8000 or 5173), and to a real `python -m app.worker` process, against PostgreSQL with pgvector:

| Area | Test file |
|---|---|
| early `413` (declared length, chunked body), `408` for idle and slow-drip clients, disconnects without trace, other endpoints during slow uploads, slots coming back | `tests/integration/test_upload_server.py` (group 9) |
| abusive multipart answered `422` in under 2 s (7 shapes), 60 slow clients (fast `503` / `408`, health stays under 1.5 s), no temporary file left or held open after mixed uploads | `tests/integration/test_real_server.py` |
| process killed before the commit (no `202`, nothing stored) and after the commit before the response (no `202`; document, job and bytes durable and already visible while the server is paused) | `tests/integration/test_real_server.py` |
| order of the dependency exit and the response | `tests/integration/test_real_server.py` |
| upload, poll to `ready`, failed document with its code, delete during processing, killed worker and recovery without duplicates (`attempts = 2`), API restarted with `pending` documents, exhausted attempts ending `failed` with `PROCESSING_INTERRUPTED`, isolation between teachers and students, no marker in either process log | `tests/integration/test_real_processes.py` |

The frontend checks of task 14.1 (types, mocked Playwright) belong to a later group; the contract and the generated types did not change.

## Findings of the real-server runs
- **Order of the dependency exit and the response** (FastAPI 0.162, Uvicorn with `httptools`): the response is sent *before* the `yield` dependency exits. With the exit delayed by 2 s the client had its `204` in under 1.5 s, the exit had not run, and the document was already deleted. This is why the upload and the delete commit explicitly before building the answer; the test pins the behaviour so a framework upgrade that changes it is noticed.
- **`202` only after the commit**: while the server is paused inside `commit` the transaction is not committed, and killing the process there leaves nothing. Paused after the commit (before the response), another connection already sees `documents = 1`, `jobs = 1`, `payloads = 1`, the client has no response, and after the kill the data is still there.
- **Recovery**: a worker killed with SIGKILL mid-job is replaced by another one; chunk indexes are consecutive and the job shows two attempts; three killed attempts end with the sweep failing the document as `PROCESSING_INTERRUPTED` and the bytes erased.

## Review of two controls of group 9
1. **`UploadSlots.try_acquire` / `release`.** The lock stays. The counter is a read-modify-write: without the lock two threads could both pass the limit check, and two releases could lose an update. Not seeing the race under the GIL is not a proof of absence: the interpreter may switch threads between any two bytecodes. The class now takes an optional `pause_between_read_and_write` that the tests use to force the interleaving deterministically: a `Meeting` (a two-party barrier, armed after the set-up) makes two threads reach the point between the read and the write together. With the lock the meeting cannot happen (the barrier times out and one thread goes first); without it both threads meet and the count is wrong. Tests: two acquires of the last slot (exactly one wins), two releases (no lost update), an acquire interleaved with a release. Red before the seam (3 failed with `TypeError`), then green. Removing the lock from `try_acquire` or from `release` is **killed** (the group 9 tests let the first survive). Residual risk: none known for the counter; the seam is `None` in production and costs one comparison.
2. **Closing forms and temporary files.** The explicit `await form.close()` in a `finally` stays, and Starlette closes its own files when parsing is interrupted (`except BaseException` in `MultiPartParser.parse`). `tests/integration/test_upload_resources.py` replaces `SpooledTemporaryFile` with a tracking subclass that the test keeps referenced, so nothing can be closed by CPython releasing the last reference. After a success, a file that rolled to disk, 415, 422 (empty, two files, extra field), 413 on the file, 409, 503 (failed commit), an unexpected error, and a timeout, an oversize body and a disconnect in the middle of a file, every tracked file is closed. Removing the `close` is **killed** (it survived the group 9 tests). Open-file checks of the real server process: `/proc/<pid>/fd` is inspected after uploads that spool to disk, abusive bodies, 60 slow clients and disconnects; no file of the process's temporary directory is held open and the directory is empty. On Linux a temporary file is unlinked at creation, so listing the directory alone cannot detect a leak; the descriptor check can.

## TDD evidence and mutations
- The new real-server and process tests exercise behaviour implemented in groups 8 and 9, so they were green on first run (the earlier groups' red runs apply); their value is shown by mutation. The slots tests were red first (see above).
- Mutations of group 10 (8): lock removed from `try_acquire`; lock removed from `release`; form not closed; upload never committed; delete not committed before the `204`; worker without the sweep at start; no idle deadline; slot cap raised to 10,000. First pass: 2 survivors (the `release` lock, because the barrier had been used up by the test's own set-up; and the idle deadline, because the real-server test only bounded the time by the total deadline). Both closed (an armed meeting point; the idle `408` must arrive before the total deadline). Final: all 8 killed.

## Results
- Full backend suite in the Linux worker image against PostgreSQL: **1684 passed, 1 skipped (AES), 16 deselected (`realmodel`)**; coverage of `app` **98 %** (`upload_guard` 99 %, `document_deps` and `endpoints/documents` 100 %, `worker` 99 %).
- `ruff check --no-cache`, `ruff format --check`, `mypy --strict app tests` (167 files) clean, `pip-audit` without vulnerabilities (no dependency changed), `openspec validate --strict` valid. All were repeated after the last change, including the tests added at the end.

## Risks and deviations
- The real-server and process tests are Linux only and take about 70 s together; they start one to three processes each.
- `tests/server_support.py` and `test_upload_server.py` duplicate a few socket helpers (kept to avoid rewriting the group 9 file).
- The 60-client test depends on timing (fast `503` within 3 s, health under 1.5 s); the margins are wide, but a very slow CI runner could need them widened.
- The host virtual environment is still blocked by Windows Application Control; everything ran in the Linux image.
- Dependabot alert #1 remains open (planned in 15.1 and 17.3).
