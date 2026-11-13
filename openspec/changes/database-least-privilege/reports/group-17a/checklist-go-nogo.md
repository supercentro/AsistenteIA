# GO / NO-GO checklist for step 17B (group 17A)

Every line is verifiable. A line is "done" only with its evidence file or a pasted result. **One NO-GO stops 17B.** The first write operation (17B.2: `docker compose stop`, then everything after) needs the owner's explicit "GO" **after** sections A to L are green.

| # | Gate | How to verify | Expected | Evidence |
|---|---|---|---|---|
| **A** | **Authorisation** | the owner's message authorising 17B, task 3.3b and the rotation window | explicit, naming 17B | copy of the message in the report |
| A2 | Nothing else in flight | `git status`, `git log -1`, branch `feature/database-least-privilege` | clean tree (except the 7 reference documents), HEAD recorded | report |
| **B** | **Exact backup, restore proven** | sections 1 and 2 of `backup-and-recovery.md` | hashes equal in 3 places, `pg_restore --list` readable, the restored copy `IDENTICAL` to the source | `<TMP>/source-db.txt`, `restored-db.txt`, compare output |
| B2 | Older backups untouched | `sha256sum` of the 0004 dump equals its `.sha256` | equal | report |
| **C** | **Unambiguous cluster** | `tools/preflight_readonly.sh asistenteia-db-1 asistenteia <TMP>/preflight-before` | container `asistenteia-db-1`, compose project `asistenteia`, volume `asistenteia_db_data`, host port 127.0.0.1:5442, database `asistenteia`, PostgreSQL 15.19, `read_only_session on` | `identity.txt` |
| **D** | **Catalog fingerprint equal to the rehearsed one** | `snapshot-db.txt` of the real database against the replica's S0 (`compare_snapshots.sh`) | revision 0005; same tables, columns, constraints, enum labels, indexes; original owners and ACLs; all `rows` lines 0 (the rows of `alembic_version` = 1) | the diff |
| **E** | **Transactions and sessions** | `activity.txt` | 0 open transactions older than 1 min, 0 idle in transaction, 0 prepared transactions, 0 ungranted locks, no long query; only sessions of `asistente` | `activity.txt` |
| **F** | **Services and dependencies identified** | `docker ps`, `docker inspect` of worker and backend | worker healthy; image ids recorded (the development `latest` tags are the same ids as `main-f455234`); old images tagged `pre-17b`; main's compose file saved for the rollback | report |
| F2 | The rollback tooling is present | the files of `reports/group-17a/tools` are those tested (hash recorded) | `prepare_env_files.py`, `restore_public_*.sql`, `compose.rollback.override.yml`, `compare_snapshots.sh`, `snapshot_*.sql`, `preflight_readonly.sh` | `sha256sum` list |
| **G** | **Restricted roles prepared** | `prepare_env_files.py --dry-run` on the real folder, then (after GO) the real run | the dry run accepts the files; the real run creates 3 files and 3 `.pre-17b` backups, prints names only | tool output |
| **H** | **Complete rollback procedure** | `runbook-17b.md` rollback table and the tested evidence | rehearsed from every stage (`g17a-stages-output.txt` 20/20) and from the end state (`g17a-replica-output.txt` 76/76); the owner knows the differences (default ACL representation) | those files |
| H2 | Who decides and when to stop | the stop conditions of the runbook | read and acknowledged by the owner | report |
| **I** | **Exposed credential with a planned rotation** | `credentials-and-services-map.md` section 4; a password manager entry prepared | rotation scheduled after the acceptance; `.pre-17b` copies to be destroyed | report |
| **J** | **Quality gates** (on the final code) | ruff check and format, `mypy --strict`, unit tests, role-bound and roles-mode suites, migrations, frontend gates, `openspec validate --all --strict` | all green, as in the last report (1377 / 864 / 439 / 484; frontend statements 97.68 %) | the gate outputs |
| J2 | CI | the owner's decision about the first GitHub run (`ci-first-run.md`) | taken and recorded (a green local gate is not a remote validation) | report |
| **K** | **Resources** | free memory, disk, Docker responsive | at least 8 GB RAM, three times the dump size on disk | preflight `free_ram_gb` |
| **L** | **Residual risks accepted** | the list below | each accepted in writing | report |
| **M** | **Explicit "GO" before the first write** | the owner's message "GO 17B.2" after A to L are green | present | report |

Residual risks the owner must accept for 17B:

1. The API and the worker are down for about 2 to 3 minutes, and again for the same time on a rollback (dominated by the worker's start period).
2. The new code refuses to start as a superuser, so the previous stack must be started from the old images (override provided), never from the new `backend/app`.
3. The rollback is identical except the representation of default ACLs (`NULL` becomes the equivalent explicit ACL); the dump gives the exact one.
4. `db-verify` assumes one application database per cluster: do not bootstrap `asistenteia_test`.
5. The closing of `PUBLIC` is cluster-wide and is restored by script, not by `db-adopt --rollback`.
6. The pre-17B copies of the env files hold the exposed password until they are destroyed.
7. The rehearsal ran on a reconstructed 0005 copy and an empty database, with the same image ids as the development stack, not on the real data.
8. GitHub Actions has not run the workflow (TD-045).

NO-GO examples: a hash differs; the restored copy is not `IDENTICAL`; the real catalog differs from the rehearsed one; an open or prepared transaction; the worker is unhealthy for an unknown reason; less than 8 GB free; the owner has not said "GO".
