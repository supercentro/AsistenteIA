# Group 6: loaders and isolated PDF child

Date: 2026-11-09. Branch `feature/document-ingestion`. Tasks 6.1, 6.2 and 6.3. No database, endpoint, worker or repository code: two modules under `backend/app/rag/` and their tests.

## What was added
- `app/rag/loaders.py`
  - `DocumentLoadError(code)`: carries one `DocumentErrorCode` and the fixed message of the catalogue; never content, library text or an exception chain. Nothing is logged.
  - `load_text` / `load_markdown` (task 6.1): strict UTF-8 (`utf-8-sig`: one leading BOM accepted and removed, invalid bytes and NUL give `CORRUPT_FILE`), character cap (`TEXT_TOO_LARGE`), the existing `normalize_text`, blank result gives `NO_EXTRACTABLE_TEXT`. One `Page(None, text)`. Markdown is data: `<script>`, HTML, links and syntax stay unchanged.
  - `load_pdf(payload, PdfLimits)` (task 6.2): starts `python -I pdf_child.py MEM CPU PAGES CHARS` with a minimal environment (`LC_ALL`, `PATH`), `stdin` = bytes (written by a thread so a child that never reads cannot block the parent), `stdout` read through `select` with the wall-clock deadline and the byte cap, `stderr` discarded, `close_fds`, own session. Any breach kills the process group, reaps the child and closes the pipes. The output protocol is validated strictly (JSON lines `page`/`text`, `end`, `error`; types, order, extra keys, data after `end`, exit status). Exit by `SIGXCPU` gives `PROCESSING_TIMEOUT`, `SIGKILL` gives `RESOURCE_LIMIT_EXCEEDED`, any other failure gives `PROCESSING_FAILED`. The child may only report five codes; anything else becomes `PROCESSING_FAILED`. Text of each page is normalised in the parent; pages without visible text are skipped, page numbers are kept; no page with text gives `NO_EXTRACTABLE_TEXT`. Outside Linux it raises `UnsupportedPlatformError` and starts nothing (no in-process fallback).
  - `PdfLimits` and `PdfLimits.from_settings(settings)` (MB to bytes).
- `app/rag/pdf_child.py`: self-contained (standard library and `pypdf` only). Applies its own limits before reading `stdin`: `RLIMIT_AS`, `RLIMIT_CPU` (soft limit plus 2 s, so `SIGXCPU` ends it), `RLIMIT_FSIZE=0`, `RLIMIT_NOFILE=32`, `RLIMIT_CORE=0`. Checks `is_encrypted` first, then the page count (before any extraction), then the character total page by page. `MemoryError` gives `RESOURCE_LIMIT_EXCEEDED`, any other failure `CORRUPT_FILE`. Lone surrogates are removed. Only protocol lines are written.
- `pyproject.toml`: `[tool.mypy] platform = "linux"` (the child uses POSIX-only calls; CI and the worker are Linux, and mypy on Windows rejected them).
- Test support: `tests/pdf_support.py` (PDFs generated from bytes: text per page, scan, many pages, 600,000-line page, flate bombs, XFA, bad JPEG, equal-offset xref stream, encrypted, metadata) and `tests/child_support.py` (a stand-in child to test the parent protocol).

## TDD evidence
Tests committed before the code (`71d24ef`): `test_loaders_text.py`, `test_pdf_child.py`, `test_pdf_wrapper.py`, `test_loader_leaks.py`.
- **Failing run before the implementation**: 4 collection errors, `ModuleNotFoundError: No module named 'app.rag.loaders'`.
- **After the implementation** (Linux worker image, offline code mount): 195 passed, 1 skipped (AES: the `cryptography` package is not installed; explicit skip reason). On Windows the Linux-only tests are skipped with an explicit reason and the platform guard test runs.

## Mutation checks (56 mutations, `mutate_g6.py`, run in the Linux image)
Removing or weakening each guarded item makes at least one test fail: address space, CPU limit (and soft/hard gap), file writes, open files, core dumps, order limits-before-input; encrypted check, page cap, character cap (and off by one), surrogates, end marker, memory error mapping; BOM, invalid bytes, NUL, text cap (and off by one), normalisation, blank text, error chaining; platform guard, stderr discarded (two forms), minimal environment (two forms), `close_fds`, own session, `-I`, wall-clock deadline (two forms: a mutation that removes the deadline hangs and is stopped by the harness timeout), output cap (and off by one), `SIGXCPU` and `SIGKILL` mapping, allowed child codes, boolean page numbers, page order, page keys, exit status, incomplete stream, page cap recheck, no pages, normalisation in the parent, killing the child, MB to bytes, settings mapping and wrong arguments.

