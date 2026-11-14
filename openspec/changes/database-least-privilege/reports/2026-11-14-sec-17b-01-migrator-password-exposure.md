# SEC-17B-01: exposure of the `asistente_migrator` password in a tool traceback (2026-11-14)

Sanitized report. No credential, URL, hash or token appears here. Status: **incident open; the real rotation is NOT authorised and was not run**.

## 1. What happened

During the removal of the three synthetic users of 17B.5 (19:19 local, development), an ad hoc script run in a throw-away container of the `asistenteia-migrate` image connected with `psycopg.connect(os.environ["MIGRATION_DATABASE_URL"])`. The variable holds an SQLAlchemy-style URL (`postgresql+psycopg://...`); `psycopg.connect` expects a libpq URL or key/value string and raised `ProgrammingError: missing "=" after "<the whole URL>" in connection info string`. The unhandled traceback printed the full URL, **including the password of `asistente_migrator`**, in the tool output of the Claude Code session. The operation did not change any data (the connection never opened). The retry used a corrected URL, caught exceptions (printing the exception type only) and piped all output through a redaction filter.

## 2. Root cause

1. A one-off script was written without exception handling around the connection (psycopg messages echo the input string).
2. The URL dialect prefix was not normalised for the raw driver (the application code goes through SQLAlchemy, which accepts `+psycopg`).
3. The redaction filter on tool output was added only after the first failure; the first run printed unfiltered output.
4. The repository tools (`rotate_*`, orchestrator) already avoid tracebacks and redact; the ad hoc script was outside them.

Corrective practice (adopted for the rest of the intervention): scripts that open connections catch the exception and print `type(e).__name__` only; every command that can echo a URL is piped through `sed -E 's#(postgres[a-z+]*://)[^ ]+#\1<redacted>#g'`; connection strings are never interpolated into messages.

## 3. Scope of the exposure (found by value scan; only paths and counts were printed)

| Place | Holds the value | Note |
|---|---|---|
| `backend/.env.migrate` (git-ignored) | yes | `MIGRATION_DATABASE_URL`, expected |
| `backend/.env.roles` (git-ignored) | yes | `DB_MIGRATOR_PASSWORD`, expected |
| Claude Code session transcript (one local `.jsonl` file under the user profile) | **yes** | the incident itself; the text was also part of the conversation processed by the model service |
| Other live env files (`.env`, `.env.worker`, `.env.db`, `.env.cli`, `.env.test`) | no | |
| `*.pre-17b` copies | no | they predate the roles (created by S21 before the role passwords existed in any file) |
| Git history and the remote branch | no | the files are git-ignored and no commit was made after S21; HEAD `c789ed0` is the commit published before the intervention |
| Orchestrator state folder and logs (91 files) | no | |
| Both PostgreSQL backup folders (dumps and manifests) | no | `pg_dump` of one database does not carry role passwords |
| Claude scratch folders (temp) | no | |
| Containers (15) and images (30), including `docker history` | no | one-shot containers were removed; env files are read at run time |
| PostgreSQL server | only the SCRAM-SHA-256 verifier | not the password |

Reachability of the credential: the database publishes only `127.0.0.1:5442` (loopback) and the Docker network; the role is not a superuser, `CREATEROLE`, `CREATEDB`, `REPLICATION` or `BYPASSRLS`, has a connection limit of 5, and owns the nine application objects (it can change the schema and read all data of the development database). The data of the environment is empty (0/0/0/0/0/0). The exposure is therefore a **credential compromise in a development environment with local-only reachability**, treated as compromised until rotated.

## 4. Consumers and dependants (found by name, not by value)

| Consumer | How it uses the credential | Needs an update when it rotates |
|---|---|---|
| `backend/.env.migrate` | `MIGRATION_DATABASE_URL` for `db-migrate`, `db-grants`, `db-verify`, the `migrate` service and Alembic | yes |
| `backend/.env.roles` | `DB_MIGRATOR_PASSWORD` read by `db-bootstrap` (it sets role passwords from it) and `db-verify` | yes |
| `db-bootstrap` | **re-applies `DB_MIGRATOR_PASSWORD` to the role every time it runs**: if it runs between the database change and the file change, it silently reverts the password | order of the procedure (section 6) |
| Orchestrator stages S22, S25, S26 | run the above commands with those two files | all done; the orchestrator keeps no copy |
| Backend and worker | do **not** use it (their URLs name `asistente_app` and `asistente_worker`; 0 migrator variables in either container) | no recreation |
| CI (`.github/scripts/privilege_gate.sh`) | uses its own synthetic passwords generated per run | no |
| Backups of configuration | none hold it | no |

