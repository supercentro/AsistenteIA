# Backup and recovery procedure for step 17B (group 17A design; rehearsed on a replica, not run on the real database)

Goal: a new backup of the development database at revision 0005 that is proven restorable **before** anything changes, a complete comparison tool, and a recovery of last resort. The original backup (`asistenteia_pre_0005_20261112T034241Z.dump`, revision 0004) and every earlier backup are never modified or overwritten; the new one gets a new name.

## 1. Taking the backup (the only operation on the real database that 17B.1 adds, and it only reads)

```bash
STAMP=$(date -u +%Y%m%dT%H%M%SZ)
docker exec asistenteia-db-1 sh -c 'pg_dump -U "$POSTGRES_USER" -d asistenteia -Fc -f /tmp/asistenteia_pre_17b.dump'   # custom format, inside the container (no shell re-encodes the stream)
docker exec asistenteia-db-1 sha256sum /tmp/asistenteia_pre_17b.dump                                                # hash INSIDE
docker exec asistenteia-db-1 sh -c 'pg_restore --list /tmp/asistenteia_pre_17b.dump | wc -l'                         # must list the 6 tables, vector, 2 enum types (about 57 lines at 0005)
docker cp asistenteia-db-1:/tmp/asistenteia_pre_17b.dump "<BACKUPS>/asistenteia_pre_17b_$STAMP.dump"                 # a NEW name
sha256sum "<BACKUPS>/asistenteia_pre_17b_$STAMP.dump"                                                              # equal to the one inside
cp "<BACKUPS>/asistenteia_pre_17b_$STAMP.dump" "<SECOND-LOCATION>/"
sha256sum "<SECOND-LOCATION>/asistenteia_pre_17b_$STAMP.dump"                                                      # second copy, same hash
# manifest next to the dump (database, revision, size, sha256, toc lines, row counts, created UTC, source; no data) and its .sha256 file
# Integrity files PER COPY (TD-049): never `sha256sum <absolute path>` (it prints the path and the user name into the file).
# Run once per folder; each folder gets its own .sha256 (dump + manifest, file names only) and manifest, and `verify` fails closed.
python -I "<REPO>/openspec/changes/database-least-privilege/reports/group-17c/tools/backup_manifest.py" write "<BACKUPS>" "asistenteia_pre_17b_$STAMP.dump" --copy primary --meta alembic_revision=0005
python -I "<REPO>/openspec/changes/database-least-privilege/reports/group-17c/tools/backup_manifest.py" write "<SECOND-LOCATION>" "asistenteia_pre_17b_$STAMP.dump" --copy second --meta alembic_revision=0005
python -I "<REPO>/openspec/changes/database-least-privilege/reports/group-17c/tools/backup_manifest.py" verify "<BACKUPS>" "asistenteia_pre_17b_$STAMP.dump" --copy primary   # also before any restore (use Windows paths for python)
# Restrictive permissions on Windows (chmod has no effect there): inheritance removed, one rule (current user, Read), descriptor
# re-read and verified, fails closed. Apply it to the dump, the .sha256 and the manifest of BOTH copies (17C, group-17c/tools):
powershell -NoProfile -ExecutionPolicy Bypass -File "<REPO>/openspec/changes/database-least-privilege/reports/group-17c/tools/secure_file_acl.ps1" -Path "<BACKUPS>/asistenteia_pre_17b_$STAMP.dump"
# FOLDER policy (tools/secure_folder_acl.ps1, -VerifyOnly to inspect; applying it to the real folders needs the owner's separate OK):
# inheritance off; SYSTEM Full, Administrators Full (kept on purpose), current user Modify+DeleteSubdirectoriesAndFiles (create, read,
# verify and delete a copy, not Full Control); nobody else. `run_17c_backup.sh` reports the verdict for both destination folders.
# -VerifyOnly re-checks an existing file without touching it. Known limits: a member of Administrators can still take ownership,
# and the FOLDER keeps its own ACL (TD-049). Comparison limit: snapshot_db.sql compares owners, ACLs, constraints, defaults, enums,
# indexes, extensions and row COUNTS; once the database holds data, add a content check (for example pg_dump --data-only of the
# source and the copy, hashed) before trusting a restore.
```