First pass: 52 detected, 4 survivors, handled as follows:
| Survivor | Resolution |
|---|---|
| data accepted after the `end` marker | new cases (a new page and a second `end` after `end`); now detected |
| process group not killed | new test with a grandchild process in the group; now detected |
| other signals ignored | the branch was redundant (a non-zero exit already fails the stream); removed |
| feeder thread not joined | still survives: the join only guarantees the thread has ended when the call returns, and the thread ends anyway when the pipe breaks. Kept for hygiene; a thread-name test asserts the observable result. Accepted as equivalent |

## Real-file checks (Linux, real child)
Text per page with numbers; blank pages skipped; scan; PDF without pages; truncated, empty, non-PDF; encrypted without and with password (RC4); page cap (and exact boundary, and checked **before** extraction using a hostile first page); character cap (and boundary); output cap; **CPU limit** stops a 5 MB file with a 600,000-line page in about 1 s while the wall clock is 60 s; **wall clock** stops it at 1 s with a 300 s CPU limit; **memory limit** (100 MB) stops a 60 MB flate stream; a 300 MB stream is refused by `pypdf` (`CORRUPT_FILE`); the worker keeps running after each breach; XFA form read as text; malformed JPEG never decoded; equal-offset xref stream ends in a controlled code.
Not covered: AES-256 encryption (package missing in the image, test skipped); the advisory-specific files are shaped from the advisory descriptions and are not exploits.

## Leak tests (6.3)
Markers in the content, in invalid bytes, NUL, over-cap text, PDF metadata (info, outline, annotation), an encrypted PDF password, a truncated PDF, the child's `stderr`, an error detail, a malformed line and a wrongly typed field never appear in `str`, `repr`, `args`, the formatted traceback, `caplog` (DEBUG, all loggers) or the captured file descriptors. Successful and failing loads emit no log record. Errors are not chained to decoder or parser errors.

## Quality gates
`ruff check --no-cache`, `ruff format --check`, `mypy --strict app tests` clean; `pip-audit` no known vulnerabilities (no dependency change); frontend gates not rerun (contract and types untouched); `openspec validate document-ingestion --strict` valid, `--all --strict` 15 of 15.
Strict xfail of the real-application contract test still `xfailed`, reason "The document routes are implemented in group 9 (task 9.1)"; the routes do not exist yet.

## Full run
Windows host with the isolated test database: **1070 passed, 107 skipped (Linux-only PDF tests and AES), 16 deselected (`realmodel`), 1 xfailed**, coverage of `app` 91 % there because the Linux-only tests are skipped. In the Linux image the new modules reach `loaders.py` 97 % and `pdf_child.py` 86 % with branches (the body of `apply_limits` runs only in the subprocess, which line coverage does not follow, and is verified by the limit tests; the rest are `__main__` and defensive `except` lines). CI (Linux) runs all of them. `asistenteia_test` has no tables afterwards; the development database `asistenteia` is at revision `0004` with 0 documents; migration `0005` was not applied to it.

## Deviations and notes
1. The design says `python -I -m app.rag.pdf_child`. With `-I` the interpreter ignores `PYTHONPATH` and the working directory, so `-m` cannot find the package; the child is self-contained and is started by **file path** (`python -I .../pdf_child.py`). It imports nothing of the application, which also reduces the code a hostile file can reach.
2. The test seam `loaders._CHILD_SCRIPT` (monkeypatched in tests) lets a stand-in child exercise the parent protocol; it is a module constant, not a parameter reachable from input.
3. `tests/unit/test_pdf_child_unit.py` (in-process child loop) was added after the implementation to cover surrogates and error mapping without a real process; it is compensated by the mutation checks above.
4. A memory breach seen as `SIGKILL` (for example the container's out-of-memory kill) is reported as `RESOURCE_LIMIT_EXCEEDED`; other crashes (`SIGSEGV`, `SIGABRT`) as `PROCESSING_FAILED`.
5. JSON escaping can make the child's output larger than its text; text close to the 2,000,000-character cap made of four-byte characters can reach the 8 MB output cap and fail as `RESOURCE_LIMIT_EXCEEDED` instead of `TEXT_TOO_LARGE`. Both are documented, bounded outcomes.
6. The text character cap is applied to the decoded text before normalisation (a bound on work); the PDF cap counts the child's raw page text.
7. `mypy` runs with `platform = "linux"` so the POSIX-only calls type-check the same on Windows and Linux.
8. A test of my own (`SIGKILL` case) first failed because the stand-in child tried to reset the handler of `SIGKILL`, which is not allowed; the test was fixed, not the code.