## 5. Rotation tool: reuse and adaptation

`rotate_db_role.py` (SQL step, probes) is already role-generic: `alter --role asistente_migrator` sends a client-side SCRAM verifier on standard input; the probe needs `--database asistenteia` because the databases are closed to PUBLIC and the migrator only connects to the application database. **No change was needed.**

`rotate_admin_password.py` is not reusable as is: its files (`.env.db`, `.env.roles` `ADMIN_DATABASE_URL`, `.env.test`), its old-value source (`POSTGRES_PASSWORD`) and its temporary-file pattern are specific to the administrator. A new `rotate_role_password.py` (profile `migrator`) imports its checks and its atomic write pattern and differs in: the files (`.env.roles` variable `DB_MIGRATOR_PASSWORD`, `.env.migrate` URL variables whose user is `asistente_migrator`), the old-value source (`DB_MIGRATOR_PASSWORD`, which must agree with the URL), the orphan pattern, and a `discard` command that removes only the two `*.old` backup copies (never `*.pre-17b`). Commands: `plan`, `apply`, `verify`, `rollback`, `discard`.

Tests (all on synthetic folders and a disposable PostgreSQL; nothing real was touched): `test_rotate_role_password.py` 54 checks; `test_rotate_role_password_mutations.sh` 13 of 13 mutations caught (the first version of the suite let 3 survive and the review added 4 more; tests were added and re-run); `test_migrator_rotation_e2e.sh` 37 checks (accept/reject over the network, partial failure with both recoveries, no secret in any docker argument or output, the administrator unaffected, refusals). Evidence: `rotation/g17b-migrator-rotation-*.txt`. An independent review is recorded in section 8.

## 6. Procedure for the real rotation (PROPOSED; requires a separate, explicit authorisation)

Owner, before the window: create the new-password file outside the repository (48 characters from `secrets.token_urlsafe(36)`, value never shown), restrict it with `secure_file_acl.ps1 -Rights Modify`, store it in the password manager. The operator receives only the path. `ROT_TEST_HOOKS` and `ROT_DOCKER_CMD` must not be set. Nothing may run `db-bootstrap` or an orchestrator stage while the procedure runs.

Rules added by the two reviews: before anything, `ROT_TEST_NO_ACL`, `ROT_TEST_FAIL_AT`, `ROT_TEST_HOOKS` and `ROT_DOCKER_CMD` must be unset in the shell (`Remove-Item Env:NAME` or check that they are empty); no `docker compose up`, `run` or `start` and no host reboot between steps 4 and 5 (compose runs `bootstrap` as a dependency of `migrate` and `bootstrap` re-sets the role passwords from `.env.roles`); `--acl-script` is mandatory on Windows; the new-password file is created without BOM; `alter` (step 4) always runs before `apply` (step 5); step 9 runs only after the probes of step 6 and the owner's acceptance; `rollback` is used only with the backup folder of the current run.

