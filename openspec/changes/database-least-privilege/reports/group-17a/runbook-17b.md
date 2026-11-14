# Runbook 17B: real run on the development database (PLAN; nothing here was executed on the real stack)

Prepared in group 17A. Every command below was rehearsed on a disposable replica of the development stack (`run_17a_replica.sh`) or on a disposable cluster (`run_17a_stages.sh`); the evidence is in `g17a-replica-output.txt` and `g17a-stages-output.txt`. Placeholders: `<REPO>` is the checkout, `<BACKUPS>` the backups folder outside the repository, `<TMP>` a folder outside the repository for evidence. **The real checkout path contains a SPACE (`New folder`): every `<REPO>`, `$S`, `$O`, `<TMP>`, `<BACKUPS>` below must be written inside double quotes (`"<REPO>/backend"`, `"$S/tools/..."`, `-f "$O"`), or the shell splits the path.** Commands are for a POSIX shell (Git Bash); `docker compose` is run from `<REPO>` with the real project name `asistenteia`.

**Shell.** Git Bash on Windows rewrites arguments that look like paths: start the session with `export MSYS_NO_PATHCONV=1`, otherwise `/tmp/...` arguments of `docker exec` and `docker cp` are mangled. Use the Windows form (`C:/...`) for paths handed to `docker cp`, `docker run -v` and `python` from Git Bash.

**Authorisation.** 17B starts only after the owner authorises it in a new message, and each phase that writes needs the explicit "GO" of the checklist (`checklist-go-nogo.md`). Task 3.3b (the creation of the role files and the edit of the two `DATABASE_URL` values) is part of that authorisation.

## 0. What is going to change, and what is not

Changes: roles `asistente_migrator`, `asistente_app`, `asistente_worker`, `asistente_cli` (new); ownership of `alembic_version`, the six tables and the two enum types (administrator → migrator); the grants; `users.role` default (revision 0006); `PUBLIC` loses `CONNECT`/`TEMP` on every database of the cluster, `USAGE` on schema `public` of `asistenteia`; three new environment files and two edited lines; the API and the worker run new images and connect with restricted roles. Not changed: data (all tables are empty today), `asistenteia_test`'s content, the volume, the administrator role (until step 17B.6).

Known consequences: the API and the worker are **down** from step 17B.2 until step 17B.5 (measured on the replica: about 5 s of commands plus about 125 s until the worker is healthy because of its `start_period`); a restart of the old stack with the old images keeps working only if rolled back first; the new code **refuses** a superuser connection.

## Orchestrator (`group-17b/run_17b.sh`): the way to run the stages

The stages below are also implemented as an orchestrator that runs **one stage at a time**, fails closed and keeps a state file without secrets (`G17B_STATE_DIR`, a folder outside the repository). Read its header for the exit codes. Rules it enforces: `set -Eeuo pipefail`; a lock directory refuses a concurrent run (exit 5); a stage already done is refused (exit 6); a stage whose predecessor is not done is refused (exit 6); the cluster identity (compose project, container, database, PostgreSQL 15, `system_identifier`) is checked before every stage and must not change between stages (exit 3); free RAM and disk are gated (exit 4); the log is sanitized (no path, user name or URL); on any failure it stops at once, records the failed stage, prints the rollback column that applies and **never** runs a destructive command by itself; Ctrl+C or TERM records the interruption (exit 40) and, for a stage that writes, marks its outcome as UNKNOWN. A stage that writes and failed, was interrupted or was killed is **not** rerun silently: exit 8 until the owner has looked at `--status` and the database and sets `G17B_CONFIRM_RERUN=<stage>` for that one run. The state file carries a hash chain (an edited `done` list is refused, exit 6), the cluster identity is pinned (`system_identifier` of the development cluster is a constant in the script; S10 pins it in the state and every later stage must match), and the test profile can never name an object of the real stack. Known limits (accepted, from the independent reviews): the state chain and the pinned identity are accident guards, not a defence against someone who edits the state file knowing the algorithm (it covers `done` and `cluster_id`, not `failed`/`uncertain`); `G17B_OWNER_GO` is an environment variable, so it must be set for ONE command line and never exported in the shell; killing the docker client does not stop a container already started in the daemon (the stage is then marked UNKNOWN); the test profile and its hooks are refused in the real profile and cannot keep the real env folder, backups or compose file. The settings load (S13) reads the real env files and needs the extra argument `--allow-real-settings` on that command line. The stages from S20 on write and, in the real profile, refuse to run (exit 7) unless the owner has authorised `GO 17B.2` in a new message (the operator then sets `G17B_OWNER_GO=GO-17B.2` for that run only).

