# Recovery matrix of step 17B and of the TD-038 rotation (read from the code and the rehearsals; nothing real was run, 2026-11-14)

**Verdict on the clean-up: NO-GO for deleting the `*.pre-17b` copies, and NO-GO for running the current `cleanup` command, while those copies are the only TESTED way to restore the configuration.** The minimal corrections that would change that are in section 4. Gates A, H2, L and M stay PENDING (section 5).

## 1. What each recovery consumes

| To recover | With | Where it comes from | Tested |
|---|---|---|---|
| the **database contents and catalog** | the verified dump (two copies, per-copy manifests, SHA-256 `d0a2ad6b…`), `restore_public_cluster.sql`, `restore_public_schema.sql`, the rollback commands (`db-migrate --downgrade 0005`, `db-adopt --rollback --remove-roles`) | outside the repo (`Backups`); the dump restored IDENTICAL in a disposable cluster | yes (17C; replica 86/86 and stages 20/20) |
| the **services** (old stack) | image tags `asistenteia-backend:pre-17b` and `asistenteia-worker:pre-17b` (made by S12 from the ids the containers run), `git show main:docker-compose.yml`, `tools/compose.rollback.override.yml` | local Docker images and the repository | yes (replica rehearsal, override pre-checks) |
| the **configuration**, file level | `prepare_env_files.py --rollback`, which REQUIRES `backend/.env.pre-17b` and `backend/.env.worker.pre-17b` and the current `.env.db` (it refuses otherwise); it also reads `.env.test` and the marker `.env.test.absent-before-17b` / `.env.test.pre-17b` for the `TEST_*` lines; it sets `DATABASE_URL` to the administrator of the CURRENT `.env.db`, keeps what it replaces as `*.rolled-back` and renames the three new role files to `*.rolled-back` | the `.pre-17b` copies created by S21 (the real env files are git-ignored: **no other copy exists**) | yes (80 checks, replica) |
| the **rotation** while it runs (recoveries A/B/C of `rotation/README-17b6.md`) | the backup folder `<BACKUP>/*.old` (originals of `.env.db`, `.env.roles`, `.env.test`) and `rotate_admin_password.py rollback` | the folder given to `apply`, outside the repo | yes (84 + 38 checks) |

`.env.db.pre-17b` is **not** used by `--rollback` (the tool reads the current `.env.db`). The `*.old` copies are used only by the rotation recoveries.

## 2. Matrix: where it fails and what recovers it

| Situation | State | Recovery | Consumes | Tested |
|---|---|---|---|---|
| S20 to S31 fail or the owner stops | before any rotation | checklist section 7 (rollback of the stage reached: stop services, migrate downgrade, adopt rollback, restore PUBLIC, `prepare_env_files.py --rollback`, previous stack with the override) | dump (last resort), `.pre-17b` copies, `pre-17b` images | yes |
| 17B.5 functional check fails | before rotation | same rollback; data written under the roles stays | same | yes |
| rotation: `plan` or the first probe fails | nothing changed | fix the cause | none | yes |
| rotation: **`ALTER ROLE` works, the update of the env files fails** | database has the NEW password, files have the OLD | `apply` restores the files by itself; then **A, revert** (`alter` from `<BACKUP>/.env.db.old`) or **B, forward** (apply again with a new empty backup folder). Never `prepare_env_files.py --rollback` in this state | `<BACKUP>/*.old` | yes (e2e, both recoveries) |
| rotation: **the new password works, the recreation of `db` fails** | database and files have the NEW password; the running container still carries the OLD value in its environment | recreate `db` again (`docker compose up -d --no-deps --force-recreate db`). The password is stored in the data directory and the image's entrypoint ignores `POSTGRES_PASSWORD` when the directory exists, so a failed recreation cannot change authentication; API and worker do not use the administrator. If the container will not start, the volume is untouched (recovery C) | none | the successful recreation is rehearsed (e2e); a FAILED recreation is analysed, not rehearsed |
| the rotation tool is killed in the middle of `apply` | mixed files, orphan `..env.*.rot-<pid>` temps | `rotate_admin_password.py rollback` (restores byte for byte, removes the orphans), then A or B depending on whether `ALTER ROLE` ran (probe with the current password tells) | `<BACKUP>/*.old` | yes (interruption test; a hard kill is documented) |
| the owner wants to undo 17B **after** the rotation, before any clean-up | new password everywhere | `prepare_env_files.py --rollback`: rebuilds `.env` and `.env.worker` with the administrator password of the CURRENT `.env.db`, so the exposed value is never reintroduced; then the rest of the rollback | `.env.pre-17b`, `.env.worker.pre-17b` | yes (replica: rollback after rotation) |
| the owner wants to undo 17B **after the clean-up** | the `.pre-17b` copies are gone | database: dump; services: `pre-17b` images + override; **configuration: no tested tool** (it can be rebuilt by hand from the current files, but that is not rehearsed) | dump, images | **not covered for the configuration** |
| the clean-up is interrupted | some copies removed | run `cleanup` again: it needs the old value to recognise the copies, read from `<BACKUP>/.env.db.old`. Known defect: `.env.db.old` is the FIRST backup copy removed, so an interruption after it leaves a re-run unable to read the old value (the remaining files can then be removed by exact name by hand: `.env.pre-17b`, `.env.worker.pre-17b`, `.env.db.pre-17b`, `.env.test.pre-17b`, `.env.test.absent-before-17b`, never with a wildcard) | | tested for a stuck file; **not** for an interruption after `.env.db.old` |

