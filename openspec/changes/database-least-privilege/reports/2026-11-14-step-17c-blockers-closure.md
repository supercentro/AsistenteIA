# Group 17C: closing the blockers B and K of the final preflight (2026-11-14)

Branch `feature/database-least-privilege`, start at `cb45726`. Authorised scope: resolve the checklist blockers B (restore proof of the new backup) and K (memory threshold) and correct the Windows ACL handling of the backup tool. **17B was not executed**; nothing was changed in the development PostgreSQL, the roles, the credentials, the real env files or the running services (no start, stop, restart or rebuild; no `docker compose up`). The only contacts with the real stack were read-only sessions for the dev snapshot and `docker inspect`.

## 1. Why `icacls` did not apply the permissions

`run_17c_backup.sh` built the command inside a double-quoted PowerShell string: `"$env:USERNAME:(R)"`. PowerShell reads the colon after `USERNAME` as part of a scoped variable name, the variable expands to nothing and the argument becomes `(R)`; `icacls` answers `Invalid parameter "(R)"` and exits 1 without changing anything, and the script sent that output to `/dev/null`. Reproduced on a throw-away file with the errors visible (`${env:USERNAME}` with braces does expand). The dumps therefore kept their inherited ACLs (SYSTEM, Administrators, the owner with full control) until they were fixed by hand in the previous session.

Two more facts found while fixing it: Windows stores an Allow Read rule as `Read | Synchronize` (0x120089), so a verification against `FileSystemRights.Read` alone fails; and `Set-Acl` of Windows PowerShell 5.1 fails with `PrivilegeNotHeldException` (it also touches the SACL) once a file grants only Read, while `[System.IO.File]::SetAccessControl` persists only the modified DACL.

## 2. Correction and tests

- New tool `group-17c/tools/secure_file_acl.ps1` (`-Path <file> [-VerifyOnly]`): uses the .NET ACL API, no string building; disables inheritance without copying the inherited rules, removes every rule, sets the owner only when it differs (changing it needs a privilege), adds one rule (current user by SID, Allow, Read), writes with `File.SetAccessControl`, then **re-reads the descriptor** and requires: protection on, exactly one rule, not inherited, the current user's SID, Allow, exactly `Read|Synchronize`, owner = current user. Any deviation is `ACL FAIL` exit 1; a missing or non-regular file is exit 2 (fail closed). It prints only the file name and the exception type, never the folder or the message.
- `group-17c/tools/test_secure_file_acl.py`: **13 of 13** (`g17c-acl-selftest.txt`): fresh file inherits several rules; apply reports OK and an independent `Get-Acl` reading shows protection, one rule, the current SID and `Read|Synchronize`; the owner itself cannot write the file afterwards (effective permission) but can read it; verify-only passes; a rule for Everyone added behind the tool's back makes verify-only fail with exit 1 and is removed by a new apply; inheritance re-enabled behind its back fails verify-only; missing file exit 2 and not created; directory refused; no path in the output. Mutation checks: with the inheritance check removed, 1 test fails; with the rule-count check relaxed, 1 test fails.
- `run_17c_backup.sh` now calls the tool on the six files (dump, `.sha256`, manifest, both copies) and counts the `ACL OK` lines as a check (expected 6); the dump in the container's `/tmp` is removed in the cleanup trap too (also on a failure); the `asistenteia_test` snapshot runs with the read-only guard. `backup-and-recovery.md` replaces `chmod 600` by the tool; TD-049 records the remaining gap (the env files the tooling creates get inherited ACLs; Administrators can still take ownership).
- `ruff`/`mypy`: `mypy --strict` clean on the new test; the report tools are outside the backend `ruff` scope and show the same style findings (line length, subprocess) as the existing 17A tools.

## 3. Effective ACLs of the backups

`group-17c/evidence/backup-acl-verify.txt`: `secure_file_acl.ps1 -VerifyOnly` on the six real files, all `ACL OK … verified; inheritance disabled; 1 rule: current user, Allow, Read; owner: current user`. The files were not rewritten (verify only): the hand fix of the previous session already produced the expected descriptor, now proven by the tool instead of asserted. The older backups were not touched.

## 4. Memory before the restore

The threshold of 8 GB was enforced by the script, not by hand: free RAM was 7.09 GB at the preflight and 7.3 GB during the ACL work; the restore script waited (no service was stopped to free memory) and started when it measured **8.34 GB** free (`g17c-restore-output.txt`). After the run: 8.28 GB free.

## 5. Hash and integrity of the backup

`asistenteia_pre_17b_20261114T013150Z.dump`, 17 437 bytes, SHA-256 `d0a2ad6bfc0c392d765473acbaf7bfbec25ff24eea99e2828e3377176d6279d9`: equal to the recorded `.sha256` in both copies at the preflight and re-checked by the restore script before use (check [1]).

## 6. Restore

