# Group 16: rehearsal on a restored copy of the real backup (2026-11-13)

Branch `feature/database-least-privilege`, code at `a953b6f` (no functional code, test, spec, skill or agent was changed; this group only adds reports and evidence). Authorised scope: tasks 16.1 to 16.3. The development database `asistenteia`, its worker, its volumes, the real `.env` files, roles and passwords were **not** touched: no value of a real `.env` file was read or printed; the rehearsal script opened **no** connection to the development cluster (it only reads container metadata with `docker inspect`), but the two read-only snapshots of the development state (`group-12/db_snapshot.sh`, `docker exec` in the existing containers, the practice of groups 12 and 13) did query `asistenteia` and `asistenteia_test` read-only before and after, and they are identical; `docker compose up` was never run; no existing container was stopped, rebuilt or restarted; nothing was pushed. GitHub Actions has not run the workflow, so nothing here is remote validation. Evidence: `group-16/g16-output.txt` (the full log, secrets masked), `run_g16.sh` (reproducible), `tests-*.txt`, `snapshot-dev-*.txt`.

## 16.1 The backup and the restoration

| Item | Result |
|---|---|
| Backup used | `asistenteia_pre_0005_20261112T034241Z.dump`, the only backup of the development database with a manifest and a second copy that exists (an older `asistenteia_pre_0004.dump` of revision 0003 also exists and was not used; `%USERPROFILE%\\Backups\\AsistenteIA\\`, with a second copy in the owner's cloud storage); `pg_dump -Fc` of PostgreSQL 15.19, pgvector 0.8.7, taken on 2026-11-12 under the owner's authorisation |
| Integrity | SHA-256 `e6f5bb75…acaba8c6` equal in the dump, in its `.sha256` file, in the manifest and in the second copy; 14 576 bytes; `pg_restore --list` readable: 51 lines, of which 36 are real entries (the manifest's "51 toc entries" counts the header comment lines; the first run of the script counted 36 and failed, the check was corrected to count lines) |
| The original is never written | it was only read; a working copy outside the repository with the same hash was restored; hash, size and modification time of the original are equal after the run |
| **Deviation (important)** | this dump is the state **before** migration 0005 (revision `0004`), not of the current database (0005, still empty). The rehearsal therefore restored it and applied `0005` **as the original administrator** inside the copy, exactly how the real database got there on 2026-11-12, to reach the state that group 17 will find. It is a reconstruction (same migration, same owner, empty tables), **not verified against the catalog of the real 0005 database** and not a dump of it; before task 17.2 the same catalog fingerprint (columns, types, NOT NULL and index definitions) must be computed read-only on the real database and compared with the one of the copy, and task 17.1 requires a fresh verified backup of the real database |
| Disposable cluster | one container `g16pg<pid>`, PostgreSQL 15.19 + pgvector 0.8.7, own network `g16net<pid>` (the only network it belongs to), data on tmpfs (0 mounts, no volume), **no published port**, throwaway administrator `asistente` with a random password; none of the networks or volumes of the development stack is shared (checked by `docker inspect`); only the original administrator exists as a role |
| Restoration | `createdb` + `pg_restore --exit-on-error` into two databases (the main copy and a second copy): revision `0004`, six tables and two enum types owned by the original administrator, vector 0.8.7, catalog fingerprint `bcf7be12…8cc1d7e`, no error |
| Recovery from the backup (end of the run) | the main copy was dropped and restored again from the same verified dump: same revision, same catalog fingerprint as the first restoration, owners equal to the original administrator |

## 16.2 Rehearsal (final run: 209 of 209 checks passed, 0 failed)

Initial state of the copy, before the bootstrap: revision 0005, the original administrator is the owner of every table and type, `users.role` has no default, no role but the administrator exists, `PUBLIC` is not yet closed on the databases (`asistenteia`, `asistenteia_copy2` and `postgres` with the default ACL). The main copy is empty like the development database; the second copy holds synthetic rows (a teacher, a student, a subject, an enrollment, a document, a chunk, a job and 200 000 students) so that data preservation is shown with data.

| Step | Result |
|---|---|
| `db-bootstrap` | creates the four roles with SCRAM verifiers, closes `PUBLIC`, and reports the ownership drift of the old tables with **exit 1** (reported, not repaired); revision, ownership, rows and catalog unchanged |
| Failure before the adoption | `db-verify` finds the privilege differences (exit 1); `db-migrate` before the adoption **fails safe**: the migrator does not own the tables (`SQLSTATE 42501`), nothing changed, `users.role` still without default |
| Wrong identity | `db-migrate`, `db-migrate --downgrade` and `db-verify` with the administrator URL, and `db-migrate` with the application role URL, are refused before any statement; nothing changed (PG-02) |
| Wrong or system database | `postgres`, `template0`, `template1` and `POSTGRES` are refused by `db-bootstrap`, `db-adopt` and `db-adopt --rollback --apply`; a database that does not exist fails for adopt and is refused for the rollback; nothing changed in the cluster or in the roles (PG-07) |
| `db-adopt` dry run | exit 0, lists the plan, changes nothing |
| A session holds the database | the adoption is refused naming the session; nothing changed |
| **Partial failure** | a prepared transaction (no session) holds a lock on one table, so the adoption alters other objects and then times out: `could not get a lock within lock_timeout; nothing was changed` after 6.3 s; **owners, types, revision, rows and catalog are exactly as before** (atomic); the lock was released afterwards |
| `db-adopt --apply` | exit 0: every table and the enum types belong to the migrator; revision, rows and catalog unchanged |
| Migration 0006 | `db-migrate` (Alembic as the migrator, then the grants) exit 0; revision 0006; `users.role` DEFAULT `'student'::user_role`; `db-grants` again exit 0 (idempotent) |
| `db-verify` | **no findings** after the migration and after the functional run |
| Effective privileges | the working roles are not superuser and cannot create roles, databases, replication or bypass RLS (checked on the catalog); the API role cannot insert a teacher, update `users.role` or create objects; the worker cannot read `users`; the CLI cannot read `documents`; plus the 9 refusals of the isolation block. The per-column recomputation of the matrix is the one inside `db-verify` |
| Functional validation with synthetic data | API as `asistente_app` and worker as `asistente_worker` (disposable containers on the rehearsal network, the API published only on `127.0.0.1` at a temporary port), teachers created by the CLI: the **same 101 curl checks of group 13** passed on the adopted copy (registration, login, consent, subjects, enrollments, TXT, Markdown and PDF uploads processed by the worker, deletions and cascades, role denials, persistence); the 45 + 17 checks of 2026-11-12 are not stored as a script in the repository, so the group 13 scenario is what was rerun |
| Coverage of the "state" comparisons | the `state()` used by the "nothing changed" and "equals its state before the bootstrap" checks covers revision, table owners, enum type owners, row counts and a fingerprint of columns, types, NOT NULL and index definitions, plus the `users.role` default separately; it does **not** cover table, column or schema ACLs, default ACLs, constraints other than indexes, sequences or extension ownership, so those checks do not prove that privileges were restored after `DROP OWNED` and `DROP ROLE` |
| Data preservation | the second copy, with 200 002 users and the rest, kept every row through adoption, migration and grants (counts equal) |
| Re-execution | `db-bootstrap` again (exit 0, no drift any more), `db-adopt` and `db-adopt --apply` again (nothing to do), `db-migrate` again, `db-grants` again, `db-verify` again: all consistent |

## 16.2 Rollback and recovery

| Test | Result |
|---|---|
| Rollback dry run | exit 0, names the database, changes nothing |
| `--remove-roles` while the second database is still adopted | refused **before any change**, naming the other database (the fix of the second review, R7) |
| Rollback of one database | reassigns ownership **only in the named database**; the report names the other database still owned by the migrator; the main copy gets its original owner back with rows and catalog intact; the second copy stays owned by the migrator |
| Rollback run twice | the second run is a no-op (exit 0) |
| Re-adoption after a rollback | works; owned by the migrator again |
| The whole way back | `db-migrate --downgrade 0005` for both, rollback of the first, rollback of the second **with `--remove-roles`** (exit 0): the cluster has only the original administrator again; the main copy equals its state before the bootstrap (revision 0005, owners, types, catalog, no `users.role` default) and keeps the four accounts of the functional run; the second copy equals its state before the bootstrap including its 200 002 users |
| Recovery from the backup | see 16.1: restored again, same fingerprint. **Limits:** it ran after the roles were removed; the dump has no rows, so row restoration was not exercised; a restore with the roles present (a fresh `createdb` has the default `PUBLIC` access, so the closing would have to be applied again with `db-bootstrap`) and a dump taken after the adoption (owner `asistente_migrator`) restored into a cluster without the roles were not rehearsed; no failure was injected in the multi-statement role removal (`_drop_roles`), the "stops half way" part of TD-044 |

## Findings of the rehearsal (PG-08, TD-044 and new)

None of these is a failure of the rehearsal; they are the behaviours that group 17 must know. The adoption procedure was not changed.

1. **PG-08, scale of the adoption lock.** Adopting the second copy with 200 002 users took 1.8 s including the container start; the row counts inside the exclusive-lock transaction are not a problem at this size, only at much larger ones.
2. **PG-05, grants after Alembic (confirmed).** Columns added outside `db-migrate` (here by the migrator with `ALTER TABLE`) were readable by the application role on four tables and by the CLI role on `users` until `db-grants` ran; `db-verify` detected them (exit 1) and `db-grants` healed them. The rule "always `db-migrate`, never `alembic upgrade` alone" is what protects this.
3. **PG-08, a database with a quote in its name** makes `db-bootstrap` abort (exit 1) and it changed nothing (state, roles and database ACLs equal).
4. **PG-08, the closing of `PUBLIC` is not undone by the rollback.** After the whole way back the original administrator is the only holder of `CONNECT`/`TEMP` on every database of the cluster, including the templates, and the bootstrap's `REVOKE ALL ON SCHEMA public FROM PUBLIC` is not undone either (not shown by the run, read from `bootstrap.py`). Harmless on this cluster (only the administrator exists) but permanent for any other role that relied on `PUBLIC`.
5. **New: `db-verify` assumes one application database per cluster.** After a second database is bootstrapped, `db-verify` of each database reports that the four roles can connect to the other one (the only findings, 4 per database). In the real cluster only `asistenteia` is bootstrapped (`asistenteia_test` is closed and gets no `CONNECT`), so group 17 is not affected, but nobody should bootstrap a second application database in the same cluster without expecting that output.
6. **The backup is of revision 0004**, see 16.1.
7. **Bootstrap before the adoption exits 1** by design (it reports the drift); a script that treats that exit code as a failure must be written with that in mind.

Proposed documentation updates (not made, they need your authorisation because this task allows reports and tasks only): add findings 4 and 5 to TD-044 and the dangerous-operations checklist of the development guide, and state in the group 17 procedure that the backup of task 17.1 must be a fresh dump of the real 0005 database.

## Quality gates

| Gate | Result |
|---|---|
| `ruff check --no-cache`, `ruff format --check`, `mypy --strict` (233 files) | clean (run on the unchanged code; their output is not stored in `group-16`) |
| Specific tests on a disposable PostgreSQL **15.19** (`group-16/tests-role-bound.txt`): adoption, bootstrap, grants, identity, verify, lifecycle, startup | **115 passed** (a first run used PostgreSQL 16.16 by a mistake of the copied script, which was caught by the review; both runs passed, the one recorded is the rerun on 15.19) |
| Migrations 0001 to 0006, unit tests of the guards, of the superuser refusal and of the commands (`tests-migrations.txt`) | **81 passed** |
| `openspec validate --all --strict` | 18 of 18 |
| Development database and worker, before and after (read-only snapshots) | deterministic part identical (31 lines); revision 0005, no drift, no new role, 0 rows; both containers healthy |

## Incidents and deviations of this group

- **First run of the script (kept as `g16-output-run1-superseded.txt`): 199 of 208 passed.** The 9 failures were mine, not the procedure's: a wrong count of the table of contents (the manifest counts all lines), the bootstrap of the second database made `db-verify` of the main one report the finding 5 above (the order of my script, now corrected so that the main database is verified before the second one is bootstrapped, and the cross-database finding is checked explicitly), and a comparison of the final state that forgot the accounts of the functional run. The script was corrected and the final run is the one recorded; nothing in the code was touched.
- The backup is of revision 0004 (see 16.1).
- The privilege probes of the run use `docker exec psql -U <role>` over the unix socket of the container (trust), so they test privileges, not authentication; authentication is exercised by the API, the worker and the CLI, which connect over TCP with their passwords. The SCRAM verifiers are shown by the bootstrap code and its tests, not by this run's output. The isolation checks compare against the networks and volumes of `asistenteia-db-1` read with `docker inspect` (the output does not print them; the proof that the cluster has no mount is `mounts: 0`).
- This is not a validation of GitHub Actions and not a rehearsal on the real database: the data of the main copy is empty (like the real one) and the data-preservation evidence comes from the second copy.

## Cleanup

Identity checked before removal: container `g16pg<pid>` and network `g16net<pid>`, both with the label `purpose=g16-rehearsal` and none outside the `g16` scheme. Removed: the container, the network, the two temporary image tags (`asistenteia-backend:g16-branch`, `asistenteia-worker:g16-branch`) and the credential files (generated per run outside the repository). Containers, networks and volumes left: 0. The other containers of the machine (the real stack and other projects) are identical before and after; the original backup is untouched (same hash, size and time).

## Conditions for group 17 (from the report and the independent review: PASS WITH GAPS, no critical or high finding)

1. A **fresh dump of the real 0005 database** (task 17.1), hash verified, restored and read back before any change, and the catalog fingerprint of the real database compared with that of the reconstructed copy.
2. Stop the API, the worker and the CLI. The adoption guard sees sessions, not prepared transactions (not a risk here).
3. Run `db-bootstrap` for `asistenteia` only and treat its **exit 1 as "drift reported"**; then the adoption dry run, `db-adopt --apply`, `db-migrate`, `db-verify`. Never `alembic upgrade` alone. Do not bootstrap `asistenteia_test` or any second application database in that cluster (it would make `db-verify` report the CONNECT of the roles to it).
4. Do not use `--remove-roles` on the real cluster. Keep a manual re-grant recipe (`CONNECT`/`TEMP` on the databases and `USAGE`/`CREATE` on schema `public` for `PUBLIC`) in case the old access is needed again, because the rollback does not restore it.
5. Documentation to update with the owner's authorisation (this group may not edit `docs/`): TD-044 and the dangerous-operations checklist with findings 4 and 5 and the recovery limits above.