## 3. When the `*.pre-17b` copies stop being necessary

- **Security value of deleting them is low after the rotation:** the old administrator password is then invalid (the server rejects it), so the dead values in them are harmless. What they still hold that is live is a second copy of `JWT_SECRET` (also in the current `.env`). TD-038 also lists `JWT_SECRET` as exposed; **its rotation is not part of 17B.6** (it would sign out every session; dev only, but a separate decision).
- **Recovery value is high:** they are the only tested route to the pre-17B `.env` and `.env.worker` (the real env files are git-ignored).
- They stop being necessary when the owner formally closes 17B (accepts the final state and no longer wants the file-level rollback) **and** an independent tested way to rebuild the configuration exists, or the owner explicitly waives it in writing.
- Group A (not needed by `--rollback`): `.env.db.pre-17b`, and the rotation `*.old` copies once the rotation is verified and accepted. Group B (needed): `.env.pre-17b`, `.env.worker.pre-17b`, `.env.test.pre-17b`, `.env.test.absent-before-17b`. The current `cleanup` removes both groups together.

## 4. Conditions to run a clean-up without losing recovery, and the minimal corrections

Conditions: (1) the rotation is verified (`verify` clean) and the owner accepted 17B.5 and 17B.6 in writing; (2) the owner confirmed in writing that the file-level rollback of 17B is no longer wanted, OR the group B copies are kept; (3) the dump copies still verify (S11); (4) the `pre-17b` image tags still exist; (5) `cleanup --dry-run` was read.

Minimal corrections (a tool change each, with tests, needing the owner's authorisation; **none was made**):
1. `cleanup` option to remove only group A (`.env.db.pre-17b` and the `*.old` copies) so that the useless-for-rollback copies can go while group B stays. Until then use no clean-up at all.
2. In `cleanup`, remove `.env.db.old` LAST among the backup copies (one-line order change plus a test of an interruption after each file).
3. Only if the owner wants group B gone with a tested way back: `prepare_env_files.py --rollback --pre-dir <archive outside the repo>` (read the two copies from an owner-only archive instead of the working tree), tested like the existing 80 checks. Otherwise group B simply stays until the owner decides.

## 5. Gates (nothing here is approved)

| Gate | Condition to approve | State |
|---|---|---|
| **A** real intervention in development | message A of the authorisation package naming the head commit, the stages S20 to S31 one at a time, the window; 17B.6 and any clean-up NOT included | **PENDING** |
| **H2** who stops and recovers | the owner is the decision-maker; the operator stops, reports and runs only the rollback of the stage reached **that the owner orders**; any rollback that writes is the owner's decision | **PENDING** |
| **L** residual risks, development only | the owner accepts in writing the table of checklist section 4, section 2 of the authorisation package and the open items of this matrix (clean-up NO-GO, JWT_SECRET not rotated, a failed recreation of `db` only analysed) | **PENDING** |
| **M** final GO | "GO 17B.2" only after A, H2 and L are in place and the same day: S10 and S11 repeated and clean, free RAM at least 8 GB and disk at least 15 GB, the CI of the exact head commit green, S12 repeated only if code or configuration changed | **PENDING** |
