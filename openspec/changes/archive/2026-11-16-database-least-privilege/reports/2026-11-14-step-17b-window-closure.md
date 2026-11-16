# Step 17B.2 to 17B.5: closure of the intervention window of 2026-11-14 (development database)

Sanitized. No credential, URL, hash or token appears here. Head commit of the intervention: `c789ed0` (the code and configuration that ran); the documentation commits that follow it (`5e4d614`, `185d67b`, `30a07bb` and this one) are local and unpublished. Window: 14/11/2026 18:30-20:00 America/Argentina/Cordoba (owner: stop, rollback and contact). The owner accepted 17B.2 to 17B.5 as operationally closed.

## 1. What was done (one stage per invocation, each authorised by a new owner message)

| Stage | Result |
|---|---|
| S20 | backend and worker stopped (18:30) |
| S21 | env files prepared: `.env.roles`, `.env.migrate`, `.env.cli`, `.env.test` created; `.env` and `.env.worker` now name `asistente_app` and `asistente_worker`; `*.pre-17b` copies and the `.env.test.absent-before-17b` marker created |
| S22 | `db-bootstrap`: four restricted roles created, databases closed to PUBLIC; exit 1 as expected, only from ownership drift of exactly 9 objects |
| S23 | `db-adopt` dry run: the same 9 objects |
| S24 | `db-adopt --apply`: **nine objects (seven tables, two enum types) adopted by `asistente_migrator`**; data, indexes and constraints identical |
| S25 | **migration 0005 -> 0006 applied** (`users.role` server default `'student'`), privilege grants applied |
| S26 | `db-verify`: `no findings` |
| S30 | backend and worker recreated with the restricted identities (19:06); worker healthy in 14 s; total unavailability about 36 minutes |
| S31 | only `asistente_app` and `asistente_worker` hold sessions |
| 17B.5 | **25 of 25 functional checks**; the synthetic subject (with its document, chunks, job and enrollment) removed through the application role; the three synthetic users removed in one transaction by the migrator under an exceptional owner authorisation (dry run, exact ids, exactly 3 rows); **counts back to 0/0/0/0/0/0**; details in `2026-11-14-step-17b5-functional-closure.md` |

Final state of the environment (read only, 19:56): revision 0006; nine objects owned by `asistente_migrator`; PUBLIC without grants on tables, columns, databases and schema; restricted roles without `SUPERUSER`, `CREATEROLE`, `CREATEDB`, `REPLICATION` or `BYPASSRLS`; `db-verify` with no findings; backend HTTP 200 (restricted role `asistente_app`), worker healthy (`asistente_worker`), 0 restarts; one session of each, none of the administrator; orchestrator state intact (S10-S13, S20-S26, S30, S31 done, none failed).

## 2. Backups and recovery assets (all intact at the close)

Two copies of the verified dump taken before 17B with independent manifests (SHA-256 prefix `d0a2ad6b`), the `pre_0004` and `pre_0005` backups, the three `*.pre-17b` configuration copies (byte-identical to before S30) and the marker, the `pre-17b` image tags of backend and worker, the git recovery refs `refs/backup/pre-j2-sanitize` and `refs/original/refs/heads/feature/database-least-privilege`. Nothing was deleted. The rollback of the intervention (runbook steps 2 to 6) was never needed and was not run.

## 3. Open items (none authorised)

| Item | State |
|---|---|
| **SEC-17B-01** (password of `asistente_migrator` exposed by a traceback) | **open**; tool and procedure prepared and twice reviewed; real rotation pending a separate authorisation and a new window (`2026-11-14-sec-17b-01-migrator-password-exposure.md`, sections 6, 7 and 10) |
| **TD-038** administrator password rotation (17B.6) | pending; the old value stays valid until a separately authorised 17B.6 |
| `JWT_SECRET` rotation | pending; outside 17B |
| clean-up of the `*.pre-17b` copies | **NO-GO** (they are the only tested file-level rollback path) |
| TD-039 (`DELETE /users/me` and the other erasure endpoints are in the contract and not in code) | open; closes in change 11 together with a reviewed `DELETE` grant on `users` |
| TD-045 (branch protection unavailable), Dependabot and `pip-audit` findings, publication of the three local documentation commits, PR and merge | open / not authorised |

## 4. Recovery matrix: `ALTER ROLE` succeeded, then `apply` failed on `.env.roles` or `.env.migrate` (analysis only; nothing was run)

