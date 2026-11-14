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

## What is missing for a SAFE rotation (so: NOT READY, "NO-GO" for 17B.6 as it stands)

1. **No tested tool for step 3.** The three files are edited by hand. A typing mistake in a URL would break `bootstrap` or the host tests, and an editor shows the value. Needed: a small tool (stdlib, names and verdicts only, atomic, with a rollback copy and tests on synthetic files, like `prepare_env_files.py`) that reads the new value from the file, replaces the old one in the three files and checks that the old value no longer appears. It does not exist yet.
2. **The validation of step 5 has no copy-paste commands.** The rehearsal ran it with the password on the command line of a throw-away container (`-e PGPASSWORD=<value>`), which must not be copied to the real run. The real form has to pass the value through the environment of the invoking shell without writing it on the command line (`PGPASSWORD="$(cat <NEWFILE>)" docker run --rm --network asistenteia_default -e PGPASSWORD pgvector/pgvector:0.8.7-pg15 psql -h db -U asistente -d postgres -Atc 'select 1'`, and the old value read from `.env.db.pre-17b` the same way). Two traps to write down: inside the database container the loopback address is trusted by `pg_hba`, so a TCP check from inside it proves nothing; and the check must not print the value.
3. **The password file does not exist and its protection is not written.** The owner must create `<NEWFILE>` outside the repository and its password-manager entry before the window, and restrict it to the owner (`secure_file_acl.ps1 -Rights Modify` works on any file). The operator must not create it.
4. **Open owner decision:** whether `.env.test` will hold the administrator URL (the real `.env` carried `TEST_DATABASE_URL` with it, so yes unless the host tests are changed); it must then follow the rotation.
5. **Destroying the `*.pre-17b` copies** is described but has no command or check that they are gone (and that no other copy of the old value remains in the repository folder).

## Consequence

17B.2 (S20 to S31) does not depend on any of this, and TD-038 stays an accepted risk of class A until 17B.6 (see the risk table of `17b2-authorisation-checklist.md`). The exposed value stays valid for as long as the rotation is not done. Closing items 1 to 3 and 5 is a documentation-and-tool task (about the size of `prepare_env_files.py` for the tool) that needs the owner's authorisation; item 3 and item 4 are the owner's.
