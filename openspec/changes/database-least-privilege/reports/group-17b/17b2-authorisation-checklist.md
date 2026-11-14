# Step 17B.2: definitive authorisation checklist (prepared 2026-11-14; NOT an authorisation)

Nothing in this document authorises anything. Gates **A** and **M** are the owner's and are **not** marked. 17B.2 writes to the real development PostgreSQL and recreates the API and the worker; until the owner sends the message described in section 3, only stages S10 to S13 (read only, images) may run.

Code state this checklist refers to: branch `feature/database-least-privilege`, published at the head recorded in the report of the day (the run of the orchestrator must be done from a clean checkout of that head). Procedure: `group-17a/runbook-17b.md`; orchestrator: `group-17b/run_17b.sh` (`--plan`, `--status`, `--stage Sxx`, `--through Sxx`).

## 1. Gates A to M

| # | Gate | State now | Evidence | Repeat on the day |
|---|---|---|---|---|
| **A** | Authorisation of 17B (and of task 3.3b and of the rotation window) | **OWNER, OPEN: not authorised** | the owner has authorised only 17B.1, S13, the publication of the branch and this checklist | needs a new explicit message naming 17B.2 |
| A2 | Nothing else in flight | OK | clean tree except the seven reference documents; branch published; HEAD recorded | `git status`, `git log -1`, same head as the remote, OpenSpec 18/18 |
| B | Exact backup, restore proven | OK | dump of 2026-11-14, revision 0005, SHA-256 `d0a2ad6b…6279d9`, 17 437 bytes; restored in a disposable cluster IDENTICAL to the source (17C); per-copy manifests (TD-049) | **S11** (hashes, manifests, ACLs, fresh snapshot equal to the backup-time one). If it fails: a NEW backup needs the owner's authorisation |
| B2 | Older backups untouched | OK | hashes of `pre_0004`, `pre_0005` and both 17b copies unchanged (`td049-real-folders-evidence.txt`) | S11 covers the 17b copies; compare the inventory of the rollback folder |
| C | Unambiguous cluster | OK | container `asistenteia-db-1`, project `asistenteia`, database `asistenteia`, PostgreSQL 15.19, `system_identifier` pinned in the script | **S10** |
| D | Catalog equals the expected 0005 baseline | OK | `IDENTICAL` 118 lines and 9 lines (cluster) | **S10** |
| E | Transactions, sessions, other clients | OK | 0 open transactions, 0 prepared, 0 ungranted locks, only the worker as a client, no other login role | **S10** |
| F | Services and dependencies | OK, with risk | worker healthy, API exited, pre-17b image tags point at the ids the containers run | S10 (state), `--status`; re-run **S12** if any commit touched `backend/` or `docker-compose.yml` since the last S12 (the services bind-mount `./backend/app`: the working tree must equal the commit the images were built from) |
| F2 | Rollback tooling is the tested version | OK | env tool 80/80; rollback rehearsed from every stage and from the end state (replica 86/86, stages 20/20); orchestrator static suite and disposable-stack scenarios green | `python group-17a/tools/test_prepare_env_files.py` (80 checks), `bash group-17b/test_run_17b_static.sh` |
| F3 | New images built, settings loadable | OK | S12 real (five images, containers untouched); S13 real: API and worker settings of the current files load in the new images; simulated post-transformation environment loads for API, worker, migrator, CLI, roles and db-verify | S13 again only if the env files changed (`--allow-real-settings`, owner's decision) |
| G | Restricted roles prepared | OK (dry run) | `prepare_env_files.py --dry-run --strip-legacy` accepts the real folder; the four new files get the owner-only descriptor (`-Rights Modify`, Docker Desktop reads them: 23/23) | the dry run is the first command of S21 |
| H | Complete rollback procedure | OK | runbook table; manual order documented | the owner reads section 7 |
| H2 | Who decides and when to stop | **OWNER, OPEN** | section 5 below | the owner reads and acknowledges it in the authorisation message |
| I | Exposed credential with a planned rotation | OK on paper; **rotation tools ready and tested on disposable resources** (`group-17b/rotation/`, `td038-rotation-readiness.md`); still needed for 17B.6: the owner's password file and manager entry, the owner's approval of `README-17b6.md` | `credentials-and-services-map.md` section 4; rotation is **after** acceptance (17B.6) | the owner prepares the password-manager entry and the file for the new value before the window |
| J | Quality gates | OK | CI green on GitHub Actions three times in a row (pushes of `53031a1`, `8931d67`, `963bc02`; `backend`, `privileges`, `frontend`; 1 072 privilege tests, 0 failed, 0 skipped); local suites as in the earlier reports | the CI run of the head to be used must be green |
| J2 | CI decision | **APPROVED by the owner** (first real runs green) | `group-17c/ci-first-run-result.md`; TD-045 stays open | none |
| K | Resources and window | repeat | free RAM measured 8.4 to 9.7 GB during 17B.1; disk 675 GB | **RAM at least 8 GB free (stop below)**, disk at least 15 GB, a window of at least 30 minutes with API and worker allowed to be down (2 to 3 minutes expected) |
| L | Residual risks accepted | **OWNER, OPEN** | table in section 4 | the owner accepts it in writing |
| M | Explicit "GO 17B.2" before the first write | **OWNER, OPEN: not given** | none | only after A to L are green and the owner has seen the output of S10 to S13 of that day |

The owner's decision sheet for the four open gates (A, H2, L, M), the messages the owner can send, the preparation of the new password and the recovery after a rotation is `17b-authorisation-package.md`.

## 2. Order of the real operations (all but the first four need the owner's GO)

Read only, before the GO (they are already authorised): `S10 preflight`, `S11 backup_validate`, `S12 images` (only if needed, see F), `S13 settings_load` (needs the owner's decision, argument `--allow-real-settings`). The owner reads their output.

After the owner's message "GO 17B.2" (one invocation per stage; the operator reports each output before the next one):

| # | Stage | What changes | Expected result | If it fails |
|---|---|---|---|---|
| 1 | S20 `stop_services` | `backend` and `worker` stopped (the database container is not touched) | database snapshot identical to S10 | previous stack with the override (rollback step 6) |
| 2 | S21 `prepare_env` | dry run, then `.env.roles`, `.env.migrate`, `.env.cli`, `.env.test` created, `DATABASE_URL` rewritten in `.env` and `.env.worker`, `POSTGRES_*` removed, `TEST_*` moved, `.pre-17b` copies, owner-only descriptors | names only on screen | steps 5, 6 |
| 3 | S22 `bootstrap` | the four roles created; ends with exit 1 and lists the ownership drift (**expected**) | exit 1 and the drift listing; anything else stops | steps 3, 4, 5, 6 |
| 4 | S23 `adopt_dry_run` | nothing | exactly 9 objects | same |
| 5 | S24 `adopt_apply` | ownership of `alembic_version`, the six tables and the two enum types goes to the migrator | exit 0 (atomic) | same |
| 6 | S25 `migrate` | Alembic 0005 to 0006 and the grants | revision 0006 | steps 2, 3, 4, 5, 6 |
| 7 | S26 `db_verify` | nothing | "no findings" | same |
| 8 | S30 `switch_services` | `backend` and `worker` recreated with the new files and images | worker healthy (about 125 s) | steps 2 to 6 |
| 9 | S31 `verify_sessions` | nothing | only `asistente_app` and `asistente_worker` hold sessions | steps 2 to 6 |
| 10 | manual, runbook 17B.5 | synthetic accounts `g17b-*` and data, denied cases, `db-verify`, cleanup, row counts equal to the preflight | all checks pass | steps 2 to 6 (the data written under the roles stays) |
| 11 | manual, runbook 17B.6, **only after the owner accepts** | rotation of the administrator password (TD-038), then destroy the `*.pre-17b` copies | old password refused, new accepted, `bootstrap` exits 0, API answers | section 7 |

The orchestrator never runs rows 10 and 11 and never runs a destructive command by itself.

## 3. Use of `G17B_OWNER_GO` (an acknowledgement token, not a secret, and not an override)

- It is given **only on the command line of the single stage the owner has just authorised**, as a prefix assignment that is not exported: `G17B_OWNER_GO=GO-17B.2 bash run_17b.sh --stage S20`. Never `export`, never in `.bashrc`, a profile, a `.env` file, a script, a CI variable or a shell alias; never `--through` over several write stages unless the owner's message says so.
- It is not stored in any file by the operator and the orchestrator does not write it to the state file or to the log. Avoid leaving it in the shell history (start the line with a space when `HISTCONTROL=ignorespace` is set, or clear the history entry afterwards). A different value, another case or an empty value is refused with exit 7.
- It only opens the **authorisation** check. It does not skip, and nothing else skips: the cluster identity (pinned `system_identifier`), the integrity of the state file, the order of the stages, the refusal of a stage already done, the lock, the RAM and disk gates and the checks of each stage always run. A write stage that failed, was interrupted or was killed is refused (exit 8) until the owner has looked at `--status` and the database and sets `G17B_CONFIRM_RERUN=<stage>` for that one run.
- The test profile and its hooks are refused in the real profile; the test profile cannot name the real stack, its env folder, its backups or its compose file.
- No stage from S20 on is run without the owner's explicit additional authorisation. This checklist is not that authorisation.

## 4. Residual risks, for the development environment only (for the owner's approval: gate L)

Classes: **A** acceptable for development; **M** mitigated; **S** obliges to stop; **P** pending for production.

| Risk | Class | Reason / mitigation | Production |
|---|---|---|---|
| TD-038: the administrator password and the JWT secret lived in a container environment and were never rotated | A until 17B.6, then M | single-user workstation, loopback port, no real data; rotation rehearsed (about 8 s) and done after acceptance; the `*.pre-17b` copies hold the old value until destroyed | **P**: rotate before any shared or real use; never reuse the development values |
| TD-039: commit-after-response handlers | M | fixed in code on this branch with RED/GREEN tests and 16 mutations | **P**: merge and deploy the fix |
| TD-040: the API role can still insert a teacher until the roles are adopted | A until S24, then closed | 17B.2 is what closes it; the code-level rule holds meanwhile | **P**: verify after the real rollout |
| TD-044: limits of the adoption and of the rollback (grants after Alembic, row counting inside the lock, the bootstrap closes `PUBLIC` on every database, rollback without one transaction) | A | the database is empty; the commands refuse running sessions, unexpected objects and lock waits; dev cluster only | **P**: rehearse on a copy of real data, never on a shared cluster without review |
| TD-045: CI is advisory, branch protection unavailable on this plan; floors can be overridden; actions pinned by tag | A | three green remote runs; operational rule: no merge to `main` without `backend`, `privileges` and `frontend` green on the head of the pull request | **P**: protection and required checks, pin by SHA |
| TD-048: the start-up identity check refuses a superuser only; `OperationalError` is answered 503 for several causes | A | development roles are the five defined ones | **P**: harden the checks and the error mapping |
| API and worker down about 2 to 3 minutes, and again on a rollback | A | window of at least 30 minutes | **P**: rolling or blue-green |
| the development worker enters a crash loop if it is restarted with the current code before S30 (the new code refuses a superuser) | **S** if anything restarts it | do not restart services by hand; S20 stops it, S30 recreates it with the new files; recovery with the override | n/a |
| the real `.env` still holds the administrator credentials until S21 | A until S21, then closed | `--strip-legacy`; the tool refuses to run without it | n/a |
| rollback restores the default ACLs in an equivalent explicit form, not byte for byte | A | ownership, roles, grants and rows identical; the dump gives the exact catalog | **P**: document |
| the closing of `PUBLIC` is cluster-wide and is undone by script, not by `db-adopt --rollback` | M | `restore_public_cluster.sql` and `restore_public_schema.sql` are part of the rollback | **P**: review per cluster |
| `db-verify` assumes one application database per cluster | A | do not bootstrap `asistenteia_test` | **P**: review |
| the rehearsals ran on a reconstructed 0005 copy and an empty database | A | the real database is empty with the same catalog (gate D) | **P**: rehearse with data |
| the state file and the token are accident guards, not a defence against a malicious operator | A | single-user workstation | **P**: signed approvals |
| `pip-audit` reports `dnspython` and `opentelemetry-api` in `backend/uv.lock` (non-blocking) | A | same alerts as `main`, not introduced by this change | **P**: update dependencies first |

## 5. Stop conditions (NO-GO; after a stop take the rollback column of the stage reached, never improvise on the real database)

Any unexpected exit code; any hash, manifest or ACL check of the backup that fails; the real database no longer equal to the state the backup was taken from (a new backup is needed and needs the owner's authorisation); the catalog or the cluster different from the expected baseline; an open or prepared transaction, a query running over 30 seconds, or a client the owner does not recognise; the `system_identifier` different from the pinned one; free RAM below 8 GB or free disk below 15 GB; a build failure; a settings load failure (S13); bootstrap not ending with exit 1 and the drift listing; the dry run not listing exactly 9 objects; `db-adopt --apply` or the migration failing; any `db-verify` finding; a lost connection during the adoption; the worker not healthy after 450 s; a session of the administrator after the switch; an interruption (exit 40) of a write stage (its outcome is unknown); a state file reported as edited; the CI run of the head not green; a request of the owner.

## 6. Authorisation message the owner can send (suggested; the operator needs it before S20)

"GO 17B.2" naming: the head commit; the stages S20 to S31 in order, one invocation each; task 3.3b (creation of the role files and the edit of the two `DATABASE_URL` values); the window; acceptance of section 4; and, separately, whether 17B.6 (rotation) may follow after the owner's acceptance.

## 7. Recovery by stage (runbook `group-17a/runbook-17b.md`, "Rollback"; first stop `backend` and `worker`: `docker compose rm -sf backend worker`)

| Stage reached | Steps |
|---|---|
| S20 (services stopped, nothing else) | 6 |
| S21 (files prepared) | 5, 6 |
| S22 to S24 (bootstrap, adoption) | 3, 4, 5, 6 |
| S25 to S31 (migration, grants, switch) | 2, 3, 4, 5, 6 |

1. stop the services. 2. `db-migrate --downgrade 0005` with `.env.migrate`. 3. `db-adopt --rollback --remove-roles --apply --database asistenteia` with `.env.roles` (dry run first). 4. `restore_public_cluster.sql` on `postgres` and `restore_public_schema.sql` on `asistenteia`. 5. `prepare_env_files.py <backend> --rollback` (restores `.env` and `.env.worker` from the `.pre-17b` copies with the administrator password of the current `.env.db`; renames the new files `*.rolled-back`). 6. start the previous stack from `git show main:docker-compose.yml` plus `tools/compose.rollback.override.yml` (checks before: no `backend/app` bind, two `:pre-17b` images). Measured on the replica: about 134 s. Recovery of last resort: the verified dump (`DROP DATABASE`, `createdb`, `pg_restore`, then the restore scripts; about 1 s when empty). Rotation interrupted (17B.6): `ALTER ROLE` failed, nothing changed; `ALTER ROLE` done but a file still old, write the new value in the files by hand and recreate `db`; never run `--rollback` in that state (credentials map, section 4).

## 8. Evidence index

`group-17c/ci-first-run-result.md`, `group-17c/ci-push-audit.md`, `group-17c/td049-real-folders-evidence.txt`, `group-17b/g17b-real-s10-s11-s12.log.txt`, `group-17b/g17b-s13-validation-output.txt`, `group-17b/g17b-static-output.txt`, `group-17b/g17b-orchestrator-docker-output.txt`, `group-17b/g17b-docker-mutations-output.txt`, `group-17b/g17b-images-after-s12.txt`, `2026-11-14-step-17b1-s13.md`, `2026-11-14-step-17b1-continuation.md`.
