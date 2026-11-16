# Operational decisions in force and final gate table (informative; recorded 2026-11-14; NOTHING HERE IS AUTHORISED)

## 1. Decisions kept explicitly by the owner

| # | Decision | Effect |
|---|---|---|
| 1 | **Clean-up of the `*.pre-17b` copies: NO-GO** | no command that deletes them is run; reasons and the minimal corrections are in `recovery-matrix.md` sections 3 and 4 |
| 2 | **Step 10 of 17B.6 is not run** | `rotation/README-17b6.md` marks it NO-GO; the package and the checklist say the same |
| 3 | The existing configuration copies are kept | `.env.pre-17b`, `.env.worker.pre-17b`, `.env.db.pre-17b` and, when 17B creates them, `.env.test.pre-17b` and `.env.test.absent-before-17b` stay where S21 puts them |
| 4 | The PostgreSQL backups are not deleted | the two copies of the 17b dump with their independent manifests, `pre_0004` and `pre_0005` |
| 5 | The recovery refs are not deleted | `refs/backup/pre-j2-sanitize` and `refs/original/refs/heads/feature/database-least-privilege` |
| 6 | **`JWT_SECRET`: rotation pending, outside the scope of 17B.2** | it is also a TD-038 item; rotating it signs every session out and is a separate decision and procedure |
| 7 | **TD-038: the administrative password stays valid until a rotation the owner authorises separately (17B.6, message R)** | accepted risk, class A in the checklist |
| 8 | `.env.test` stays inside the scope of the rotation | `rotation/env-test-decision.md` |

## 2. 17B.2 to 17B.5 never invoke the clean-up, directly or indirectly (verified by reading, 2026-11-14)

- `run_17b.sh` (the orchestrator): no call to `rotate_admin_password.py`, to `rotate_db_role.py`, to any `cleanup` mode or to `prepare_env_files.py --rollback`. Its only deletions are its own temporary files and the snapshot folders under the state folder (outside the repository): the lock, the sanitized-output temporaries, `preflight-before` and `after-stop`. The `*.pre-17b` names appear only in existence checks (the S21 post-check and `--status`).
- S21 runs `prepare_env_files.py --dry-run --strip-legacy` and then `--strip-legacy`: the forward mode creates the `.pre-17b` copies and refuses to run while any exists; it deletes only files it created itself in the same run when it has to undo a failed run.
- The runbook for 17B.2 to 17B.5 has one word "cleanup": the heading of 17B.5 refers to deleting the SYNTHETIC ROWS of the functional check (`DELETE ... WHERE email LIKE 'g17b-%'`), not any file. The heading now says "removal of the synthetic data" to avoid the confusion.
- Any later change that would make an orchestrator stage delete a recovery copy needs the owner's separate authorisation.

## 3. Final gate table (informative: the owner approves each one in a message of his own)

| Gate | What the owner approves | Condition before it can be approved | Approval state |
|---|---|---|---|
| **H2** | the owner is the person who DECIDES any rollback that writes; the operator stops the execution, reports and runs a rollback only when the owner orders it | the stop conditions (`17b2-authorisation-checklist.md` section 5) and the recovery matrix (`recovery-matrix.md`) have been read; a contact for the window is named | **NOT APPROVED** |
| **L** | the residual risks, for the DEVELOPMENT environment only | the table of the checklist section 4, section 2 of `17b-authorisation-package.md`, and the open items of the matrix (clean-up NO-GO, `JWT_SECRET` not rotated, a failed recreation of `db` only analysed) | **NOT APPROVED** |
| **A** | the express authorisation of 17B.2 to 17B.5 and task 3.3b on the development database, one stage per invocation | message A of the package, naming the head commit and the window; excludes 17B.6, the rotation of `JWT_SECRET`, any clean-up and any new backup | **NOT APPROVED** |
| **M** | the final operational GO | given the same day, only after A, H2 and L are in place and after the operator has repeated and shown: S10 and S11 clean, free RAM at least 8 GB and free disk at least 15 GB, the CI of the exact head commit green; S12 only if code or configuration changed | **NOT APPROVED** |

## 4. What is still open (not blockers of the request for authorisation, but they stay visible)

`JWT_SECRET` and the administrative password are still the exposed values; the clean-up and its minimal corrections (`recovery-matrix.md` section 4) wait for a decision; the three branch-level items of TD-045 (protection unavailable, procedural rule of three green checks, pinned actions) stay open.

## 5. Update at the close of the 2026-11-14 window (recorded afterwards; the sections above are the state before it)

The owner approved gates A, H2, L and M for the development database in the window 18:30-20:00 of 2026-11-14 (head commit `c789ed0`) and authorised each stage S20 to S31 and 17B.5 in a message of its own. The intervention is operationally closed (`../2026-11-14-step-17b-window-closure.md`). The table of section 3 describes the state BEFORE the window; the approvals are not reusable for another window.

Decisions in force after the close:

| # | Decision | Effect |
|---|---|---|
| 1 | clean-up of the `*.pre-17b` copies stays **NO-GO** | unchanged from section 1 |
| 2 | 17B.6 (administrator password, TD-038) and the `JWT_SECRET` rotation are **pending** and need their own authorisation | unchanged |
| 3 | **SEC-17B-01** (password of `asistente_migrator` exposed in a traceback) is open; the password is treated as compromised until rotated | real rotation only with a new owner message, a new window and the procedure of the SEC-17B-01 report |
| 4 | the three local documentation commits and the closure commit are **not published**; no push, PR or merge without the owner | unchanged |
| 5 | no application role may delete users until change 11 delivers the erasure endpoints and a reviewed grant (TD-039); deleting synthetic users needs an exceptional authorisation | recorded in the 17B.5 report |
| 6 | the session transcript that contains the exposed password is outside the repository and is not edited by the operator | the owner decides |
