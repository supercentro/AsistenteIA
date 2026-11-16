# Group 2: privilege inventory and matrix (2026-11-12)

Branch `feature/database-least-privilege`. Authorised by the owner: group 2 only, plus approval of the artifacts and of decision DD-9 (option A) as the target design. Nothing of groups 3 to 19 was started. No Docker, no database, no role, no `.env` and no Compose file was touched: free memory was 5.5 GB (below the 6 GB gate), and group 2 needs none of them.

## What was built

| Task | Result |
|---|---|
| 2.1 failing tests first | `backend/tests/unit/test_db_privileges_matrix.py` (19 tests) and `test_db_privileges_inventory.py` (13 tests). Failing run: `tdd-failing-run.txt` (collection error `No module named 'app.db_privileges'`, taken with the matrix module moved away). **Deviation:** the inventory (2.2) was written before the tests, because the tests need it and its output was how I learned what to assert; the matrix module (2.3) was written after the tests were drafted but before the failing run was recorded, so the failing run was reproduced by removing the module. The compensation is the set of mutation checks below |
| 2.2 inventory | `backend/tests/privilege_inventory.py` (static `ast` analysis, call graph from the API, worker and CLI entry points, own parser for the raw SQL). Output: `privilege-inventory.txt` (regenerate with `cd backend && uv run python -m tests.privilege_inventory`) |
| 2.3 matrix | `backend/app/db_privileges.py` (data only, imported by nothing at runtime yet) and `backend/tests/privilege_matrix_check.py` (the comparison) |
| 2.4 new table or column fails; mutation checks | `mutation-checks.txt`: five edits of the real matrix file and one edit of the application code (a new attribute assignment in `ConsentService.record`), each failed the suite; the files were restored (verified byte for byte). Thirteen in-memory mutations run on every test run (missing grant, extra grant, extra `DELETE`, widened `SELECT`, dropped table, dropped role, unknown table, missing lock carrier, new column, new table, closed gap, stale gap) |
| 2.5 advisory lock or row lock | Decision: **keep `SELECT ... FOR UPDATE` and the lock-carrier `UPDATE (description)`** (design DD-3, note 6). It is an analysis, not a measurement |

## How the inventory works, and its limits

It reads `app/` with `ast`, builds a call graph (receivers resolved through annotations, `Annotated[...]` aliases per module, `__init__` assignments and Protocol implementations; method references such as `self._guard(self._service.sweep)` count as calls), starts from every function of `app.api`, `app.worker` and `app.cli`, and lists per actor and table the SELECT, INSERT, UPDATE, DELETE and row-lock needs of: ORM and Core constructs, constructors of mapped classes, attribute assignments on mapped objects, `session.get`, `RETURNING`, `from_select`, and every `text()` statement (SQL pieces concatenated from constants and from literal call-site arguments; parsed for tables, aliases, `SET` targets, `INSERT` columns, `RETURNING`, `FOR UPDATE [OF]`). Every call whose method name matches a function that holds a statement and whose receiver cannot be resolved is reported; the suite requires that list to be empty. Every function that holds a statement and no actor reaches must be declared (`UNREACHED_ALLOWED`).

Honest limits: (1) it is static, so it over-approximates reads (every `Model.column` used in a function counts as a read) and cannot see statements built from dynamic strings that are not literals in the project; (2) five SQLAlchemy behaviours are assumptions, listed in `ASSUMPTIONS` and in the inventory file, and are proved against a live database by task 5.4 (ORM INSERT returns the key and server-generated columns; Core insert of rows may `RETURNING` the key; flush of an attribute assignment is `UPDATE ... WHERE pk`; a row lock needs one `UPDATE` column; `select(Model)` reads every column); (3) the SQL parser is regular-expression based and checked by hand-written goldens for the shapes that exist (UPDATE with expression and `RETURNING`, unqualified single-table, join with `FOR UPDATE OF`, CTE then UPDATE, INSERT, DELETE); I also compared its output with my reading of every raw statement of `ingestion_job_repository.py` and found no difference; (4) it does not prove the privileges work, only what the code needs: the live proof is groups 4 to 6 and 9.

## Consolidated matrix

See `design.md` DD-3 (the table and the six notes) and `privilege-inventory.txt`. Summary of what differs from the matrix of the spike, found only because it is now derived:

- `INSERT` is column-level everywhere; the application role cannot read `ingestion_jobs.locked_by` (the fencing token), `locked_until` or `document_id`; the worker matrix equals the spike's.
- The registration still inserts `role`: a **known gap** the suite records (`KNOWN_GAPS`) until task 8.4.
- The application `SELECT` on `document_chunks` is **anticipated** (the retrieval query has no entry point yet) and is allowed only through a named extra root that the suite removes as soon as an endpoint reaches it.
- `DocumentRepository.get_for_teacher` is dead code (declared, no grant).
- The CLI needs only `users` (`SELECT`, `INSERT` with `role`).

## DD-9 and the five identities

Applied at the owner's request: proposal, design (DD-1, DD-3, DD-9, open questions, matrix), the `database-roles` spec (five identities, four working roles, CLI scenarios) and `role-based-access`. Until group 8 exists the CLI keeps using the application role. Nothing was implemented: no CLI role, no migration `0006`, no code in the registration path, no environment file. Task 8.1 (record the decision) was ticked because the decision is documentary; 8.2 to 8.7 stay open and unauthorised.

## Gates

| Gate | Result |
|---|---|
| `ruff check --no-cache .` and `ruff format --check .` (backend) | clean |
| `mypy --strict app tests` | no issues in 180 source files |
| `pytest tests/unit` | 914 passed, 110 skipped, **3 failed** (see below); the 32 new tests pass |
| `openspec validate database-least-privilege --strict` and `--all --strict` | valid, 18 of 18 |
| Integration and end-to-end tests | **not run**: they need PostgreSQL in Docker and the free memory was below 6 GB; group 2 does not change what they cover |

The three failures are existing tests that do not run on this Windows machine: `test_worker_health.py::test_the_defaults_leave_room_for_the_beat_interval` asserts a POSIX `/tmp/` path, and the two `test_worker_settings.py` tests import the worker in a subprocess that fails inside the Windows virtual environment (`limits` package). None touches the new files; `main` is green in Linux CI at `3b312e4`. I did not run them on a clean checkout of `main` here, so "existing" rests on the traces above.

## Evidence still pending (not closed, not claimed)

Adoption of a database with data, recovery of ownership, readability of the catalogs, connection limits and safe rollback were observed only in the first spike run and their output was not kept. They remain open until tasks 4.5, 5.1, 5.3, 5.9 and 16.2 reproduce them and keep the results.

## Risks and decisions pending

- Decision 2.5 is an analysis; if the owner prefers an advisory lock, it is a separate, tested change (new handling of the foreign-key race and new concurrency tests, plus changes to the archived design A5 behaviour).
- The API can read queued upload bytes through `ingestion_jobs.payload` (the admission query sums their sizes); a size column would remove it.
- The five `ASSUMPTIONS` are unproved until task 5.4.
- Group 3 and the next groups need the owner's authorisation; groups 16 and 17 need their own.
