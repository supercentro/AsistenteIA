# TD-038: readiness of the rotation of the administrator password (read-only verification, 2026-11-14)

Verified only by reading the procedure (`group-17a/credentials-and-services-map.md` section 4) and the rehearsal evidence (`group-17a/g17a-replica-output.txt`, check 5). **No password was created, read, printed or changed; no real file was opened for this.** The rotation is step 17B.6: it comes after the owner accepts 17B.5, it is not part of S20 to S31 and it is not authorised.

## What is ready

| Element | State |
|---|---|
| Secure generation of the new value | procedure written: a value of letters, digits, `-` and `_` (what `secrets.token_urlsafe` produces, so it needs no URL quoting) written straight to a file outside the repository; never on a command line |
| Change of the role | rehearsed form: `ALTER ROLE` fed on standard input (`printf` builtin) into `psql` inside the database container; step 2 is the point of no return |
| Files that hold the value | `.env.db`, `.env.roles`, `.env.test` (after `--strip-legacy` the `TEST_*` URLs live in `.env.test`); `.env` and `.env.worker` no longer do (the tool refuses otherwise); the `*.pre-17b` copies hold the old value until destroyed |
| Recreation of the database container | `docker compose up -d --no-deps --force-recreate db` (the volume is untouched); rehearsed 8.5 s; API and worker reconnect |
| Validation | rehearsed: old password refused over TCP, new accepted over TCP, `bootstrap` again exits 0, no file of the environment holds the old value, a later rollback restores the rotated value, not the exposed one |
| Recovery | written for the three cases: `ALTER ROLE` failed (nothing changed, retry); `ALTER ROLE` done but a file still old (write the new value by hand, recreate `db`); never run `prepare_env_files.py --rollback` in that state |

## State after the tools (2026-11-14, second pass): READY TO REHEARSE, NOT AUTHORISED TO RUN

| Gap found in the first pass | Now |
|---|---|
| 1. no tested tool for the edit of the three files | `group-17b/rotation/rotate_admin_password.py` (plan, apply, verify, rollback, cleanup); 62 checks and 7 mutations; atomic per file, originals kept owner-only, all-or-nothing with byte-for-byte restore, names only |
| 2. no copy-paste validation, password on a command line | `rotate_db_role.py`: the SQL goes on standard input as a SCRAM verifier computed client-side, the network checks pass the password through the environment of the client from another container; proven on a disposable PostgreSQL that no argument, output or log holds a secret (37 checks, 5 mutations) |
| 3. password file not created / protection not written | the owner creates it (commands in `rotation/README-17b6.md`); the tools refuse a file inside a Git repository, a link, several lines or a weak format; still an OWNER action |
| 4. `.env.test` | decided: it needs a superuser of the test cluster (`rotation/env-test-decision.md`); it is rotated with the other two files; a separate throw-away test cluster is the proposal to take it out of the rotation (needs approval, not part of 17B.2) |
| 5. destroy the `*.pre-17b` copies | **NO-GO to run it for now (`recovery-matrix.md`)**; the tool exists: exact names only, after `verify` is clean, refuses links and directories, keeps copies that do not hold the old value, overwrites then deletes; tested with decoys |

Remaining before 17B.6 can be authorised: the owner's `<NEWFILE>` and password-manager entry; the owner's approval of the procedure in `rotation/README-17b6.md`; an independent review of the two tools; and the 17B.5 acceptance. The rotation has NOT been run on the real database and no real password was read, created or changed.