| # | Command (paths abbreviated; Windows paths for `python`) | Expected | If it fails |
|---|---|---|---|
| 0a | pre-flight of the part that comes AFTER the point of no return: `secure_file_acl.ps1 -VerifyOnly` accepts the new-password file; `<BACKUP>` does not exist or is empty and lies outside the repository and the backend folder; the quoting of `DB_MIGRATOR_PASSWORD` in `.env.roles` is known (the scan strips one pair of matching quotes; check the flag, not the value) | all true | fix before step 1; nothing changed |
| 0b | `check_containers_for_value.py <backend>`: no container (running, exited or created) carries the old value; names and counts only. Exited compose `bootstrap` and `migrate` containers (`restart: "no"`, no `--rm`) ARE expected to be listed: `docker rm` them by exact name. The scan covers container configuration (raw, percent-encoded and JSON-escaped forms); it does not cover `docker logs` or image layers: the value is dead after step 4, so this is hygiene | `holding the value: 0` after the removals | remove the named containers; services are not touched |
| 1 | `rotate_role_password.py plan <backend> --new-file <NEW>` | `PLAN OK: nothing written` | fix the cause; nothing changed |
| 2 | `rotate_db_role.py check --container asistenteia-db-1` | `password_encryption=scram-sha-256` | stop |
| 3 | `rotate_db_role.py probe --network asistenteia_default --host db --role asistente_migrator --database asistenteia --from-env-file <backend>/.env.roles --var DB_MIGRATOR_PASSWORD --expect accept` | current password accepted | stop |
| 4 | `rotate_db_role.py alter --container asistenteia-db-1 --role asistente_migrator --password-file <NEW>` | `ALTER ROLE OK` (point of no return) | exit 3: run the probe of step 3 before retrying |
| 5 | `rotate_role_password.py apply <backend> --new-file <NEW> --backup-dir <BACKUP> --acl-script <ACL>` | `APPLY OK`; `.env.roles` and `.env.migrate` updated atomically | the tool restores by itself; then recovery A or B |
| 6 | probes: new password from `<NEW>` accepted; old from `<BACKUP>/.env.roles.old --var DB_MIGRATOR_PASSWORD` rejected | accepted / rejected | recovery A |
| 7 | `db-verify` as in S26 (`docker run --rm ... --env-file .env.migrate --env-file .env.roles ... db-verify`, output piped through the URL redaction filter) | `no findings` and exit 0 | recovery A; read the log without URLs |
| 8 | `rotate_role_password.py verify <backend> --new-file <NEW> --old-from <BACKUP>/.env.roles.old` | `VERIFY OK` | fix the file it names |
| 9 | after the owner accepts: `rotate_role_password.py discard ... --dry-run`, then without it | the two `*.old` copies removed; `*.pre-17b` untouched | read what it kept |
| 10 | record the result in `docs/technical-debt.md` and close SEC-17B-01 | | |

Backend and worker are not touched and not restarted; the database container is not recreated (the role password lives in the data directory). The orchestrator state is not modified.

## 7. Recovery

| Where it fails | Recovery |
|---|---|
| steps 1 to 3 | nothing changed |
| step 4 exits 3 | probe with the current password; if accepted, nothing changed |
| step 5 (files failed, database has the new password) | the tool restores the files; **A, revert**: `alter --from-env-file <BACKUP>/.env.roles.old --var DB_MIGRATOR_PASSWORD` then probes (old accepted, new rejected); or **B, forward**: apply again with a NEW empty backup folder |
| the process was killed (also a second Ctrl+C during the restore) | `rotate_role_password.py rollback <backend> --backup-dir <BACKUP>` (restores both files byte for byte, removes orphan temporaries; running it twice is safe), then A or B according to the probe of step 3. After any failed or rolled-back `apply` the two `*.old` copies hold the STILL-LIVE old value and `discard` refuses (the live files hold it too): delete them by exact name by hand once the rotation is done or abandoned |
| step 7 finds drift | recovery A; the rotation does not change grants, ownership or schema, so a finding would come from something else: stop and report |
| someone ran `db-bootstrap` between 4 and 5 | it reverted the password to the old file value; probes tell; run step 4 again |

The old password stays valid only until step 4. The two `*.old` copies hold the old (by then dead) value until step 9.

## 8. Independent review

Separate subagent, clean context, read-only; it never read the real env files and used no Docker. About 20 scratch fixtures (CRLF, BOM, duplicate variables, sibling files holding the old value). Verdict: **conditional GO, no blocker**.

