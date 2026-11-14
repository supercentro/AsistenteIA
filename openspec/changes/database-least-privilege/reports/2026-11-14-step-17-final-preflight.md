# Group 17: final preflight before 17B (2026-11-14)

Branch `feature/database-least-privilege`, code at `97f2161`. Authorised scope: the final preflight only. **No schema, role, grant, credential or environment change was applied to the development stack**: no `db-bootstrap`, `db-adopt`, `db-migrate`, `db-grants`, no migration 0006, no role, ownership or privilege change, no password change, no real `.env` written (the tools ran in dry-run mode; a before/after listing of the folder was compared in the session, with no output file kept), no service stopped, started or recreated, no `docker compose up`, nothing pushed. The only contacts with the real PostgreSQL were read-only sessions and one `pg_dump` (a read), plus one file written in the container's `/tmp` and removed. The real files were read in memory in two places, both authorised by the owner for this task and neither printing a value: the secret scan (to compare candidates with the real values) and the dry run of the env tool (to validate that `DATABASE_URL` is the administrator of `.env.db`).

## 1. The 14 secret-looking matches (`g17c-secret-classification.md`)

All 14 are **synthetic test fixtures** (URLs with throw-away passwords of at least 16 characters, which the settings classes require): 8 files under `backend/tests/`, 2 of them named as synthetic by their own value. The comparison with the real administrator password and the real JWT secret found **0** lines in the whole local history and **0** files in the working tree containing a real value; none of the commits is on the remote. 11 more matches in other scopes (the CI throw-away database password, an example in the guide, two made-up values of a mutation script and of the env tool's self-test) are synthetic too; two of those commits are already on `origin/main`. **No NO-GO for the push from the secrets point of view.**

## 2. Compatibility with the real env files (names only)

- Self-test of the tool on synthetic folders: **80 of 80** (77 plus 3 added after the independent review: TEST_ names of `.env.worker` moved, rollback keeps the files it replaces, a second rollback refused; both fixes checked by mutation). Also changed after the review: the undo now runs on Ctrl+C and registers each new file before writing it (CRLF, BOM, special characters, comments, queries, quotes, partial copy, undo, rollback, legacy names).
- Dry run on the real folder: the tool **refuses** without `--strip-legacy` because the real `backend/.env` still carries `POSTGRES_DB`, `POSTGRES_PASSWORD`, `POSTGRES_USER` and `TEST_DATABASE_URL` (the API container would keep receiving the administrator credentials after 17B); with `--strip-legacy` it plans to remove the first three and move the last to a new `.env.test`. The tool was extended for this (tests first); the runbook and the credentials map now use `--strip-legacy` and the rotation covers `.env.test`. `DATABASE_URL` of `.env` and `.env.worker` is the administrator of `.env.db` (the check passed).
- `check_env_names.py` on the real files (figures taken from the session output; no output file was kept): `.env` has 9 names and lacks 17 optional tuning names that the example documents (the code has defaults), `.env.worker` has 21 and lacks only the test-only `ALLOW_SUPERUSER_DATABASE_ROLE` (default off). No `.env.test`, `.env.roles`, `.env.migrate` or `.env.cli` exists yet.
- Nothing was written in `backend/`.

## 3. The new backup of 0005

`asistenteia_pre_17b_20261114T013150Z.dump`: `pg_dump -Fc` (PostgreSQL 15.19) of `asistenteia`, 17 437 bytes, 57 lines in `pg_restore --list`, SHA-256 `d0a2ad6bfc0c392d765473acbaf7bfbec25ff24eea99e2828e3377176d6279d9` (equal outside and inside the container). Stored outside the repository in the owner's `Backups` folder with a `.sha256` file and a manifest (no data); a **second independent copy** in another folder, same hash; both copies are readable only by the owner's account: the script's own `icacls` call did NOT take effect (its output still shows inherited SYSTEM and Administrators entries), so the inheritance was removed by hand afterwards and the result was listed for all six files in the session (no evidence file; the script is to be corrected before a rerun). Of the older backups only `pre_0005` has a hash check in the evidence (equal to its recorded one); `pre_0004` was not hash-checked, but no name was reused and nothing was written to that folder except the new files. The source database did not change while the dump was taken (snapshots equal). Before the dump: identity checked (container `asistenteia-db-1`, compose project `asistenteia`, port 127.0.0.1:5442, database `asistenteia`, revision 0005, read-only session), 0 open transactions, no prepared transaction, no ungranted lock, the only client is the worker container.

## 4. Restoration and equivalence: **NOT DONE (blocked by the memory gate)**

The restore into a disposable PostgreSQL requires 8 GB of free RAM. The host had 6.5 to 7.6 GB free (other processes: memory compression and WSL outside this project) during the checks and the 30 minutes the second script waited, so it stopped (`g17c-restore-output.txt`). I did not override the gate. What is already proven without the restore: the real catalog is `IDENTICAL` to the expected baseline of 0005 (118 compared lines) and the real cluster too (gate D), and the hashes of both copies match; what is NOT proven is that this dump restores and equals the source (check B). **This is a NO-GO condition of the checklist until `run_17c_restore.sh` passes** (it reuses the source snapshot taken at the dump; it needs only a free-memory window or the owner's decision to relax the gate).

## 5. Independent review

Separate subagent, read only. Verdict **NO-GO for 17B**, agreeing with this report; no blocker in the tooling. Findings and handling: (High) runbook paths unquoted although the checkout path contains a space: fixed, every path quoted and a warning added; (Medium) `.env.worker` TEST_* lines dropped: fixed with a test; rollback overwrote the current `.env`/`.env.worker`: now kept as `.rolled-back`, a second rollback is refused; interrupt (Ctrl+C) and partially written new files in the undo: fixed; claims without evidence file (permissions, `pre_0004` hash, RAM figure, dry-run listing, names counts): corrected in the text above; stale `checklist-go-nogo.md` (64 checks, gate G without `--strip-legacy`, Compose `!reset` support, `.env.test`): updated; (Low) `$OUTSIDE` undefined in the restore script: fixed. Accepted or open: the backup script's `icacls` call does not work (to correct before reuse); the leftover `/tmp` dump on a failure between dump and removal (the 17B procedure checks it); `chmod 0600` has no effect on Windows so new env files and `.pre-17b` copies get inherited ACLs (git- and docker-ignored by `.env.*`; the `.pre-17b` copies hold the exposed password until the acceptance step destroys them); after a rollback `POSTGRES_PASSWORD` in the restored `.env` is the old value until rotated.

## 6. Checklist A to M

`group-17c/checklist-status.md`: green A2, B2, C, D, E, F (with a risk), F2, G (with a finding), H, I (on paper), J; **blocked** B (restore) and K (memory); open for the owner A, H2, J2, L, M; F3 (the image builds) belongs to 17B.1.

## 7. Open risks

1. The restore proof of the new backup (blocked by memory).
2. The development worker runs the branch code of 2026-11-13 11:30 UTC (it was recreated after the Docker restart and mounts `backend/app`): its **next restart, or a restart of Docker or the machine, loads the current code, which refuses the administrator URL, and with `restart: unless-stopped` it crash-loops** until 17B, or until the previous stack is started with `compose.rollback.override.yml`. Nothing was changed.
3. The real `.env` carries the administrator credentials (`POSTGRES_*`, `TEST_DATABASE_URL`) until `--strip-legacy` runs in 17B.
4. Branch protection and required checks are not available on this private repository's plan (the API answers 403): the `privileges` job cannot be made binding; a procedural rule only (`ci-remote-proposal.md`, TD-045).
5. The preflight tool had a SQL error in one query (found by running it on the real database, harmless, read only); fixed, and the tool now fails loudly on any query error. The replica of 17A did not catch it because it did not check that line; the replica was not rerun because of the memory gate, so the fixed query is proved only on the real database (read only).
6. Everything listed as residual risk in `group-17a/checklist-go-nogo.md` (the downtime of 2 to 3 minutes, the old stack from the old images, ACL representation, one application database per cluster, `PUBLIC` closing, the `.pre-17b` copies, the reconstructed rehearsal, GitHub Actions never run).

## 8. State of the services

`asistenteia-db-1` healthy at revision 0005, `asistenteia-worker-1` healthy (0 restarts), `asistenteia-postgres` running, `asistenteia-backend-1` exited since 2026-11-12 as before. The deterministic read-only snapshot of the development stack is identical to the one of 17A (31 lines, no drift, 0 rows). No container, network or image tag of this preflight is left; the dump file inside the container was removed.

## 9. Local commits

Listed in the final answer.

## 10. Recommendation

**NO-GO for executing 17B today**, because gates B (restore of the new backup) and K (memory) are not green and A, L, M need the owner. It becomes GO when: (a) `run_17c_restore.sh` passes (restore `IDENTICAL`), (b) 8 GB are free, (c) the owner authorises 17B and accepts the risks in writing, and (d) the independent review below has no open High finding.