Disposable cluster `pgvector/pgvector:0.8.7-pg15` (PostgreSQL 15.19), own network, `tmpfs` data directory, no published port, 1 GB memory limit; the second copy restored with `pg_restore --exit-on-error`: **rc 0 in 250 ms**. Revision `0005`; extensions `vector 0.8.7` and `plpgsql` present. Cleanup: 0 containers, 0 networks left; the image stays.

## 7. Source versus copy

`compare_snapshots.sh` on the catalog snapshots: the restored copy is **IDENTICAL to the source on 118 compared lines** (revision, schema, 7 tables with owner `asistente` and default ACLs, columns, constraints, defaults, enum types, indexes, sequences, extensions, row counts: `alembic_version` 1, every other table 0) and **IDENTICAL to the expected 0005 baseline** of 17A. Data readability: every table was read by the counting queries; the content is the single `alembic_version` row (the development database holds no business rows). No unexplained difference. Evidence: `evidence/source-snapshot-db.txt`, `evidence/restored-snapshot-db.txt`.

## 8. No change in development

The deterministic read-only snapshot of the development stack after 17C is identical to the one taken before 17A (31 lines): revision 0005, no drift, 0 rows. `asistenteia-db-1` and `asistenteia-worker-1` healthy, worker 0 restarts, `asistenteia-backend-1` exited as before; no dump left in the container's `/tmp`; no g17 container or network.

## 9. Independent review

Clean-context subagent, read only (git, `docker ps/inspect`, read-only psql, `Get-Acl`, `sha256sum`, the synthetic self-test). Verdict: **the 17C closure is technically sound; blockers B and K are closed with reproducible evidence; GO for 17B from its side, conditional on the owner gates and on recording its findings.** It confirmed: hashes and manifest (no data) in both copies, `pre_0005` untouched, file mtimes unchanged by verify-only; the six descriptors exactly as reported; source vs restored IDENTICAL (118 lines) and restored vs expected IDENTICAL, with `compare_snapshots.sh` comparing what §7 lists; development unchanged by its own fresh read-only snapshot (IDENTICAL, revision 0005, services healthy, `/tmp` empty, no g17c resources); the RAM gate enforced before `docker run` and the 8.34 GB recorded; 13/13 self-test; the scripts cannot write the real database. Not confirmed by it: the mutation checks (now logged in `g17c-acl-selftest.txt`, three mutations each failing one test), the 31-line dev comparison, the ruff/mypy statement.

Findings and handling:
- (Medium) the `.sha256` files written by the backup run hold ` *<absolute path>` (Git Bash `sha256sum` output; the `sed` for two spaces never matched), so they carry the user's folder and the second copy's file points at the first folder. Script fixed (hash + file name, plus a check); **the two existing `.sha256` files were left as they are** (the authorisation does not cover rewriting files in the backup folders; they are read-only and outside the repository). Recorded in TD-049 for the owner to decide.
- (Medium) the backup folders keep inherited Full Control for SYSTEM and Administrators: an administrator can delete or replace a backup through the folder regardless of the file ACL. Added to TD-049; the tool deliberately secures files, not folders.
- (Medium) the edited `run_17c_backup.sh` (ACL loop and check, cleanup `rm`, read-only guard, `.sha256` format) has not run end to end: running it again would create a new real backup, which was not authorised, and the script refuses while a 17b backup exists. The recorded output is that of the first version. The standalone tool is tested; the script edits are syntax-checked only. To be run on the day of 17B (its backup step) or when the owner authorises a new backup.
- (Low) provenance: `evidence/source-identity.txt` and `source-activity.txt` come from the preflight re-run at 02:14 UTC (after the preflight tool fix), while the dump was taken at 01:31 UTC; the restore script compared the copy with the dump-time snapshot kept in the temp folder (identical content, 118 lines) and the catalog has no volatile part, so the two sources agree. Said here instead of implied.
- (Low) the tool now refuses a reparse point (symbolic link or junction) with exit 2; the weak assertion `"2" in out` of the test is now `found 2` and `another identity`.
- (Low) what `snapshot_db.sql` does not compare: sequence values, function and trigger bodies (counted only), views, RLS policies, comments, row content beyond counts. Immaterial today (one row, no sequences or functions), material once data exists: noted in `backup-and-recovery.md` for a future backup of a populated database.

## 10. Checklist

`group-17c/checklist-status.md` updated: B and K green; the owner's gates A, H2, J2, L, M still open; F3 belongs to 17B.1.

## 11. Recommendation

The two technical blockers are closed. GO for 17B now depends only on the owner: the explicit authorisation (A, M), the acceptance of the residual risks (L, including the worker crash-loop risk on its next restart, the legacy variables in the real `.env`, and the advisory-only CI gate), the window (K at the time of the run: the worker image build needs the 8 GB again), and a clean independent review of this closure.
