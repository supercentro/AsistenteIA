# Step 17B.5: functional validation on the development database (2026-11-14), closed by the owner

Sanitized evidence. Run id `g17b55ee3f62`; emails were `@example.com` synthetic accounts; no password, token or hash was stored or printed. Head commit `c789ed0`, window 18:30-20:00 America/Argentina/Cordoba, development only.

## Result

Accepted by the owner: 25 of 25 functional checks, 3 synthetic users removed, final counts equal to the initial ones, PostgreSQL healthy at revision 0006, backend and worker operating with the restricted roles, `db-verify` with no findings.

## Checks (HTTP statuses)

| Area | Case | Status |
|---|---|---|
| Users | register student A / B | 201 / 201 (role `student`) |
| Users | duplicate registration | 409 |
| Users | teacher created by the CLI role (`--password-stdin`) | exit 0; `/users/me` shows role `teacher` |
| Authentication | login of the three users / wrong password / no token | 200 / 401 / 401 |
| Subjects | teacher creates a subject | 201 |
| Subjects | student creates a subject / anonymous creates a subject | 403 / 401 |
| Subjects | non-enrolled student A and B read it | 404 / 404 |
| Enrollments | teacher enrolls A; again; unknown email; a student enrolls someone | 201; 409; 404; 403 |
| Enrollments | enrolled A reads the subject; A lists subjects / B lists subjects | 200; 1 / 0 visible |
| Documents | student uploads / teacher uploads a small TXT | 403 / 202 |
| Worker | the TXT reached `ready` | after 3 s, 2 chunks, no `error_code`, job payload bytes cleared (0) |

Denied at database level (each in a rolled-back transaction as the restricted role): `asistente_app` inserting a teacher into `users`, `asistente_worker` reading `users`, `asistente_cli` deleting `subjects`, `asistente_app` reading `alembic_version` and creating a table: all `permission denied`.

Identities: during the run `pg_stat_activity` showed one session of `asistente_app` (backend) and one of `asistente_worker` (worker), none of the administrator; backend and worker had 0 restarts, 0 authentication or permission errors, 0 tracebacks, 0 token-like strings in their logs.

## Removal of the synthetic data

| Data | Mechanism | Result |
|---|---|---|
| subject (with its document, chunks, job, enrollment by cascade) | `DELETE ... WHERE id = <exact id> AND name LIKE 'g17b...'` as `asistente_app` (the permission `DELETE /subjects` uses) | counts 3/0/0/0/0/0 |
| 3 users | an exceptional authorisation by the owner: one transaction as `asistente_migrator` (not the superuser), dry run first, the three exact ids plus email, name and domain conditions, parameters, `DELETE` must affect exactly 3 rows or `ROLLBACK` | 3 rows, `COMMIT`, counts 0/0/0/0/0/0 |

Why the migrator: no application role holds `DELETE` on `users` (see TD-039 below). The catalog snapshot after the removal is IDENTICAL to the one before 17B.5 (119 lines).

## TD-039 and `DELETE /users/me`

`DELETE /users/me`, `DELETE /users/me/conversations`, `DELETE /conversations/{id}` and `POST /chat` are in `docs/api-spec.yml` and **do not exist in code** (TD-039 item d). The privilege matrix gives `asistente_app` no `DELETE` on `users`, which is what 17B.5 met. TD-039 stays **open**; its closure belongs to change 11 (`personal-data-erasure`), which will need (a) the endpoint with the explicit commit helper and a forced-refused-commit test and (b) a reviewed `DELETE` grant on `users` for the application role in the matrix (and `db-verify`). Nothing was changed in the matrix or in the contract.

## Incident raised during this step

SEC-17B-01 (see `2026-11-14-sec-17b-01-migrator-password-exposure.md`): the migrator password appeared in a traceback of a one-off script. No data was affected; the rotation is prepared but not authorised.

## Final state at close

Revision 0006; counts 0/0/0/0/0/0; nine objects owned by `asistente_migrator`; PUBLIC without grants; both dumps with the registered SHA-256; the three `*.pre-17b` copies byte-identical; orchestrator state intact (S10-S13, S20-S26, S30, S31 done, none failed); Git tree unchanged (HEAD `c789ed0`).
