# 17B authorisation package (owner's decision sheet; prepared 2026-11-14; NOTHING HERE IS AUTHORISED)

Read together with `17b2-authorisation-checklist.md` (gates, order, token use, risks, stop conditions, recovery) and `rotation/README-17b6.md` (rotation). This sheet only says who decides what and gives the messages the owner can send. No password was generated, read or changed to prepare it. Gates **A, H2, L and M are PENDING**; none is inferred from any earlier message.

## 1. The four open gates

| Gate | State | Who | What closes it |
|---|---|---|---|
| **A** authorisation of the migration (17B.2 to 17B.5, task 3.3b) | **PENDING** | owner | message A below, naming the head commit and the window |
| **H2** who decides at a stop | **PENDING** | owner decides; the operator stops and reports | the owner confirms in message A that the stop conditions of checklist section 5 apply, that the operator never improvises on the real database, and names who can be reached during the window |
| **L** residual risks accepted | **PENDING** | owner | message A states acceptance of the table of checklist section 4 (class A and M rows) and of the extra items in section 2 below |
| **M** explicit "GO" before the first write | **PENDING** | owner | message M below, sent only after A, H2 and L are in place and the owner has read the output of S10 to S13 of that day |

## 2. Risks added by the TD-038 tools (for gate L)

| Risk | Class | Note |
|---|---|---|
| the rotation tools have never run on the real database (rehearsed on a disposable PostgreSQL with synthetic credentials, two independent reviews) | A | 17B.6 is a separate step with a separate authorisation |
| `.env.test` stays inside the rotation (decision record `rotation/env-test-decision.md`) | A | it holds the administrator credential until a separate test cluster exists; the tool rotates it with the other two files |
| the clean-up (step 10 of the rotation) removes the `*.pre-17b` copies that `prepare_env_files.py --rollback` needs, and overwriting a file is best effort on an SSD | **S** if done early | run the clean-up only when the owner no longer wants the file-level rollback path of 17B; after it, the way back is the verified dump plus the `pre-17b` image tags |
| the old (exposed) value stays valid until the rotation, and the backup copies of the env files hold it until the clean-up | A | accepted in the checklist (TD-038); rotation is the closure |
| the operator must never open the new-password file | A | the tools read it; the checks around it print booleans only |

## 3. Messages the owner can send (suggested wording; the operator needs them in a NEW message each time)

**Message A (gates A, H2, L).** "I authorise step 17B.2 to 17B.5 and task 3.3b on the development database `asistenteia`, from the head commit `<sha>`, in the window `<date and hours>`, with the stages S20 to S31 run one at a time. I have read the stop conditions (checklist section 5) and the recovery table (section 7): at any stop the operator stops, reports and takes the rollback of the stage reached; I can be reached at `<contact>`. I accept the residual risks of the checklist (section 4) and of section 2 of the authorisation package. This message does NOT authorise 17B.6, a new backup, a push, or anything not listed."

**Message M (gate M), same day, after the read-only stages.** "GO 17B.2." (the operator then runs each stage with the token on that command line only, as the checklist section 3 says).

**Message R (separate, after the owner has accepted the result of 17B.5 in writing).** "I authorise 17B.6, the rotation of the administrator password, with the tools of `rotation/` from the head commit `<sha>`, new-password file prepared by me at a path I will give the operator privately." If the owner wants the clean-up (step 10) in the same window, say so explicitly; otherwise it waits.

## 4. Procedure

**Before the window (owner):**
1. Prepare the new password OUTSIDE the repository, in a file that only the owner can read: `python -c "import secrets; print(secrets.token_urlsafe(36))" > <NEWFILE>` (the value is not shown), then `powershell -NoProfile -ExecutionPolicy Bypass -File group-17c/tools/secure_file_acl.ps1 -Path <NEWFILE> -Rights Modify`. It must be UTF-8 or ASCII and one line (a PowerShell `>` redirect writes UTF-16 and the tool refuses it).
2. Copy the value from that file into the password-manager entry; check the entry; keep the file until 17B.6 is complete, then delete it. The operator is given only the path, never the value; the operator never opens it. What the operator can check without seeing it: `rotate_admin_password.py plan` accepts the file (format, outside the repository) and `secure_file_acl.ps1 -VerifyOnly -Rights Modify` accepts its descriptor.
3. Free RAM at least 8 GB, a window of at least 30 minutes, `ROT_TEST_HOOKS` and `ROT_DOCKER_CMD` not set in the shell.

**17B.2 to 17B.5 (after messages A and M):** the nine write stages in the order of checklist section 2, then the functional verification: through the real endpoints and with synthetic data only (`g17b-*@example.com`): registration, login, a teacher created through the CLI service (`--password-stdin`), a subject, an enrollment, a TXT upload that the worker takes to `ready`; the denied cases (a student cannot create a subject, the API role cannot insert a teacher, the worker role cannot read `users`); `db-verify` again with no findings; deletion of the synthetic rows and row counts equal to those of the preflight; only `asistente_app` and `asistente_worker` hold sessions. The owner accepts the result in writing (this acceptance is the condition for message R).

**17B.6 (only after message R):** the table of `rotation/README-17b6.md`, steps 1 to 9; step 10 (clean-up) only if the owner asked for it, remembering section 2.

## 5. Recovery

| Where it fails | What to do |
|---|---|
| S20 to S31 | checklist section 7 (the rollback of the stage reached; first stop `backend` and `worker`) |
| 17B.5 (functional) | the same rollback; data written under the new roles stays |
| rotation, before `ALTER ROLE` (README steps 1 to 3) | nothing changed; fix the cause |
| rotation, `ALTER ROLE` done and the files failed (step 5) | README recovery A (revert the database from the backup copy of `.env.db`) or B (fix and apply again with a new empty backup folder) |
| rotation, the database container does not become healthy (step 6) | README recovery C (the volume is untouched; check `verify`; recreate) |
| the tool process was killed in the middle | `rotate_admin_password.py rollback` with the backup folder (restores the files byte for byte and removes the orphan temporary files), then A or B depending on whether `ALTER ROLE` ran |
| after the rotation the owner wants to undo 17B | `prepare_env_files.py --rollback` rebuilds `.env` and `.env.worker` with the administrator password of the CURRENT `.env.db` (never the exposed one) as long as the `*.pre-17b` copies still exist; after the clean-up only the dump and the `pre-17b` images remain |

## 6. What is NOT in this package

17B.2 or any stage from S20 on has not been run; no real password, role, file or service was touched; the branch protection and the pull request are outside it.
