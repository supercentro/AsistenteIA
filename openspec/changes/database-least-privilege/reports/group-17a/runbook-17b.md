# Runbook 17B: real run on the development database (PLAN; nothing here was executed on the real stack)

Prepared in group 17A. Every command below was rehearsed on a disposable replica of the development stack (`run_17a_replica.sh`) or on a disposable cluster (`run_17a_stages.sh`); the evidence is in `g17a-replica-output.txt` and `g17a-stages-output.txt`. Placeholders: `<REPO>` is the checkout, `<BACKUPS>` the backups folder outside the repository, `<TMP>` a folder outside the repository for evidence. Commands are for a POSIX shell (Git Bash); `docker compose` is run from `<REPO>` with the real project name `asistenteia`.

**Shell.** Git Bash on Windows rewrites arguments that look like paths: start the session with `export MSYS_NO_PATHCONV=1`, otherwise `/tmp/...` arguments of `docker exec` and `docker cp` are mangled. Use the Windows form (`C:/...`) for paths handed to `docker cp`, `docker run -v` and `python` from Git Bash.

**Authorisation.** 17B starts only after the owner authorises it in a new message, and each phase that writes needs the explicit "GO" of the checklist (`checklist-go-nogo.md`). Task 3.3b (the creation of the role files and the edit of the two `DATABASE_URL` values) is part of that authorisation.

## 0. What is going to change, and what is not

Changes: roles `asistente_migrator`, `asistente_app`, `asistente_worker`, `asistente_cli` (new); ownership of `alembic_version`, the six tables and the two enum types (administrator → migrator); the grants; `users.role` default (revision 0006); `PUBLIC` loses `CONNECT`/`TEMP` on every database of the cluster, `USAGE` on schema `public` of `asistenteia`; three new environment files and two edited lines; the API and the worker run new images and connect with restricted roles. Not changed: data (all tables are empty today), `asistenteia_test`'s content, the volume, the administrator role (until step 17B.6).

Known consequences: the API and the worker are **down** from step 17B.2 until step 17B.5 (measured on the replica: about 5 s of commands plus about 125 s until the worker is healthy because of its `start_period`); a restart of the old stack with the old images keeps working only if rolled back first; the new code **refuses** a superuser connection.

## 17B.1 Preflight (read only) and backup

```bash
export MSYS_NO_PATHCONV=1
cd <REPO>
# 1. identity of the cluster and of the database: write the output in <TMP>/preflight-before
bash <REPO>/openspec/changes/database-least-privilege/reports/group-17a/tools/preflight_readonly.sh asistenteia-db-1 asistenteia <TMP>/preflight-before
# expected: container asistenteia-db-1 healthy, project asistenteia, volume asistenteia_db_data, revision 0005,
#           0 open transactions / idle in transaction / prepared / ungranted locks, read-only session, free disk
# 2. gate D: the catalog of the real database against the committed expected baseline of 0005 (rows = all 0, alembic_version = 1)
S=<REPO>/openspec/changes/database-least-privilege/reports/group-17a
bash $S/tools/compare_snapshots.sh $S/expected/snapshot-db-0005.txt <TMP>/preflight-before/snapshot-db.txt                       # must print IDENTICAL (about 120 lines)
MIN_LINES=5 bash $S/tools/compare_snapshots.sh $S/expected/snapshot-cluster.txt <TMP>/preflight-before/snapshot-cluster.txt    # roles, databases, ACLs: IDENTICAL
# 3. state of ALL the services and what they run: the backend (exited today) and the worker mount backend/app
docker ps -a --format '{{.Names}} {{.Image}} {{.Status}}'
docker inspect asistenteia-backend-1 asistenteia-worker-1 --format '{{.Name}} image={{.Image}} status={{.State.Status}} restarts={{.RestartCount}} started={{.State.StartedAt}}'
docker logs --tail 5 asistenteia-worker-1 2>&1 | grep -ciE 'superuser|refus'          # 0 expected: the running worker must not be refusing anything
# 4. keep the OLD images for the rollback, from the images the CONTAINERS use (this changes only image metadata)
docker tag "$(docker inspect -f '{{.Image}}' asistenteia-backend-1)" asistenteia-backend:pre-17b
docker tag "$(docker inspect -f '{{.Image}}' asistenteia-worker-1)"  asistenteia-worker:pre-17b
docker images --no-trunc --format '{{.Repository}}:{{.Tag}} {{.ID}}' | grep -E ':(latest|pre-17b) ' | grep asistenteia-   # record the ids in the report
# 5. build the NEW images now, while the stack is still up (they are needed from step 17B.3 on; the worker image
#    took 14 minutes and 3.2 GB when built from scratch on the workstation, see g17a-worker-build.txt)
docker compose build bootstrap migrate cli backend worker      # time it; a failure here is a NO-GO before anything changed
docker compose config --images                                  # the image names compose will use: record them
# 6. the new settings load with the REAL files: see the note after this block (nothing is printed)
# 7. variable NAMES of the real env files against their examples (names only; read the list before continuing)
python $S/tools/check_env_names.py <REPO>/backend
```