| Stage | What | Writes? |
|---|---|---|
| S10 `preflight` | identity, RAM, disk, catalog = expected 0005 baseline (gate D), cluster = expected, activity (gate E), services seen | no |
| S11 `backup_validate` | per-copy manifests, hashes, file and folder ACL, both copies equal, and the **backup equals the real state** (fresh read-only snapshot vs the one taken when the backup was made) | no |
| S12 `images` | tag the images the containers use as `pre-17b`, `docker compose build bootstrap migrate cli backend worker`, check no container changed | no container, volume or network |
| S13 `settings_load` | proves that what Compose resolves for backend and worker equals what the helper parses (`compare`, names and booleans only), then loads the API and worker settings of the CURRENT files in the new images, in throw-away containers without network that receive the environment on stdin (`docker run --env-file` is NOT used: it keeps an inline comment such as `APP_ENV=development # note` inside the value, Compose strips it). The post-transformation files are simulated by `group-17b/run_s13_validation.sh` | reads the real env files in memory: needs the argument `--allow-real-settings` (owner's decision); writes nothing |
| S20 `stop_services` | `docker compose stop backend worker`; the snapshot must stay identical | yes |
| S21 `prepare_env` | `prepare_env_files.py --dry-run --strip-legacy`, then for real; then the four new files get the owner-only descriptor (`secure_file_acl.ps1 -Rights Modify`: readable by Docker Desktop, still editable for the rotation) | yes |
| S22 `bootstrap` | first bootstrap; exit 1 is EXPECTED and it must list the ownership drift | yes |
| S23 `adopt_dry_run` | exactly 9 objects | no change |
| S24 `adopt_apply` | `db-adopt --apply` | yes |
| S25 `migrate` | Alembic 0005 → 0006 and the grants | yes |
| S26 `db_verify` | "no findings" | no |
| S30 `switch_services` | recreate backend and worker, wait until the worker is healthy | yes |
| S31 `verify_sessions` | only the restricted roles hold sessions | no |

`run_17b.sh --plan` lists them, `--status` prints the state, the rollback that applies and a read-only look at the database (revision, whether the four roles exist) and at the env files (names only). Tested only against a disposable stack (`group-17b/test_run_17b.sh`).

## 17B.1 Preflight (read only), backup validation and images

Run `S10`, `S11`, `S12` with the orchestrator (they are the only stages authorised before the owner's GO). By hand, the equivalent of S10 is:

```bash
export MSYS_NO_PATHCONV=1
cd <REPO>
bash "<REPO>/openspec/changes/database-least-privilege/reports/group-17a/tools/preflight_readonly.sh" asistenteia-db-1 asistenteia "<TMP>/preflight-before"
S="<REPO>/openspec/changes/database-least-privilege/reports/group-17a"
bash "$S"/tools/compare_snapshots.sh $S/expected/snapshot-db-0005.txt <TMP>/preflight-before/snapshot-db.txt                       # IDENTICAL (about 120 lines)
MIN_LINES=5 bash "$S"/tools/compare_snapshots.sh $S/expected/snapshot-cluster.txt <TMP>/preflight-before/snapshot-cluster.txt    # IDENTICAL
docker ps -a --format '{{.Names}} {{.Image}} {{.Status}}'
docker logs --tail 5 asistenteia-worker-1 2>&1 | grep -ciE 'superuser|refus'          # 0 expected
python "$S/tools/check_env_names.py" "<REPO>/backend"                                  # names only
```

**Backup: reuse, do not take a new one unless a control fails.** The 17b backup of 2026-11-14 (dump `asistenteia_pre_17b_20261114T013150Z.dump`, revision 0005, SHA-256 `d0a2ad6bfc0c392d765473acbaf7bfbec25ff24eea99e2828e3377176d6279d9`, 17 437 bytes) exists in two folders, each with its own `.sha256` and `<dump>.integrity.txt` (TD-049). It may be reused for 17B only if **all** of this holds (S11 checks it):

1. each copy: SHA-256 and size equal the recorded ones; `backup_manifest.py verify <folder> <dump> --copy primary|second --manifest-suffix .integrity.txt` is OK; `sha256sum -c <dump>.sha256` is OK inside the folder; the two copies equal each other;
2. the folder policy holds on both folders (`secure_folder_acl.ps1 -VerifyOnly`) and every file has the owner-only Read descriptor (`secure_file_acl.ps1 -VerifyOnly`);
3. a **fresh** read-only `snapshot_db.sql` of the real database is `IDENTICAL` to the snapshot taken when the backup was made (`group-17c/evidence/source-snapshot-db.txt`): same schema, catalog, ownership, permissions, constraints, indexes, extensions, **row counts** and Alembic revision (0005);
4. the restore of the second copy into a disposable cluster was proven `IDENTICAL` (17C, `g17c-restore-output.txt`).

**Stop condition: any difference (schema, catalog, ownership, permissions, counts or revision) means the backup no longer describes the database. Do not move, delete or overwrite any existing backup; stop and ask the owner to authorise a new backup.** A new backup is taken only with `group-17c/run_17c_backup.sh`, which refuses to run while a `pre_17b` backup exists in either folder (the owner decides what happens to the old one).

```bash
# 4. keep the OLD images for the rollback (S12 does this; it only adds image tags), from the ids the CONTAINERS use
docker tag "$(docker inspect -f '{{.Image}}' asistenteia-backend-1)" asistenteia-backend:pre-17b
docker tag "$(docker inspect -f '{{.Image}}' asistenteia-worker-1)"  asistenteia-worker:pre-17b
# 5. build the NEW images now, while the stack is still up (S12; the worker image from scratch: 14 minutes and 3.2 GB; cached: seconds)
docker compose build bootstrap migrate cli backend worker      # a failure here is a NO-GO before anything changed; creates no container
# 6. (S13, owner's decision) the new settings load with the REAL files: a throw-away container that prints nothing
```

Stop condition: any hash differs, a manifest or ACL check fails, the backup no longer equals the real state, a transaction older than a minute is open, a prepared transaction exists, free RAM is below 8 GB, the catalog of the real database differs from the reconstructed 0005, or the build fails. **NO-GO.**

## 17B.2 Stop the services and prepare the files

```bash
docker compose stop backend worker            # measured: about 1.4 s; the db container is NOT touched
bash "$S"/tools/preflight_readonly.sh asistenteia-db-1 asistenteia <TMP>/after-stop     # snapshot again
bash "$S"/tools/compare_snapshots.sh <TMP>/preflight-before/snapshot-db.txt <TMP>/after-stop/snapshot-db.txt   # IDENTICAL: nothing was written between the backup and the stop
python "<REPO>/openspec/changes/database-least-privilege/reports/group-17a/tools/prepare_env_files.py" "<REPO>/backend" --dry-run --strip-legacy
python "<REPO>/openspec/changes/database-least-privilege/reports/group-17a/tools/prepare_env_files.py" "<REPO>/backend" --strip-legacy
# creates backend/.env.roles .env.migrate .env.cli (the orchestrator then gives the four new files the owner-only descriptor, secure_file_acl.ps1 -Rights Modify; tested with Docker Desktop in group-17b/test_env_acl_docker.sh), rewrites DATABASE_URL (user and password) in .env and .env.worker,
# REMOVES POSTGRES_USER/PASSWORD/DB from .env and MOVES TEST_* to a new backend/.env.test (host tests read it first),
# copies .env, .env.worker and .env.db to *.pre-17b; prints names only, refuses to run twice or on a quoted URL.
# WHY --strip-legacy: the real backend/.env (checked in the final preflight, names only) still carries POSTGRES_DB, POSTGRES_PASSWORD,
# POSTGRES_USER and TEST_DATABASE_URL besides DATABASE_URL: without stripping them the API container would keep receiving the
# administrator credentials after 17B. The tool refuses to run without the flag when it finds them.
```

Stop condition: the tool refuses (a file is missing, the current `DATABASE_URL` is not the administrator of `.env.db`, a target already exists). Fix the cause; do not edit by hand.

## 17B.3 Bootstrap, adoption, migration, verification

```bash
docker compose run --rm --no-deps bootstrap                                  # exit 1 EXPECTED: lists the ownership drift
docker compose run --rm --no-deps bootstrap python -m app.cli db-adopt --database asistenteia             # dry run: 9 objects
docker compose run --rm --no-deps bootstrap python -m app.cli db-adopt --apply --database asistenteia     # measured 1.6 s
docker compose run --rm --no-deps migrate                                    # Alembic 0005 -> 0006 and the grants
docker run --rm --network asistenteia_default --env-file backend/.env.migrate --env-file backend/.env.roles \
  --entrypoint python asistenteia-migrate:latest -m app.cli db-verify          # "no findings" (the image compose built for the migrate service)
```

Stop conditions: the dry run lists anything but the 9 expected objects (`alembic_version`, six tables, `document_status`, `user_role`); `db-adopt --apply` exits non-zero (it is atomic: nothing changed); `db-verify` reports anything. Run the **rollback of the reached stage** (section "Rollback").

## 17B.4 Switch the services

```bash
# the images were built in 17B.1; the old ones are tagged pre-17b
docker compose up -d --no-deps --force-recreate backend worker      # both healthy about 125 s later (worker start_period)
until [ "$(docker inspect -f '{{.State.Health.Status}}' asistenteia-worker-1)" = healthy ]; do sleep 5; done   # wait for it: the worker needs up to 120 s plus the model load
```

(`--no-deps` on purpose: with dependencies compose would run `bootstrap` again and could recreate `db`.) Prove the roles: `SELECT usename, count(*) FROM pg_stat_activity WHERE datname='asistenteia' GROUP BY 1` shows `asistente_app` and `asistente_worker`, and not `asistente`.

## 17B.5 Functional validation and cleanup of the synthetic data

Synthetic accounts and data only (`g17b-*@example.com`), through the real endpoints: registration, login, the teacher created by `docker compose run --rm -T --no-deps cli create-teacher ... --password-stdin`, a subject, an enrollment, a TXT upload that the worker takes to `ready`, the denied cases (student cannot create a subject; the API role cannot insert a teacher; the worker role cannot read `users`), `db-verify` again. The replica ran 15 checks plus the 101 of group 13 in group 16. Cleanup: delete the synthetic rows as the administrator (`DELETE ... WHERE email LIKE 'g17b-%'`, children first) and check that the row counts equal those of the preflight.

## 17B.6 Rotation of the administrator password (after the acceptance, see `credentials-and-services-map.md` section 4)

About 8 s, services running; destroys the exposed value; then destroy the `*.pre-17b` copies.

## Rollback (rehearsed on the replica from the final stage, with data written under the roles and the password rotated: 134 s; and from each earlier stage in `g17a-stages-output.txt`)

Stop the services first (`docker compose rm -sf backend worker`), then, **as far as the stage reached**:

| Stage reached | Commands |
|---|---|
| files prepared, services stopped, nothing else done | 5, 6 only (`prepare_env_files.py --rollback`, then start the previous stack with the shipped override: `docker compose start` would load the new code from the mount and refuse the administrator URL) |
| after the bootstrap | 3, 4, 5, 6 |
| after the adoption | 3, 4, 5, 6 |
| after the migration and grants | **2**, 3, 4, 5, 6 |
| after the services switched (with or without data) | 2, 3, 4, 5, 6 (the data written under the roles stays) |

1. (the stop above)
2. `db-migrate --downgrade 0005` with `.env.migrate` (Alembic as the migrator: about 1.3 to 1.7 s).
3. `db-adopt --rollback --remove-roles --apply --database asistenteia` with `.env.roles` (ownership back to the administrator, the four roles dropped; about 2 s). Dry run first: it names the database.
4. `psql ... -f restore_public_cluster.sql` on `postgres` and `restore_public_schema.sql` on `asistenteia` (PUBLIC `CONNECT`/`TEMP`/`USAGE` back).
5. `python prepare_env_files.py <REPO>/backend --rollback` (restores `.env` and `.env.worker` from the `.pre-17b` copies with the administrator password of the CURRENT `.env.db`, renames the three new files `*.rolled-back`).
6. Start the previous stack from its own definition **plus the shipped override** (without it the `backend/app` bind mount of main's file is the new code and the services refuse the administrator URL and crash-loop):
   ```bash
   git show main:docker-compose.yml > <TMP>/compose.main.yml
   O="<REPO>/openspec/changes/database-least-privilege/reports/group-17a/tools/compose.rollback.override.yml"
   docker compose -p asistenteia --project-directory "<REPO>" -f "<TMP>/compose.main.yml" -f "$O" config | grep -cE 'backend[/\\]app'   # pre-GO check: must print 0 (Windows prints backslashes in bind sources)
   docker compose -p asistenteia --project-directory "<REPO>" -f "<TMP>/compose.main.yml" -f "$O" config | grep -c 'image: asistenteia-.*:pre-17b'   # must print 2
   docker compose -p asistenteia --project-directory "<REPO>" -f "<TMP>/compose.main.yml" -f "$O" up -d --no-deps backend worker
   ```
   The replica rehearsed exactly this file (`compose.rollback.override.yml`) on top of main's compose file, with only the isolation of ports and env files added.

Measured on the replica: services available again about 125 s after starting them (worker start period); data written under the roles survived; the previous API and worker processed a login and an upload on the rolled-back database.

**Also not restored / lost:** the container logs of the recreated services (copy `docker logs` of the worker and backend into `<TMP>` before 17B.4 and before a rollback if they matter); a plain `docker compose up` on this branch after a rollback fails by design (`.env.roles` was renamed, so `bootstrap` fails and the services are not started) until the files are prepared again.

**What the rollback does not restore byte for byte** (differences measured against the state before, ownership, roles, grants and rows identical): default ACLs are written explicitly (`NULL` becomes the equivalent explicit ACL on the 7 tables and the databases, `PUBLIC` connect/temp on every database incl. templates); the compose spec of the recreated containers; the new image tags; the time (services down about 2 to 3 minutes); the role passwords (they no longer exist); data created by the new services. The recovery of last resort is the verified dump (section "recovery": `DROP DATABASE`, `createdb`, `pg_restore`; about 1 s when empty) and gives the exact original catalog, including the `NULL` ACLs.

## Stop conditions for the whole run

Any unexpected exit code, any `db-verify` finding, any open transaction at the start, any hash mismatch, a lost connection during the adoption (check `pg_stat_activity`, then rollback or recovery), memory below 8 GB, or a request of the owner. After a stop, take the rollback column of the stage reached; never improvise a fix on the real database.

## Timings measured on the replica (empty database; real values are expected to be close because the data is empty)

| Step | Time |
|---|---|
| backup (dump, hash, list, copy, second copy) | 1.4 s |
| restore of the backup into a disposable cluster | 0.36 s |
| stop the two services | 1.4 s |
| prepare the files (tool) | 0.25 s |
| bootstrap (first, with drift) | 1.5 s |
| adoption dry run / applied | 1.5 s / 1.6 s |
| migration 0006 and grants | 1.6 s |
| `db-verify` | 1.4 s |
| build of the five images (done BEFORE the stop, services up) | the worker image from scratch: 859 s (14 min, 3.2 GB); the API image a few seconds; cached layers much less. Not part of the downtime |
| recreate the two services and wait until healthy | about 125 s (dominated by the worker model load and `start_period`) |
| rotation of the administrator password with recreation of `db` | 8.3 s |
| full rollback | 134 s (about 9 s of commands, about 125 s of service start) |
| recovery from the dump | 1.1 s |
| rollback from each earlier stage (commands only, `g17a-stages-output.txt`) | after the bootstrap 2.2 s; after the adoption 2.5 s; after the migration 4.9 s (forward 1.6 s, 3.4 s, 7.2 s) |

## Remote verification of the `privileges` workflow (GitHub Actions; NOT part of 17B, nothing is pushed without the owner's authorisation)

TD-045 stays open until a green remote run exists. Procedure (details and commands in `group-17c/ci-remote-proposal.md`): (1) before any push: clean tree, `openspec validate --all --strict`, the secret classification (`g17c-secret-classification.md`) with no NO-GO; (2) the owner authorises `git push -u origin feature/database-least-privilege` (branch only, no pull request); (3) `gh run list --branch feature/database-least-privilege`, `gh run watch <id> --exit-status`, `gh run view <id> --log` kept outside the repository first; (4) acceptance: `backend`, `privileges` and `frontend` green, the `privileges` summary shows every report with at least the floors (unit 60, role suites 400, roles mode 480) and none skipped; (5) on failure: no pull request, reproduce locally, fix test-first, push again. Branch protection is not available on this plan (403 on a private repository), so the merge rule is procedural: no merge to `main` without a green `privileges` run linked in the pull request. A 17B run does not depend on this result; the risk stays accepted in gate L.

