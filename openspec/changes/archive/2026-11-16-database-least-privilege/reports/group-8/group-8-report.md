# Group 8: teacher provisioning separated at database level (2026-11-13)

Decision DD-9, option A. Scope: tasks 8.2 to 8.7 only. Migration 0006 was applied only on disposable PostgreSQL 15.19 + pgvector 0.8.7; the development database stays at 0005, no real role, `.env` file or container was changed, and `docker compose up` was not run. The only action on the existing stack was `docker start asistenteia-db-1` after Docker Desktop restarted (the container has restart policy `no`).

## What changed

- Migration `0006`: server default `'student'` on `users.role`; downgrade drops only the default; no row changes.
- Model: `users.role` has the same `server_default`; registration (`AuthService.register_student`) no longer names the role.
- Matrix: the application role keeps `INSERT` on `users` without `role` (it never had `UPDATE` on it); `KNOWN_GAPS` is empty; the inventory derives that registration omits `role` and the CLI inserts it.
- CLI identity: `CliSettings` / `load_cli_settings` read only `CLI_DATABASE_URL` (+ `APP_ENV`, default `production`, fail closed) from `backend/.env.cli`; no JWT secret, no fallback to `DATABASE_URL`. `backend/.env.cli.example` added.
- Compose: `cli` service (profile `cli`, one-shot, `restart: "no"`, no ports or volumes, `.env.cli` optional at the Compose level, waits for `migrate`); no other service receives `.env.cli`.
- Docs: `data-model.md`, `development_guide.md`, TD-040 (the running stack still uses the owner role until groups 16 and 17).

## Evidence

| Item | Result |
|---|---|
| RED | `tdd-red-unit.txt` (24 failures + 1 collection error before the implementation); `run-integration-red-migration.txt` (3 failed, 2 independent of 0006); `run-integration-red-roles.txt` (collection error: no `CliSettings`) |
| GREEN, final code | migration 5 passed; roles suite 371 passed (includes the 8 new teacher tests); legacy integration 862 passed; unit 1131 passed + the 3 known Windows baseline failures |
| Upgrade/downgrade 0006 | default `'student'::user_role`; teacher and student rows identical before and after both directions; round trip returns to head; `alembic check` shows no drift |
| Registration | student stored under the application role; a payload with `"role": "teacher"` gives 201 and student |
| Escalation | under the real application role the ORM insert with role teacher, a raw `INSERT` with role and `UPDATE users SET role` all give 42501; nothing stored |
| CLI | `create-teacher` and `seed` work under the CLI role; output has no password or hash; duplicate changes nothing; the CLI role is refused `UPDATE`/`DELETE` on `users`, every other table and `CREATE` |
| Mutations | `mutation-run.txt` 10 of 10 caught (broad INSERT restored, 0006 no-op / wrong default / downgrade keeps default, model without default, registration names the role, CLI falls back to `DATABASE_URL`, seed gate opens by default, CLI loses INSERT on role, CLI may UPDATE); `mutation-compose-cli.txt` 5 of 5 caught (API or worker receives `.env.cli`, `cli` not profiled, restart, port) |
| Gates | ruff check and format clean; mypy strict 215 files; `openspec validate --all --strict` 18/18; integration collection 1239 |

## Independent review (read-only, clean context): PASS WITH GAPS

| ID | Disposition |
|---|---|
| G8-01 mutation evidence incomplete (the harness lacked the guard database, so migration mutations had an invalid baseline) | fixed: the harness creates it; full rerun 10 of 10 |
| G8-02 seed gate open in Compose (`APP_ENV` never reached the command) | fixed: `CliSettings.app_env` defaults to `production`; guide passes `-e APP_ENV=development`; test and mutation added |
| G8-03 no final-state record | this report and the re-run on the final code |
| G8-04 loose assertions | tightened (201 and student); the head assertion lives in the new migration test |
| G8-05 to G8-10 | confirmed: no API path to teacher, migration correct, CLI secrets handled, Compose and docs accurate, KNOWN_GAPS emptied legitimately |

Residual (accepted): a database connection error inside the CLI shows a traceback with host and user, never the password; `docker compose run --rm cli` re-runs `bootstrap` and `migrate` (one-shots); the legacy `exec backend ... app.cli` form no longer works until the roles flow reaches this machine (TD-040).