Existing 17b backup (2026-11-14, TD-049): the folder policy is applied to both folders and the legacy `.sha256` were replaced with `tools/migrate_legacy_sha256.py` (all or nothing; stash and SDDL export outside the repository; `tools/acl_descriptor.ps1 -Mode Restore|Compare` restores the folder descriptors). Its new manifest is `<dump>.integrity.txt` (`backup_manifest.py ... --manifest-suffix .integrity.txt`); the legacy `<dump>.manifest.txt` stays as a descriptive note. Manual rollback order: (1) `acl_descriptor.ps1 -Mode Restore -Path <folder> -Store <rollback>/<label>.sddl` for each folder; (2) copy `<rollback>/<label>.sha256.orig` over `<dump>.sha256` and delete `<dump>.integrity.txt`; (3) compare with `inventory-before.txt`. PowerShell `Remove-Item` cannot delete a Read-restricted file; use `[IO.File]::Delete` or Python (the folder's delete-child right).

(The dump holds the table data, ownership and ACLs; the roles are cluster objects and are **not** in it, which is why the recovery re-applies the restore scripts, see section 4.) Remove `/tmp/asistenteia_pre_17b.dump` from the container only after the copies are verified (a container's `/tmp` is not durable).

## 2. Proving that it restores (before any change)

Into a disposable cluster that shares nothing with the development stack (own network, tmpfs data, no published port, synthetic administrator, PostgreSQL 15.19 + pgvector 0.8.7):

```bash
docker network create g17-backup-net
docker run -d --name g17-backup-pg --network g17-backup-net --tmpfs /var/lib/postgresql/data \
  -e POSTGRES_USER=asistente -e POSTGRES_PASSWORD=<throwaway> -e POSTGRES_DB=postgres pgvector/pgvector:0.8.7-pg15
docker cp "<SECOND-LOCATION>/asistenteia_pre_17b_$STAMP.dump" g17-backup-pg:/tmp/restore.dump      # the SECOND copy, so both copies are exercised
docker exec g17-backup-pg createdb -U asistente asistenteia
docker exec g17-backup-pg pg_restore -U asistente -d asistenteia --exit-on-error /tmp/restore.dump   # measured 0.36 s on an empty database
```

Compare the restored copy with the source **with the same read-only tool on both** (`tools/snapshot_db.sql`; it prints no secret):

```bash
S=<REPO>/openspec/changes/database-least-privilege/reports/group-17a/tools
docker exec -i asistenteia-db-1 sh -c 'psql -U "$POSTGRES_USER" -d asistenteia -At -F "|" -v ON_ERROR_STOP=1 -f -' < $S/snapshot_db.sql > <TMP>/source-db.txt
docker exec -i g17-backup-pg  sh -c 'psql -U asistente -d asistenteia -At -F "|" -v ON_ERROR_STOP=1 -f -' < $S/snapshot_db.sql > <TMP>/restored-db.txt
bash $S/compare_snapshots.sh <TMP>/source-db.txt <TMP>/restored-db.txt        # must print IDENTICAL
```

It compares: extension versions and owners, revision, schema `public` owner and ACL, tables with owner, ACL and row-level-security flag, every column with type, nullability, default and column ACL, indexes, constraints, enum types with labels, sequences, default ACLs, foreign objects, **exact row counts**. The replica showed IDENTICAL on about 120 lines. **A backup that was not restored and compared is not accepted.** Then destroy the disposable cluster (`docker rm -f g17-backup-pg; docker network rm g17-backup-net`).

## 3. What the comparison tool does not cover (so nobody over-reads it)

Cluster-level objects (roles, `pg_db_role_setting`) are compared with `snapshot_cluster.sql`, not inside the dump; large objects, event triggers, publications and subscriptions are not described (there are none in this schema); table contents are compared by count, not by value (a byte-level comparison is `pg_dump` of both and `diff`, which the owner may add: the data is empty today).

## 4. Recovery of last resort (rehearsed; 1.1 s on an empty database)

When the rollback is not enough (a half-applied adoption that the commands cannot repair, a lost volume, an unexplained state):

1. Stop `backend` and `worker`. Check the dump's hash against the manifest.
2. As the administrator on `postgres`: `DROP DATABASE asistenteia WITH (FORCE)`, then `createdb asistenteia`, then `pg_restore -d asistenteia --exit-on-error <dump>`.
3. The roles are cluster objects the dump does not contain: if they exist (the rollback was not run), remove them with the rollback commands first; if they were dropped, nothing else is needed. If the closing of `PUBLIC` is still in place, run `restore_public_cluster.sql` and `restore_public_schema.sql`.
4. Compare with `snapshot_db.sql` against the pre-17B snapshot (`IDENTICAL` expected, **including the `NULL` default ACLs**, which the rollback restores only in an equivalent explicit form).
5. Start the previous stack (runbook, rollback step 6).

Not covered by a dump: the cluster-wide closing of `PUBLIC` on other databases (use the restore scripts) and any data written after the backup (accepted: the stack is stopped from 17B.2 on).
