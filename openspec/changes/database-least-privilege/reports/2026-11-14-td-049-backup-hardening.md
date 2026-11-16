# TD-049: hardening and verification of the backup procedure (2026-11-14)

Branch `feature/database-least-privilege`, start at `85fd6ea`. Scope: only the backup procedure related to TD-049. **No real backup was generated, no real backup folder or file was modified, 17B was not executed**; PostgreSQL development, roles, credentials, `.env` files and services were not touched (read-only inspection only).

## 1. State of TD-049

Tooling and procedure: **resolved and tested**. Still open, by design: (a) applying the folder policy to the real backup folders, (b) rewriting the two existing `.sha256` files (they carry ` *<absolute path>`), both need the owner's separate authorisation. Recorded in `docs/technical-debt.md`.

## 2. Corrections

- `tools/backup_manifest.py` (`write` / `verify`): one `.sha256` and one manifest **per copy**. The `.sha256` has exactly two lines in `sha256sum` format (the dump and its manifest, file names only), so `sha256sum -c` works inside each folder and cannot point at another one. The manifest has a version, the copy label, file name, size, sha256, UTC time and metadata. Refuses (and never echoes) any value with a path separator or the user name; never overwrites; `verify` fails closed on: dump byte flipped or truncated, size mismatch, name of another file, absolute path in the `.sha256`, lost line, missing file, manifest edited (even with its hash recomputed: the copy label and the dump hash still disagree), manifest taken from the other folder.
- `tools/secure_folder_acl.ps1`: the minimal folder policy (section 4).
- `run_17c_backup.sh` rewritten: gates are `require` (fail closed), every file created by the run is tracked and **removed by the EXIT trap unless the whole set was verified**, SIGINT/SIGTERM handled, refuses an existing 17b backup in either folder, verifies the integrity of the pre-existing backups, the folder policy verdict is reported, per-copy manifests are verified before the restore, the manifest tool's error text is withheld from the log (it can hold a path), `MSYS` paths are converted for `python.exe`. Test hooks are refused against the real source container.
- `preflight_readonly.sh`: the `.State.Health` template failed on a container without healthcheck (found by the synthetic rehearsal; the real container was never affected); fixed with `index .State "Health"` and the tool now stops on a failed `docker inspect`.

## 3. Tests and mutations

| Suite | Result |
|---|---|
| `test_backup_manifest.py` | 29 of 29; 5 mutations (dump-hash, copy-label, path guard, size, manifest-hash checks disabled one at a time) each fail 1 to 2 tests (`g17c-manifest-selftest.txt`) |
| `test_secure_folder_acl.py` | 18 of 18 |
| `test_secure_file_acl.py` | 13 of 13 (3 mutations, previous phase) |
| `test_prepare_env_files.py` | 80 of 80 |
| synthetic end to end | 40 of 40; mutation (trap removal disabled) gives 7 failures (raw output kept) |

## 4. Effective ACL of the folders and the recommended policy

Read-only inspection of the real folders (identities generic): the primary backup folder has inheritance disabled and three explicit rules (SYSTEM Full, Administrators Full, current user Full), all with inheritance to children; the second folder and the parent `Backups` inherit the same three from the profile. The profile itself adds a sandbox package SID with execute rights only to its root. Legitimate: SYSTEM (operating system, VSS/AV), Administrators (recovery), the owner. The real folders already hold exactly these three identities (no Everyone, Users or Authenticated Users), so **there is no unauthorized identity to remove today**; the policy is hardening against accidents and drift (inheritance from the profile, Full Control for the owner), not a barrier against the owner's own account: as owner, any process running as that user keeps the implicit right to rewrite the ACL and delete a backup.

Recommended policy, implemented in `secure_folder_acl.ps1` (`-VerifyOnly` supported): inheritance off; SYSTEM Full; Administrators Full (kept, as instructed); current user Modify + DeleteSubdirectoriesAndFiles (create, read, verify and delete a copy even after the file was restricted to Read); owner = current user; nothing else. Tested on a synthetic folder: the lifecycle create, restrict, read, verify, and delete a copy through the folder right works; a restricted copy cannot be overwritten; Everyone added behind the tool's back, Full Control for the user and re-enabled inheritance are all detected (exit 1). **Applying it to the real folders was not done** (not authorised); the command is in `backup-and-recovery.md`. Known limit: an administrator can still delete or replace a backup (operating system).

