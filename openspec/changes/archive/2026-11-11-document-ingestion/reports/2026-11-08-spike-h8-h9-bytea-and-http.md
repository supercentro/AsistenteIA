# Spike H8 and H9: `bytea` in PostgreSQL, and multipart, size limits and timeouts with a real server

Date: 2026-11-08. Tasks 1.8 and 1.9. H8 ran on a disposable PostgreSQL 15.19 container (`pgvector/pgvector:0.8.7-pg15`, own private Docker network, **no published port**, 2 GB, 2 CPUs; its own database `spike`, random password never written down). H9 ran in a container without network (`--network none`) with a throw-away ASGI application and Uvicorn 0.54.0 started like the Dockerfile (`--no-proxy-headers`) on the container's loopback port 18765. Neither used the development or test databases, the Compose services, or the ports 8000, 5173 and 5442. Scripts: `reports/spike-scripts/h8_pg.py`, `h8_vf.py`, `h9_server.py`, `h9_client.py`.

## H8. A 10 MB `bytea` payload

Settings of the server: `wal_level=replica`, autovacuum on, `autovacuum_vacuum_threshold` 50, `autovacuum_naptime` 1 min.

| Measure | Result |
|---|---|
| Insert of 10 MB (incompressible), median of 5 | **136 ms** (71 to 154 ms); WAL generated **10.7 MB** (the whole payload) |
| Insert of 10 MB of repetitive text | 150 ms; WAL only 0.12 MB (TOAST compresses it with `pglz`) |
| Read back 10 MB | 73 ms |
| Table after 6 inserts | heap 0.01 MB, TOAST **51.4 MB** |
| Set `payload` to `NULL` on 5 rows | 59 ms, WAL **52.8 MB** (about 10.5 MB per payload: the old TOAST rows are deleted, 26,270 dead tuples) |
| Size right after the null-out | unchanged (TOAST 51.4 MB) |
| Autovacuum | cleaned the dead TOAST tuples within the 100 s that were waited (dead 26,270 to 0, `last_autovacuum` set); the **file stayed 51.4 MB** |
| Manual `VACUUM` | 1 ms; sizes unchanged |
| `VACUUM FULL` | TOAST 0.12 MB; for 20 nulled payloads it took **27 ms** and left 32 kB |

