# Group 9: document endpoints, upload guard and leak tests

Branch `feature/document-ingestion`. Tasks 9.1, 9.2 and 9.3. No group 10 or later work; migration `0005` was not applied to the development database; `docs/api-spec.yml`, the generated frontend types, `prompts.md` and `readme.md` are untouched (the contract of group 4 is now served by the real application).

## What was added
- `app/api/v1/endpoints/documents.py`: `POST`, `GET` and `DELETE` on `/subjects/{subject_id}/documents`; `app/api/document_deps.py`; `app/schemas/document.py` (`Document`); `app/services/document_service.py`; `app/services/upload_inspection.py`; `app/core/upload_guard.py` (ASGI guard and upload slots); four new error classes (`413`, `415`, `408`, `422` with a fixed `details.reason`).
- **Order of decisions of the upload**: authentication (`401`), role (`403`), identifier and ownership (the same `404` for unknown, foreign and malformed ids), per-address rate (`429`), a lock-free look at the queue (early `503`) - all in a short session closed before the body is read - then the upload slot (`503` when `UPLOAD_MAX_IN_FLIGHT` uploads are being received), then the body.
- **The body**: read in the handler with `request.form(max_files=5, max_fields=5, max_part_size=64 KiB)`; the guard counts the bytes that arrive (limit = `MAX_UPLOAD_MB` plus 64 KiB of multipart framing), refuses a declared length above the limit on the first read, refuses the chunk that crosses the limit, and enforces the total deadline (from the first read) and the idle gap (empty chunks are not progress). The file itself is then checked against the exact limit. Parser failures are `422 MALFORMED_MULTIPART`; a missing `file` part `FILE_PART_MISSING`; extra parts `UNEXPECTED_FIELDS`; no `422` is produced for framework errors in general.
- **Commit before `202`**: `_store` validates (name, empty, type), opens its own session, calls the service, `commit()`s and only then builds the `Document`; any `SQLAlchemyError` is `503 SERVICE_UNAVAILABLE` with a fixed message and a rollback. `DELETE` also commits before the `204`.
- The API engine now applies `statement_timeout` 15 s and `idle_in_transaction_session_timeout` 30 s (pending since group 8).
- The strict `xfail` of `test_the_application_publishes_the_document_contract` is removed; the test passes against the real application.

## Decisions to review
1. A malformed `subject_id` or `document_id` is the same `404` as an unknown one (identifiers are read from `request.path_params`, not declared as typed parameters): the contract pins `GET`/`DELETE` to `200/204, 401, 403, 404`, and the framework would add a `422`. Other subject routes still answer `422` for a malformed id.
2. A declared `Content-Length` above the limit is refused with `413` even if the client would then send a small body (the early check of the spec wins over the "declared large, sent small" scenario; with a real server the declaration is binding anyway).
3. A request whose content type is not `multipart/form-data` is `422 MALFORMED_MULTIPART` without reading the body.
4. PDF signature: the file must start with `%PDF-`.
5. The multipart limits are 5 parts and 5 fields: two to five files, or extra fields, are `UNEXPECTED_FIELDS`; more is `MALFORMED_MULTIPART`.
6. Task 10.1 (the full real-server set: kill between steps, order of the dependency exit and the response, many slow clients) is not done; `test_upload_server.py` covers only what 9.2 and 9.3 name.

## TDD evidence
- Red run before any implementation (commit `cd84041`): `102 failed, 17 passed, 18 errors` over the new files and the contract test (3 modules not importable; the routes, the guard and the service did not exist; the contract test, now without `xfail`, failed).
- First green run of the implementation: unit 95 passed; `test_documents_api.py` 98 of 100 (two flaws of the tests themselves, fixed: an exact fixed message and a valid chunk); leaks, concurrency and real-server files passed.

## Mutation checks
56 mutations (guard 14, endpoint 16, dependencies 5, inspection 11, repository/app wiring 5, plus slots). First pass: 8 survivors. Closed with new tests: idle gap measured from the last byte, empty chunks never waking the application, a database error that is not a connection failure mapped to the fixed `503`, the 256-character name boundary, an invalid mutation of the PDF signature repeated (killed), and the redundant `refresh` removed (the insert already returns the defaults). **Accepted (2)**: removing the lock of `UploadSlots.try_acquire` (a data race that the GIL makes unreproducible in a test) and not closing the form (CPython closes the temporary file at once when the last reference goes; an open-file check of the server process was added and passes).

## Results
- Full backend suite in the Linux worker image against PostgreSQL: **1645 passed, 1 skipped (AES), 16 deselected (`realmodel`), 0 xfailed** (plus one test added afterwards, `test_no_database_connection_or_transaction_is_held_while_the_body_is_read`, 10 of 10 passed in its file); coverage of `app` **98 %** (`document_service`, `upload_inspection`, `document_deps`, `endpoints/documents`, `schemas/document` 100 %; `upload_guard` 99 %).
- `ruff check --no-cache`, `ruff format --check`, `mypy --strict app tests` (163 files) clean; `pip-audit` no known vulnerabilities (no dependency changed); `openspec validate --strict` valid.
- Concurrency: 49 documents plus 24 simultaneous uploads leave exactly 50; the last queue slot goes to exactly one of 24 subjects; 3 slots of 24 subjects; pending bytes never exceed the maximum; 40 simultaneous uploads do not exhaust the pool.
- Real Uvicorn (production arguments, free port): `413` with only the headers sent, `413` for a chunked body while the client is still sending (less than 4 MB read), `408` for an idle client (about 1 s) and for a slow drip (at the total deadline), 12 disconnects leave nothing and no `Traceback` or `ClientDisconnect` in the log, no open temporary file, and `health`, `subjects`, `users/me`, the document list and `login` answer in under 1.5 s while every upload slot is held and 20 connections are stalled.
- The API image (397 MB) imports the application without `torch`, `sentence_transformers`, `pypdf` or `langchain_text_splitters`, and none of them is installed there.
- The frontend was not run: `docs/api-spec.yml` and the types are unchanged.

## Deviations and notes
- The host virtual environment is still blocked by Windows Application Control (see group 8); everything ran in the Linux image.
- The real-server tests are Linux only (they inspect `/proc`).
- The development database `asistenteia` stays at revision `0004`; `asistenteia_test` ends without tables.
