# TD-049: policy and manifests applied to the existing backups (2026-11-14)

Owner-authorised operations on the two existing backup folders only: (A) folder ACL policy, (B) replacement of the two legacy `.sha256` of the 17b dump. No new backup, no dump touched, no PostgreSQL/service/`.env` change, 17B not executed. Evidence: `group-17c/td049-real-folders-evidence.txt` (sanitized), `group-17c/tools/g17c-td049-migration-selftest.txt`.

- **Protection**: rollback folder outside the repository (legacy `.sha256` copies, SDDL export of both folders and children, inventory with hashes, ACL listings).
- **A**: `secure_folder_acl.ps1` applied and re-verified on both folders; probe (create, restrict, read, delete through the folder right) passed; inventory unchanged afterwards.
- **B**: `migrate_legacy_sha256.py` (stage and verify first, replace, verify in place, restrict, roll back every folder on failure). New per-copy `.sha256` (2 relative lines) and `<dump>.integrity.txt`; the legacy `<dump>.manifest.txt` stays untouched. `backup_manifest.py verify` OK per folder, `sha256sum -c` OK, negatives (other folder's manifest, missing manifest, absolute path) fail.
- **Hashes** of the four dumps equal before and after; the only file changes are 2 added and 2 replaced.
- **Tests**: `test_td049_migration.py` 0 failures (suffix option, success, rollback at 5 injection points for each folder, preconditions, descriptor export/compare/restore); mutation (rollback does not restore) fails 7 checks; manifest 29/29, folder ACL 18/18.
- **Independent review** (clean context, read only): PASS, no blocker or major. Minor findings: restoring the second folder's descriptor direction untested (added a check for the second folder's `.sha256`), stray table pipe in the checklist (fixed), manual rollback order documented in `backup-and-recovery.md`, rollback `remove()` unguarded (accepted: low).
- **Side effect noted**: files in those folders that inherit from the folder (the pre_0005 manifest and its `.sha256`) now inherit the new rules (user Modify instead of Full); content unchanged.
