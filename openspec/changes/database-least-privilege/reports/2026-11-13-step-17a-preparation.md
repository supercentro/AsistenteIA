# Group 17, phase 17A: preparation of the real run (2026-11-13)

Branch `feature/database-least-privilege`, code at `a953b6f` (group 16 reports on top) (no functional code, test, spec, skill or agent changed; this phase adds documents, tools and evidence). Authorised scope: the preparation only. **Nothing was executed on the development database, its worker, its volume, its images or its real `.env` files**: no backup of the real database was taken, no bootstrap, adoption, migration, grant, role change or rotation was run, no service was stopped, started or recreated, `docker compose up` was never run on the real project, nothing was pushed, and no value of a real `.env` file was read or printed. The only contacts with the real stack are read-only: container metadata (`docker inspect`) and the read-only snapshots of `group-12/db_snapshot.sh`, identical before and after (`snapshot-dev-*.txt`). GitHub Actions has not run the workflow.

## Documents and tools (in `reports/group-17a/`)

| File | Purpose |
|---|---|
| `runbook-17b.md` | the step-by-step plan of 17B with the commands, expected results, stop conditions, rollback table and the measured timings |
| `backup-and-recovery.md` | backup, hashes, restore into a disposable cluster, comparison, recovery of last resort |
| `credentials-and-services-map.md` | identities, files, services, the safe order and the rotation of the exposed administrator password (TD-038 and the incident) |
| `ci-first-run.md` | the exact procedure to run the `privileges` job on GitHub for the first time, dependencies, risks, expected results, acceptance, action on failure |
| `checklist-go-nogo.md` | the verifiable checklist for 17B (gates A to M) |
| `tools/` | `snapshot_db.sql`, `snapshot_cluster.sql`, `compare_snapshots.sh` (refuses empty or error files), `preflight_readonly.sh`, `prepare_env_files.py` (with `--dry-run` and `--rollback`; self-test `test_prepare_env_files.py`, 64 checks), `check_env_names.py`, `restore_public_cluster.sql`, `restore_public_schema.sql`, `compose.rollback.override.yml` |
| `expected/` and `run_17a_baseline.sh` | the expected snapshots of the development database at 0005 (120 + 10 + 11 lines), generated from the verified backup brought to 0005 in a cluster built like the development one; gate D of the checklist compares the real catalog with them |
| `run_17a_replica.sh`, `run_17a_stages.sh` and their outputs | the reproducible rehearsals (below) |

## What was proved, and how

**The replica** (`run_17a_replica.sh`, 86 of 86 checks): a disposable Compose project `g17arep` built from the real `docker-compose.yml` of this branch (new) and of `main` (old), with its own network and volume, no published database port, the API on `127.0.0.1` at a temporary port, synthetic credentials, and the **same image ids** as the development stack (`asistenteia-backend:latest` and `asistenteia-worker:latest` are identical to the `main-f455234` images used as "old"). It restores the backup (revision 0004), reaches 0005 as the original administrator, starts the old stack as the administrator everywhere (as the development stack runs today) and then performs 17B with the real mechanics: the read-only preflight tool, the backup procedure with a restore into another disposable cluster that compared `IDENTICAL`, the env-file tool (it printed no value, refused a second run, changed only user and password of `DATABASE_URL`), the real compose one-shots `bootstrap` (exit 1 with the drift) and `migrate`, the adoption (dry run and applied), `db-verify`, the recreation of `backend` and `worker` with `--no-deps` (both on their restricted roles, proved by the sessions; the new API refuses the administrator URL), the functional checks with synthetic data (including a teacher created by the CLI role and an upload processed by the worker role), the rotation of the administrator password (the old password refused over TCP, the new one accepted, the services reconnected, the bootstrap idempotent), the **full rollback** from the end state with data written under the roles (downgrade, ownership and roles removed, `PUBLIC` restored, the old files rebuilt with the rotated password, the old stack started from the old images; the previous API and worker answered, logged in, registered and processed an upload on the rolled-back database; the data survived), the cleanup of the synthetic rows, and the recovery of last resort (drop, restore from the verified dump: `IDENTICAL`).

**Rollback from each stage** (`run_17a_stages.sh`, 20 of 20): after the bootstrap, after the adoption, after the migration and grants, each time on a database restored from the backup: ownership, grants, defaults, constraints, rows, roles, memberships, settings and database owners are identical to the state before, with one tolerated difference.

**Differences after the rollback** (`g17a-diff-*.txt`, measured, not assumed): only the representation of default ACLs (the `NULL` ACL of the 7 tables and 5 databases becomes the equivalent explicit one, the two templates are reordered); schema `public`, roles, memberships, settings, owners and rows are identical. With `NORMALIZE=1` the comparison is `IDENTICAL`; the recovery from the dump is exact, `NULL` ACLs included.

Timings and the list of what cannot be reverted automatically are in the runbook. In short: forward procedure about 14 s of commands plus about 125 s until the worker is healthy; full rollback 134 s (about 9 s of commands plus the same worker start); rollback from earlier stages 2 to 5 s of commands; rotation 8 s; recovery from a dump 1 s on an empty database.

## Findings of the preparation (new, not defects of the code)