| Finding | Handling |
|---|---|
| M1 major: only `Refused`/`OSError` were caught; a non-ASCII URL makes `urlsplit` raise a `ValueError` whose message echoes the netloc (same leak class as the incident) | **Fixed**: `main` catches any `Exception` and prints the exception type only; `apply` no longer re-raises after the rollback. Tests: non-ASCII URL in `plan` and `apply` (no traceback, no echo, nothing changed); mutation caught |
| M2 major: on Windows, without `--acl-script` the temporary files and the backup copies keep inherited ACLs and the tool says nothing | **Fixed**: `apply`, `rollback` and a real `discard` refuse on Windows without `--acl-script` (a test-only variable disables this in the file-level suite; the e2e uses the real script). Test and mutation |
| M3 major (procedure): one-shot containers created before the rotation would carry the old value in `docker inspect` | **Runbook step 0b** below; today 0 of 15 containers hold the value |
| minor 1: `discard` removed the `--old-from` source copy first | **Fixed**: it goes last and stays if another copy is stuck; test with a forced stuck copy and the re-run; mutation |
| minor 2: an interruption between `os.replace` and its bookkeeping left that file rotated while printing "ROLLBACK COMPLETE" | **Fixed**: once the replacement phase starts, every target is restored from its verified backup (idempotent); test through a new `interruptmid1` hook; mutation |
| minor 3: second Ctrl+C or SIGTERM during the restore; leftover `*.old` after a rollback | Accepted and documented: recovery from a hard kill works (`rollback`); after a rollback the operator removes the two `*.old` copies by exact name |
| minor 4: `discard` and `rollback` accept any backup folder; discarding before the database change loses the only revert source | **Runbook**: step 9 only after the probes of step 6 and the owner's acceptance; `rollback` only with the backup folder of the current run |
| minor 5: `plan` reported `*.pre-17b` copies holding the old value only informally | `apply` prints the same note; the expected result today is none |
| minor 6: scanning covers `.env*` files of the backend folder only (not `alembic.ini`, not UTF-16 siblings); variables not ending in `URL` are caught by `holds_old` and refused (safe failure) | Accepted; the repository-wide value scan of section 3 covers the rest and is repeated after the rotation |
| minor 7: `read_new` tolerates a BOM, `rotate_db_role.py` does not | **Runbook**: `alter` runs before `apply` (as in this procedure); the file is created without BOM |
| test quality: refusal tests assert exit codes; interrupts are injected by hook, not by signal; `post_check` failure branches unexercised; CRLF/BOM/duplicate variables untested | Partly addressed (new tests, a no-op line removed); the rest is accepted: `post_check` is the reused, already tested helper of the administrator tool, and `verify_state` re-parses every rotated variable independently |

After the fixes: file-level suite 54 checks, 13 of 13 mutations caught, e2e on a disposable PostgreSQL 37 checks (re-run with the fixed tool). Reviewer's conditions: fix M1 (done), fix M2 (done), add the M3 step and the minor-4 check to the runbook (done in section 6). 
### Second review (clean context, read-only, requested by the owner)

Verdict: **GO, no blocker and no major**, conditional on five runbook amendments (all applied above). It re-ran the suite (54) and the mutations (13 of 13), simulated a hard kill right after the first `os.replace` in a scratch fixture (`verify`, `discard` and `plan` refused; `rollback` restored both files byte for byte, removed the orphan and was idempotent) and confirmed: M1 fixed for the file tool and for `check_containers_for_value.py` (type-only messages); M2 fixed (`require_acl` on `apply`, `rollback` and a real `discard`; the test bypass is cleared by the runbook); M3 fixed with limits (stopped and created containers are covered; logs and image layers are not); the two minors (discard order, interruption window) fixed; no effect on the administrator, API or worker.

| Finding | Handling |
|---|---|
| minor 1: second Ctrl+C or hard kill during `restore()` leaves mixed files | Recoverable with `rollback`; section 7 row extended |
| minor 2: the container scan did not strip quotes and compared the raw value only | **Fixed in code**: one pair of matching quotes is stripped; raw, percent-encoded and JSON-escaped forms are compared; new test (quoted variable) |
| minor 3: step 0b does not cover logs or image layers; exited compose containers do exist | Documented; step 0b now says they are expected |
| minor 4: nothing checks the ACL script or the backup folder before the point of no return | **Runbook step 0a** |
| minor 5: `*.old` copies after a failed apply hold the live old value and `discard` refuses | **Runbook**, section 7 row |
| minor 6: `bootstrap` between steps 4 and 5 reverts the password | **Runbook rule** (no compose commands, no reboot); the probes of step 6 catch it |
| minor 7: the reject probe matches "password authentication failed", which a missing role or an expired `VALID UNTIL` also gives | Accepted: the accept probe of the new password in step 6 covers it |
| tests | The mutation set passes for the right reasons; the kill-between-replaces case is covered by hook injection plus the reviewer's real kill |

## 9. What was NOT done

No `ALTER ROLE`, no change of any real `.env*`, no service restart, no push, no 17B.6, no rotation of the administrator password or `JWT_SECRET`, no clean-up of `*.pre-17b`, no deletion of backups or refs. The session transcript was not edited: it is outside the repository and its removal is the owner's decision.

## 10. Preparation of the next window (NO window is set; the owner chooses it and confirms in a new message)