Why it matters: `alter` (step 4) is the point of no return. After it, the database holds the NEW password while the files may still hold the OLD one.

**State right after the failure** (the tool restores both files from `<BACKUP>/*.old` by itself, exits 1, or 130 if interrupted, or 3 if the restore itself was incomplete):

| Component | State |
|---|---|
| PostgreSQL role `asistente_migrator` | NEW password (verifier installed by step 4) |
| `.env.roles`, `.env.migrate` | OLD values (restored byte for byte) when the exit code is 1 or 130; possibly mixed when it is 3 or when the process was killed |
| which credential works against the database | **the NEW one** (from the owner's new-password file and password manager); **the OLD (exposed) one is already rejected** |
| consumers | `db-migrate`, `db-grants`, `db-verify` and the compose `migrate`/`bootstrap` services fail authentication because the files hold the old value; **backend and worker are unaffected** (they use other roles) |
| security objective | already met at the database: the exposed password no longer opens anything |
| hazard | `db-bootstrap` (also started by a plain `docker compose up`) would re-set the migrator password from the OLD `.env.roles` and silently revert the database to the exposed value |

**Decision tree** (all steps use the tools of `rotation/`; every probe, `alter`, `apply` and `rollback` uses paths only and standard input: no secret in an argument, an output or a log):

| Situation | Action | Tool and copies | Needs the owner's express order |
|---|---|---|---|
| exit 1 or 130, files restored, new-password file intact and the cause of the failure is understood | **B, forward (preferred)**: fix the cause, then `rotate_role_password.py apply` again with a NEW empty `<BACKUP>` folder (keep the first until the end), then the probes of step 6 and `db-verify` | `rotate_role_password.py`, the new-password file; the first backup folder stays | yes (it writes files) |
| exit 3, or the process was killed, or files look mixed | first `rotate_role_password.py rollback <backend> --backup-dir <BACKUP>` (restores both files, removes orphan temporaries; safe to repeat); compare each file with its `.old` copy by size and hash, never by opening them in a shared view; then B | `<BACKUP>/*.old` | yes |
| forward is not possible in the window (new-password file lost or unusable, cause not fixable, owner wants the pre-rotation state) | **A, revert (last resort)**: `rotate_db_role.py alter --role asistente_migrator --from-env-file <BACKUP>/.env.roles.old --var DB_MIGRATOR_PASSWORD`, then probes (old accepted, new rejected). **This puts the exposed password back in the database**; SEC-17B-01 stays open and a new rotation is needed | `<BACKUP>/.env.roles.old` | yes, and the owner must accept the exposed credential being valid again |
| the new value is lost but the files are intact | create a NEW new-password file (owner) and run `alter` again, then `apply` (this is B with a different password) | new file | yes |
| anyone ran `db-bootstrap` or `docker compose up` in between | the database is back on the OLD value: probe with the current password (tells the truth), repeat step 4, then continue | probes, new-password file | yes |
| doubt about the state | do nothing that writes; probe the NEW password from the new-password file and the OLD one from `<BACKUP>/.env.roles.old` (read-only checks over the Docker network) | `rotate_db_role.py probe` | no (read only) |

**When to revert and when to go forward:** forward (B) whenever the new-password file is intact, because the old value is already dead and reverting would resurrect it; revert (A) only when forward cannot be completed in the window and the owner prefers the pre-rotation state over leaving the migrator tools unusable. In both cases the old backup copies (`<BACKUP>/*.old`) hold the old value and, after a failed or rolled-back `apply`, are deleted by exact name by hand once the rotation is finished or abandoned (`discard` refuses while the live files hold the old value).

**Operations that always need the owner's express order (H2):** `alter` (any direction), `apply`, `rollback` and `discard`. Read-only probes, `plan`, `check`, `verify` and the container scan do not.

## 5. Preparation of a new window

Nothing is scheduled. Requirements, order, stop points, recovery by stage and the message the owner can send are in section 10 of the SEC-17B-01 report. In short: new-password file prepared by the owner outside the repository (no BOM, owner-only ACL, copied to the password manager), an empty backup folder, no other process using the old password, test variables unset, no `db-bootstrap`, `docker compose up`, `run` or `start` and no reboot between `alter` and `apply`, backend and worker untouched, and a new owner message naming the head commit and the window.

## 6. Verification of this document

Audited against the six real secret values and for personal paths and e-mail addresses before it was committed (no hit); `openspec validate --all --strict` passes.
