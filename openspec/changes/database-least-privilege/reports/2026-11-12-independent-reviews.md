# Independent adversarial reviews of the design (2026-11-12)

Two reviews by separate subagents with a clean context, read-only (no Docker, no database, no `.env`, no reference document), following the `adversarial-review` skill. Each review produced findings that were checked against the code or the spike before being accepted. Dispositions refer to `design.md` (DD-n) and `tasks.md`.

## Review 1: design revision 1 (verdict: FAIL for starting implementation as written; the approach was sound)

| ID | Sev | Finding | Disposition |
|---|---|---|---|
| A-01 | High | Missing `UPDATE (consent_*)` on `users` (consent endpoint would fail) | Confirmed by running the endpoint; in the matrix; see N-1 and DD-10 |
| A-02 | High | Rollback with `DROP OWNED BY` before reassigning destroys tables | Confirmed (tables lost in the spike); rollback is `REASSIGN OWNED` first (DD-12); `REASSIGN OWNED BY <administrator>` is rejected by PostgreSQL, so adoption uses `OWNER TO` (DD-7) |
| A-03 | High | Bootstrap in a profile breaks `docker compose up` on a fresh checkout | Confirmed (H13); default-profile one-shots (DD-8) |
| A-04 | High | The API container keeps the superuser password through `backend/.env` (`POSTGRES_*`, `TEST_DATABASE_URL`) | Confirmed (variable names of the real container); env files split (DD-8), task 3.3 |
| A-05 | High | `ALTER DEFAULT PRIVILEGES ... IN SCHEMA ... REVOKE` is a no-op | Confirmed; claim withdrawn, global form for functions (DD-6) |
| A-06 | High | The API-writable source mount is visible to the worker | Recorded residual risk (change 13), `DD-13` R5 |
| A-07 | High | Grants vanish when a table is recreated | Confirmed; `db-migrate` (DD-5), round-trip test (task 5.6) |
| A-08 | Medium | Who grants `USAGE` on the schema: the migrator cannot | Confirmed; bootstrap does it, and revokes `PUBLIC`'s default `USAGE` (DD-6) |
| A-09 | Medium | Cross-database exposure (`postgres`, `template1`, test database) | Confirmed; revoked on every database (DD-6), tested |
| A-10 | Medium | `search_path = public, pg_catalog` lets `public` shadow the catalog | Confirmed; runtime roles `pg_catalog, public`; see B-01 |
| A-11 | Medium | Superuser touching owner-controlled objects is an escalation path | Confirmed (planted trigger ran as the DML role); administrator never touches application objects, `search_path = pg_catalog` (DD-6, R9) |
| A-12 | Medium | `ALTER EXTENSION UPDATE` with foreign objects in `public` | Pre-update check (`db-verify` lists foreign objects); H14 weak |
| A-13 | Medium | Migration `0001` downgrade needs ownership of the extension | Confirmed; `downgrade base` is an administrator operation, spec delta (DD-5) |
| A-14 | Medium | `drop_everything` destroys the role-bound state of the test database | Confirmed; own fixtures (DD-11, task 9.1) |
| A-15 | Medium | `restart` keeps the old environment | Confirmed (H13); `up -d` documented (DD-8) |
| A-16 | Medium | `db-verify` scope vague | Catalog list and checks fixed in the spec |
| A-17 | Medium | Rollout ignores `asistenteia_test` | Test database handled by the fixtures, out of the bootstrap |
| A-18 | Medium | Independent review placed after the real run | Review is group 15, before groups 16 and 17 |
| A-19 | Low | `UPDATE (available_at)` excess for the worker | Removed from the matrix |
| A-20 | Low | Column chosen for the `subjects` update | `description`; advisory-lock alternative is task 2.5 |
| A-21 | Low | Connection limits must come from real pools | Confirmed (capacity error looks like authentication); task 5.1 |
| A-22 | Low | Verifier can reach the server log | Confirmed (log record); residual R8 |
| A-23 | Low | Administrator name | Kept as `asistente` (DD-1) |
| A-24 | Low | Large objects and `pg_sleep` stay open | Residual R7 |

Spike hypotheses H1 to H14 were restated after this review; H7 was misstated (A-05), H8 under-specified (A-16), H13 and H14 added.

## Review 2: design revision 3 and spike evidence (verdict: GO WITH CONDITIONS)

The reviewer re-derived the matrix from the code and found it complete and not excessive (no missing privilege). Findings:

| ID | Sev | Finding | Disposition |
|---|---|---|---|
| B-01 | High | The bootstrap runs in the application database where the migrator controls `public`; a more specific signature or an operator wins over `pg_catalog` | Proved (`s8_extra.py`, `B-01`); `search_path = pg_catalog`, qualified names, role work from `postgres` (DD-6); planting tests (task 5.7) |
| B-02 | High | H13 was marked confirmed without records | Recorded in the clean run (`spike/out/h13_compose.txt`), the real-flow harness `h13/` (task 1) and repeated with the real commands (task 6.4) |
| B-03 | Medium | Revoke-then-grant is not atomic | Proved (2 of 98 reads failed); one transaction (DD-4, task 5.6) |
| B-04 | Medium | Adoption inside the idempotent bootstrap | Separate explicit command (DD-7, task 4.3) |
| B-05 | Medium | Self-password change understated; `ALTER ROLE self SET` untested; hash comparison cannot detect it | Proved; `RESET ALL`, login probe, tests (DD-6, task 5.10), residual R1 |
| B-06 | Medium | Residual-risk list incomplete (chunk poisoning, forged teacher, `LOCK TABLE`) | Proved; residual R2 to R4, DD-9 for the teacher forgery, DD-13 |
| B-07 | Medium | Silent `200` affects only the consent endpoint today | Audit of the other endpoints done by the reviewer; DD-10, group 7 |
| B-08 | Medium | D8 weakens the test guard and conflicts with specs and tests | Guard keeps its `DATABASE_URL` reference (DD-11, task 3.4), spec delta, tasks 11.1 |
| B-09 | Medium | Test layer and CI rules | Spec delta `continuous-integration`, DD-11, group 10 |
| B-10 | Medium | Evidence gaps (H1x, A-22, A-04, truncated coverage record, ungranted-column negatives) | Closed in the clean run (`s8_extra.py` and host-side records) |
| B-11 | Low | One-shots use the image, the API mounts the source | `up --build` required (DD-8) |
| B-12 | Low | Rollback incomplete (compose services, `PUBLIC` state, `DROP ROLE` loop) | DD-12, task 5.9 and 16.2 |
| B-13 | Low | Triggers on owned tables | `db-verify` lists triggers; test asserts none exists in `public` |

The reviewer's conditions 1 to 10 are covered by tasks 1, 2 to 10 and the residual-risk entries of task 18.2; condition 7 (explicit commit in the consent endpoint) was authorised by the owner on 2026-11-12 as a design item with a later functional commit (group 7).

## Review 3 of the OpenSpec artifacts

Recorded in `2026-11-12-planning-review.md` (read-only review of this planning stage).