(Step 6 is only written down as a requirement: use the image name printed by `docker compose config --images` for the backend and the worker and run `python -c "from app.core.config import load_settings; load_settings()"` / `load_worker_settings()` with `--env-file backend/.env` and `backend/.env.worker`. It reads the real files into a container that prints nothing and is removed; do it with the new images built in step 5. It was not run on the real files in 17A.)

Backup (the procedure rehearsed on the replica, 1.4 s on an empty database):

```bash
STAMP=$(date -u +%Y%m%dT%H%M%SZ)
docker exec asistenteia-db-1 sh -c 'pg_dump -U "$POSTGRES_USER" -d asistenteia -Fc -f /tmp/asistenteia_pre_17b.dump'
docker exec asistenteia-db-1 sha256sum /tmp/asistenteia_pre_17b.dump                              # note the value
docker exec asistenteia-db-1 sh -c 'pg_restore --list /tmp/asistenteia_pre_17b.dump | wc -l'      # about 57 lines at 0005
docker cp asistenteia-db-1:/tmp/asistenteia_pre_17b.dump "<BACKUPS>/asistenteia_pre_17b_$STAMP.dump"
sha256sum "<BACKUPS>/asistenteia_pre_17b_$STAMP.dump"                                            # equal to the one inside
cp "<BACKUPS>/asistenteia_pre_17b_$STAMP.dump" "<SECOND-LOCATION>/"                               # second copy, same hash
# restore into a DISPOSABLE cluster and compare (see backup-and-recovery.md)
```

Backup first, then stop; between them the services can still write, so after the stop (17B.2) take `snapshot_db.sql` again and compare it with the one taken at the preflight: it must be `IDENTICAL` (the rehearsal does this), otherwise take a new backup.

Stop condition: any hash differs, `pg_restore --list` fails, the restored copy differs from the source in `compare_snapshots.sh`, a transaction older than a minute is open, a prepared transaction exists, free RAM is below 8 GB, or the catalog of the real database differs from the reconstructed 0005. **NO-GO.**

## 17B.2 Stop the services and prepare the files

```bash
docker compose stop backend worker            # measured: about 1.4 s; the db container is NOT touched
bash $S/tools/preflight_readonly.sh asistenteia-db-1 asistenteia <TMP>/after-stop     # snapshot again
bash $S/tools/compare_snapshots.sh <TMP>/preflight-before/snapshot-db.txt <TMP>/after-stop/snapshot-db.txt   # IDENTICAL: nothing was written between the backup and the stop
python <REPO>/openspec/changes/database-least-privilege/reports/group-17a/tools/prepare_env_files.py <REPO>/backend --dry-run
python <REPO>/openspec/changes/database-least-privilege/reports/group-17a/tools/prepare_env_files.py <REPO>/backend
# creates backend/.env.roles .env.migrate .env.cli, rewrites DATABASE_URL (user and password) in .env and .env.worker,
# copies .env, .env.worker and .env.db to *.pre-17b; prints names only, refuses to run twice
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
   O=<REPO>/openspec/changes/database-least-privilege/reports/group-17a/tools/compose.rollback.override.yml
   docker compose -p asistenteia --project-directory <REPO> -f <TMP>/compose.main.yml -f $O config | grep -cE 'backend[/\\]app'   # pre-GO check: must print 0 (Windows prints backslashes in bind sources)
   docker compose -p asistenteia --project-directory <REPO> -f <TMP>/compose.main.yml -f $O config | grep -c 'image: asistenteia-.*:pre-17b'   # must print 2
   docker compose -p asistenteia --project-directory <REPO> -f <TMP>/compose.main.yml -f $O up -d --no-deps backend worker
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