## 5. Integral validation

`run_17c_synthetic_e2e.sh`: a disposable PostgreSQL 15.19 + pgvector 0.8.7 whose catalog is the real 0005 one (restored from the existing second copy, a read) acts as source, with synthetic folders under the policy and an older backup in the old format. Run 1 (happy path, 19 of 19): preflight, dump, two copies, independent manifests, `sha256sum -c`, six file ACLs, restore, equivalence, no path or user name in the files or the log, dump removed from the source, older backup untouched. Run 2 (corrupted copy), 3 (corrupted manifest), 4 (simulated Ctrl+C): non-zero exit, **no file of the run left**, trap message, no container or network left, older backup untouched. Run 5 (a 17b backup already present): refused with exit 3, folders unchanged. Cleanup: 0 containers, 0 networks, root removed. Defects found and fixed by the rehearsal: the health template, MSYS paths for `python.exe` (which also leaked the user name into a log line), and the rehearsal's own folder collision. `e2e-inner-outputs/` keeps the inner logs.

## 6. Independent review (clean context, read only)

Verdict: the tooling and procedure are sound and tested; TD-049's technical part can be closed once the points below are handled. Confirmed by the reviewer: the real folder ACLs match section 4; the verification of both ACL tools fails closed; `verify` rejects trailing spaces, names with spaces, absolute paths, relabelled and cross-folder manifests; `VERIFIED=1` is set after manifests, ACLs and the post-dump snapshot; the real 17b dumps still hash to the recorded value with their mtimes unchanged; nothing in the scripts can write to the real PostgreSQL (read-only sessions, `pg_dump`, one `rm` of the script's own `/tmp` file); the new files contain no user name. Findings and handling:
- (Medium) the e2e did not show the trap removing files that are already Read-only for their owner (the hooks fired before the ACL step). **Fixed**: new hook `acl_done` (exit after the six ACLs) and run 4b; the e2e is now **40 of 40**, with the six `ACL OK` lines present in the inner log before the failure and no file left afterwards. The mutation of the trap (removal disabled) now has its raw output kept (`g17c-synthetic-e2e-output-MUTATED-trap-removal-disabled.txt`: 33 of 40, 7 failures).
- (Medium) the policy is accident hardening (section 4 reworded above).
- (Medium) the folder policy was only a log line in the backup script. **Changed**: `G17C_REQUIRE_FOLDER_POLICY=1` turns it into a stop (the synthetic e2e sets it); left as a warning by default because the real folders do not carry the policy yet and applying it needs the owner's authorisation.
- (Medium) `verify` has no external anchor: someone who can rewrite the dump, the manifest and the `.sha256` consistently passes it, and it does not compare the two copies with each other. It is an accident and drift check; the anchor is the SHA-256 recorded in the committed run log and in the report, which a restore must be compared with. Documented, not changed.
- (Low, fixed) the trap no longer removes `/tmp/asistenteia_pre_17b.dump` in the source container unless this run created it, and the run stops if such a file already exists there.
- (Low, accepted) a second Ctrl+C during the cleanup can leave files; the interrupt test is a signal sent by the script, not a terminal Ctrl+C; hooks are refused only against the default source name; the baseline check compares the first `.sha256` line; `backup_manifest.py` does not forbid `:` in a dump name (not attacker-controlled here); `Set-Acl`-free `SetAccessControl` works on Windows PowerShell 5.1 only (the scripts call `powershell`); `datetime.UTC` needs Python 3.11+; the user name appears in two older tracked evidence files (`group-12/windows-unit-full.txt`, `group-17a/g17a-replica-output-run1-superseded.txt`), not in anything new.
- Not confirmed by the reviewer: behaviour on a terminal Ctrl+C or in the middle of `docker cp`; restoring from the second copy through the new script outside the synthetic setting.