Closing state of the 2026-11-14 window (read only, 19:56 local): revision 0006; counts 0/0/0/0/0/0; nine objects owned by `asistente_migrator`; PUBLIC without grants; `db-verify` with no findings; one session of `asistente_app` and one of `asistente_worker`; backend HTTP 200, worker healthy, database healthy; both dumps with the registered SHA-256; the three `*.pre-17b` copies byte-identical; orchestrator S10-S13, S20-S26, S30, S31 done, none failed; no `migrate`, `bootstrap` or disposable container present.

**Exact scope of the rotation:** the password of the role `asistente_migrator` in the database, `DB_MIGRATOR_PASSWORD` in `backend/.env.roles` and the user-`asistente_migrator` URL variable(s) of `backend/.env.migrate`. Nothing else: not the administrator password, not `JWT_SECRET`, not the other three roles, not `*.pre-17b`, not the backups, not the orchestrator state.

**Backend and worker are not modified, not restarted, not recreated.** Their URLs name `asistente_app` and `asistente_worker`; the compose services `bootstrap` and `migrate` are the only consumers and they are one-shot.

**Order and stop points** (section 6 is the command table): 0 conditions -> 0a/0b pre-flight (stop on any failure; nothing changed) -> 1 `plan` (stop) -> 2 `check` (stop) -> 3 probe of the CURRENT password (stop) -> **4 `alter` = POINT OF NO RETURN** -> 5 `apply` -> 6 probes (new accepted, old rejected) -> 7 `db-verify` -> 8 `verify` -> owner accepts -> 9 `discard` -> 10 record. Stop and report at any failure; no rollback that writes without the owner's order.

**Before the window (owner):**
1. Create the new-password file OUTSIDE the repository with `python -c "import secrets; print(secrets.token_urlsafe(36))" > <NEWFILE>` written as ASCII/UTF-8 **without BOM** (PowerShell `>` writes UTF-16 and is refused), one line, 32 to 128 characters of letters, digits, `-` and `_`; the value is not displayed.
2. Restrict it: `powershell -NoProfile -ExecutionPolicy Bypass -File group-17c/tools/secure_file_acl.ps1 -Path <NEWFILE> -Rights Modify`.
3. Copy the value into the password manager and check the entry; keep the file until the rotation is complete, then delete it. The operator receives the path only and never opens the file.
4. Choose an empty `<BACKUP>` folder outside the repository and outside `backend/`.
5. Name who can be reached and decides any rollback that writes (H2).

**Conditions the operator confirms at the start (read only):**
- no other process uses the old password: `pg_stat_activity` shows 0 sessions of `asistente_migrator`; no `docker compose` command, orchestrator stage, `db-migrate`, `db-grants`, `db-verify` or CI job from this machine is running; no scheduled task or other terminal runs them; `docker ps -a` lists no `migrate` or `bootstrap` container (step 0b removes exited ones by exact name);
- `ROT_TEST_NO_ACL`, `ROT_TEST_FAIL_AT`, `ROT_TEST_HOOKS`, `ROT_DOCKER_CMD` are unset;
- free RAM at least 8 GB, free disk at least 15 GB, a window of at least 30 minutes, HEAD equal to the published commit named in the authorisation;
- services healthy, `db-verify` with no findings, counts 0/0/0/0/0/0, dumps and `*.pre-17b` copies intact.

**Forbidden during steps 4 and 5:** `db-bootstrap` in any form, any `docker compose up`, `run` or `start` (compose runs `bootstrap` as a dependency of `migrate`), and a host reboot. `bootstrap` re-sets the four role passwords from `.env.roles` and would revert the migrator to the old value; the probes of step 6 detect it and step 4 is then repeated.

**Recovery by stage** (section 7): before step 4 nothing changed; step 4 exit 3 -> probe with the current password first; step 5 failed -> the tool restores the files, then recovery A (revert) or B (forward); the process was killed -> `rollback` then A or B; step 6 or 7 fails -> A; after a failed or rolled-back `apply` the `*.old` copies hold the still-live old value and are deleted by exact name by hand.

**Authorisation message the owner can send** (a NEW message; this one authorises nothing): "I authorise the rotation of the password of the role `asistente_migrator` on the development database, from the head commit `<sha>`, in the window `<date and hours>`, with the procedure of section 6 of SEC-17B-01, new-password file prepared by me at a path I will give the operator privately; I can be reached at `<contact>` and I decide any rollback that writes. It does NOT authorise 17B.6, the administrator password, `JWT_SECRET`, any clean-up, a push, a PR, or any change of backend or worker."