1. **`docker compose up` re-runs `bootstrap` and `migrate` every time, and the first `bootstrap` exits 1 on the ownership drift**, which would stop `migrate`, `backend` and `worker` from starting. 17B runs the first bootstrap by hand and recreates the two services with `--no-deps`.
2. **The old compose file bind-mounts `backend/app`**, which is now the new code and refuses a superuser connection: a rollback must start the old stack from the old images (tag them `pre-17b` first) with `tools/compose.rollback.override.yml`, not just restore the files.
3. **The files `*.pre-17b` hold the exposed administrator password**; `--rollback` rebuilds the old files with the administrator password of the current `.env.db`, so a rollback after the rotation does not reintroduce it; the copies must be destroyed after the acceptance.
4. **The worker's `start_period` (120 s) dominates the downtime** of the switch and of the rollback.
5. **`PUBLIC` closing is not undone by `db-adopt --rollback`** (cluster-wide, templates included, and the revoke on schema `public`): `restore_public_*.sql` do it and were rehearsed.
6. **`asistenteia_test` is closed to `PUBLIC` by the bootstrap too** and restored by the script; the host tests use the administrator, unaffected. It must not be bootstrapped itself (`db-verify` would report the CONNECT of the roles to it).
7. Not rehearsed, stated in the runbook: restoring a dump with the roles still present; a dump taken after the adoption restored into a cluster without roles; a real failure injected in the middle of the multi-statement role removal.

Documentation updated: `docs/technical-debt.md` (TD-044), `docs/development_guide.md` (pointer to this plan), `tasks.md` (heading of group 17; tasks 17.1 to 17.3 stay unchecked).

## Residual risks and conditions for 17B

See the checklist, gates A to M, and its eight residual risks. The principal ones: the rehearsal used a reconstructed 0005 copy of an empty database (the real catalog must be compared before 17B, gate D); the worker start period; the exposed credential until the rotation; GitHub Actions has not run the workflow.

## Quality gates

`ruff check --no-cache` and `mypy --strict` clean (233 files, no Python changed in the application); `openspec validate --all --strict` 18 of 18; the rehearsals above; the development database and worker before and after identical (read-only snapshots, 31 deterministic lines, revision 0005, no drift, no new role, 0 rows; both containers healthy).

## Superseded runs kept

`g17a-replica-output-run1-superseded.txt` (the env tool received an MSYS path and a snapshot query failed on a `"char"` concatenation: both script errors, fixed in the tools) and `g17a-replica-output-run2-superseded.txt` (73 of 74: one check counted the session of the check itself as an extra administrator session); `g17a-stages-output-run1-superseded.txt` (database names with a hyphen). The recorded runs are the final ones.

## Independent review of this preparation (read-only): PASS WITH GAPS, 0 critical, 2 high, then fixed

The reviewer (clean context) recommended NO-GO until two high and several medium findings were fixed. All were handled; the reruns are the ones recorded (replica 86 of 86, stages 20 of 20).

| ID | Finding | Handling |
|---|---|---|
| H1 | gate D could not be executed (S0 was not stored; the replica baseline had a row) | **Fixed**: `expected/` generated by `run_17a_baseline.sh`; the compare command is written in the runbook and the checklist; the tool refuses empty or error files (exit 2, minimum lines) and the replica proves it |
| H2 | the shipped rollback override was never exercised and the runbook omitted it | **Fixed**: the runbook step 6 uses it; the replica now rolls back with main's compose file + the shipped `compose.rollback.override.yml` (+ isolation), after the read-only `docker compose config` check (two `pre-17b` images, no `backend/app`); the services ran the `pre-17b` images without bind mounts and answered |
| M1 | no `MSYS_NO_PATHCONV` note | **Fixed** in the runbook (shell section) |
| M2 | image builds untested, unordered, not timed; `<new>` image name | **Fixed/measured**: all five images are built in 17B.1 while the stack is up; the branch's real `worker` target built in 859 s (14 min, 3.2 GB, `g17a-worker-build.txt`); `db-verify` uses the compose-built `asistenteia-migrate` image |
| M3 | replica versus real env files unverified | **Mitigated**: `check_env_names.py` (names only) and a settings-load requirement in 17B.1; not run on the real files in 17A |
| M4 | "same image ids" without stored evidence | **Fixed**: the replica checks that the `pre-17b` tags and the development `latest` tags have the ids of the `main-f455234` images; the runbook tags from the ids the containers use |
| M5 | the running backend/worker may already run new code | **Added** to gate F: state, restart count, start time and the last log lines of both, with the note that the mounted `backend/app` is the branch |
| M6 | no rollback row for the early stage | **Added** (files prepared, services stopped) |
| M7 | the backup is taken while the services still write | **Fixed**: a second snapshot after the stop must be `IDENTICAL` (rehearsed) |
| M8 | no exact rotation command or half-done rule | **Fixed** in `credentials-and-services-map.md` |
| M9 | checklist gaps (disk, frontend, other clients, host tests, window, reference for the tools) | **Added** (disk, client addresses, login roles, window, commit id of the tools) |
| M10 | `prepare_env_files.py` edge cases | **Fixed and tested**: CRLF preserved, BOM tolerated, percent-encoded special characters, comments and query kept, a single DATABASE_URL required, undo on failure, no silent replacement of `.rolled-back` or `.pre-17b`; 64 self-test checks |
| M11 | CI doc inaccuracies and no scan of what a push publishes | **Fixed**: 61 commits, untracked documents, `MIN_*` note, and a secret scan step (14 matches by shape, fixtures; the owner must confirm) |
| L2, L3 | plain `up` fails after a rollback; logs lost | **Added** to the list of what is not restored |

What this phase still cannot prove: the behaviour on the real data and the real env files (the replica used reconstructed 0005 and synthetic files with the same image ids); the settings load with the real files; the first GitHub run.