Where the bytes of a deleted payload remain (a 50-byte marker inside the payload was searched in the server's files):

| Moment | Files holding the marker |
|---|---|
| After the insert | 1 data file, 4 WAL files |
| After setting the payload to `NULL`, before vacuum | 1 data file, 5 WAL files |
| Logical dump (`pg_dump --data-only`) of the table after the null-out | **0** |
| Base backup (`pg_basebackup`) taken after the null-out, before vacuum | **1 data file holds it** |
| After autovacuum and after a manual `VACUUM` | still 1 data file (vacuum does not overwrite free pages), 3 WAL files |
| After `VACUUM FULL` and a checkpoint | **0 data files**, but **3 WAL files still hold it** (recycled WAL segments are not zeroed) |

Consequences (they confirm the design's warning in A1 and quantify it):
- Each 10 MB job writes about **21 MB of WAL** (10.7 MB on insert and 10.5 MB on clearing). Database backups and WAL archives made while a job exists can contain the file; a logical dump taken afterwards does not.
- Clearing the payload does not remove the bytes from the table files until the pages are reused or the table is rewritten; `VACUUM FULL` of this small table takes tens of milliseconds, so a periodic `VACUUM FULL ingestion_jobs` in the sweep is cheap (it takes a short exclusive lock) and removes the bytes from the data files. The WAL copy lasts until the segment is overwritten and the retention of any archive or backup.
- Autovacuum is enough to remove the dead TOAST tuples of a single payload (they exceed the threshold of 50), so no per-table setting is required for that; it does not shrink or zero files.

Locks and transactions:
- A transaction that takes the subject row lock, then the global advisory lock, then inserts 10 MB holds the locks for a median of **63 to 75 ms**. Simultaneous uploads: 1 upload 78 ms in total; 4 uploads 314 ms (maximum lock wait 235 ms); 8 uploads 972 ms (maximum lock wait 848 ms). With `UPLOAD_MAX_IN_FLIGHT` 4 the longest wait stays below 0.3 s.
- `statement_timeout = '200ms'` cancelled a 1 s statement; `idle_in_transaction_session_timeout = '1s'` terminated an idle transaction (the next statement fails with `IdleInTransactionSessionTimeout`). Both work as designed.
- The final write of a document is cheap: 2,000 chunks with 384-dimension vectors by `COPY` took **121 ms** in one transaction (500 rows by `executemany` took 18 ms).
- Suggested values: `statement_timeout` 15 s for the API and 60 s for the worker; `idle_in_transaction_session_timeout` 30 s. The 10 MB insert (150 ms) and the final write (0.1 s) are two orders of magnitude below them.

## H9. Multipart, real sizes, interruptions, timeouts

Prototype of the design's guard (pure ASGI, outermost): counts the bytes actually received, answers `413` itself when more than 10 MB plus 64 KiB arrive or when `Content-Length` already exceeds that, enforces an idle gap (3 s) and a total deadline (5 s) in this test, answers `408` itself, then reports a disconnect to the application; the endpoint authenticates first and reads the form with `request.form(max_files=1, max_fields=2)`. Versions: FastAPI 0.162.0, Starlette 1.10.0, `python-multipart` 0.0.33.

| Case | Result |
|---|---|
| Valid small upload | `202` |
| No credentials, body never sent | `401` at once (decided before the body is read) |
| `Content-Length` 50 MB, no body sent | `413` in **0.00 s** |
| Chunked body of 30 MB, no `Content-Length` | `413`; the client could send about 12 MB before the connection was closed |
| Declared 200 bytes, sent 20 MB | the 200 bytes are the body; the excess is parsed as a new request and rejected (`400`, connection reset); it is never buffered |
| Connected client stops sending (idle gap 3 s) | **`408` received after 3.0 s** |
| Slow drip of 1 byte per second (total deadline 5 s) | **`408` received after 5.0 s** |
| Client disconnects after 3 of 5 MB | files in `/tmp`: 2 before, 2 after; the server keeps answering |
| 20 stalled uploads open at once | all 20 received `408` after the deadline; meanwhile each ping to another endpoint took **0.5 ms** |
| 10 MB file (exactly at the limit) | `202`; server peak memory 62 to **71 MB** (+9 MB), no leftover temporary file |
| 10 MB + 70 KB file | `413`, memory unchanged |
| 5,000 form fields / 3,000 file parts / one 9 MB part header / 9.5 MB preamble / two file parts | each answered **`400` in under 10 ms** (Starlette and `python-multipart` limits) |
| No `file` part | `422` (application) |
| Empty file part | `202` in the prototype (the real service must check size greater than zero) |
| Synchronous `yield` dependency like `get_db` whose exit takes 1 s | **the response reached the client after 0.00 s and the exit finished 1.00 s later** |

Conclusions:
- **`408` is viable**: a pure-ASGI guard on Uvicorn delivers it to a connected client, both for an idle client and for a slow-drip client, and it does not block other requests. When the client closes the connection no response can be sent, and nothing is stored or leaked. The contract can keep `408` (it is no longer conditional), with the wording that it applies to clients that stay connected.
- **The `202` guarantee needs the explicit commit** (decision D2 confirmed): in FastAPI 0.162.0 a `yield` dependency exits after the response has been sent, so `get_db`'s commit would run after the client already holds a `202`.
- Starlette's multipart errors are `400` by default; the contract says `422`, so the handler must catch the multipart exception and answer `422` with the standard error body.
- The guard must absorb `ClientDisconnect` after it has answered, otherwise Uvicorn logs 22 error traces per run (the first run showed it; the corrected prototype logged none).
- Memory per upload is about the file size (+9 MB for 10 MB); four uploads in flight add about 40 MB, plus the copy that the database driver makes of the parameter.
- Recommended deadlines for the real service: total body deadline 120 s and idle gap 20 s (10 MB over a 1 Mbit/s connection takes about 80 s; 60 s would cut such a teacher). This is a decision for the user.
- Not measured: HTTP/2 or a reverse proxy in front of Uvicorn (the Dockerfile runs without proxy headers); behaviour with `h11` instead of `httptools`.
