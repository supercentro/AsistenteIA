# Incident: a database credential was printed by a review subagent (2026-11-13)

Recorded under task 15.2. **The value is not reproduced here or anywhere in the repository.** Nothing was rotated, changed or deleted: no real `.env` file, role, password, container, transcript or log was modified, and no audit record was rewritten.

## What happened

During the PostgreSQL review of task 15.1, a read-only reviewer subagent searched the real `backend/.env` files to find which database user the API and the worker use. The output of one of its searches contained the value of `POSTGRES_PASSWORD`. The reviewer reported the fact itself in its final message and did not copy the value anywhere. The review instructions said "read-only" but did not forbid reading the values of real secret files (lesson L31).

## Credential affected (names only)

| Item | Detail |
|---|---|
| Credential | the password of the PostgreSQL **administrator** of the development database (the superuser `asistente`), `POSTGRES_PASSWORD` |
| Where it lives legitimately | `backend/.env.db` (`POSTGRES_*`, read by the `db` container) and, because the development stack still connects as the administrator (TD-040), inside `DATABASE_URL` of `backend/.env` (API) and `backend/.env.worker` (worker). The database container also holds it in its environment (it keeps the environment it was created with, L29). Later it belongs in `ADMIN_DATABASE_URL` of `backend/.env.roles` and `TEST_ADMIN_DATABASE_URL` of `backend/.env.test` |
| Services touched by a rotation | `db` (container environment and the role in PostgreSQL), `backend` (API), `worker`, the host-side integration tests, and in the future `bootstrap` |
| Not affected | the passwords of the four working roles (they do not exist on this machine yet), the JWT secret, any API token, any production system |

## Where copies were looked for

Searched by pattern with counts and file names only (nothing printed): every file tracked or untracked by Git outside the real `backend/.env*` files, the committed reports, the scratch directory of this session, the output files of background tasks, the transcript of this session, and the transcripts of its subagents. Placeholders (`CHANGE_ME`) were excluded.

| Place | Non-placeholder matches |
|---|---|
| Tracked and untracked repository files (reports, docs, tests, examples) | 0 |
| Scratch directory and task output files of this session | 0 |
| Transcript of the main session | 0 |
| **Local transcript of the reviewing subagent** (`~/.claude/projects/<project>/<session>/subagents/agent-a0be5455c6bc153d6.jsonl`) | **2** |
| Remote repository, Docker images, logs of the containers | not searched: nothing was pushed and the value was never written by a command that logs; to be checked when the rotation runs |

So the value exists only in a local file outside the repository, on the owner's machine, readable by the owner's user. It is not in Git history and has not left the machine through this project. Per the instructions it was **not deleted or rewritten**.

## Assessment

Severity: low to medium. It is the password of a local development database whose port is published on the loopback interface of the owner's machine; the database holds no row of real users (all tables are empty). The risk is that someone with access to the transcript could connect as the superuser to that local database. It also matters because the same value is the administrator credential that the roles bootstrap will use (`ADMIN_DATABASE_URL`), so it should be rotated before the real roll-out rather than reused (TD-038 already records that the values were never rotated).

## Rotation procedure (prepared, not executed)

To run as part of group 17 (or earlier if the owner wants), with the owner's explicit authorisation, and in this order because each step depends on the previous one.

1. **Preconditions**: a verified backup (see the dangerous-operations checklist of the development guide); the API, the worker and the tests stopped (the code now refuses to restart them as the administrator anyway); free memory of at least 6 GB if a disposable rehearsal is run first.
2. **Rehearsal** on a disposable copy of the same image and volume snapshot: generate a new value, run `ALTER ROLE asistente PASSWORD ...` through `\password` or a prompt (never with the value on a command line or in a shell history), recreate the container, connect with the new value, and confirm that the old one is refused.
3. **Generate** the new value: `python -c "import secrets; print(secrets.token_urlsafe(32))"`; keep it in the owner's password manager, not in a chat.
4. **Change the role in PostgreSQL** first (`ALTER ROLE asistente`), because `POSTGRES_PASSWORD` is read only when the volume is created.
5. **Update the files together**, with the services stopped: `backend/.env.db`; `backend/.env.roles` (`ADMIN_DATABASE_URL`) once it exists; `backend/.env.test` (`TEST_ADMIN_DATABASE_URL`); and, **only while the API and the worker still connect as the administrator**, `DATABASE_URL` of `backend/.env` and `backend/.env.worker`. After group 17 those two hold the role passwords and do not contain this value at all.
6. **Recreate the `db` container** (it keeps the environment it was created with) with `docker compose up -d --no-build --no-deps --force-recreate db` and check the effective variable **names** (`docker exec <container> env | cut -d= -f1`), never the values; then start the other services.
7. **Verify**: the old value is refused, the new one is accepted by the administrator and, afterwards, the API and the worker start (the code refuses a superuser, so they are expected to need the group 17 roles at this point), `db-verify` has no findings, and no container, log or image carries the old value.
8. **Revoke the exposure**: delete or archive the subagent transcript only with the owner's authorisation and after the rotation (a rotated value in an old transcript is harmless); record the date of the rotation in `docs/technical-debt.md` (TD-038) and close this incident.

Dependencies and risks: the rotation cannot be done before the roles exist without breaking the API and the worker (they use the administrator today); `docker compose up` on the real stack is not authorised in this task; the container recreation changes a running service and needs the owner's authorisation.

## Prevention

L31 in `docs/lessons-learned.md`. Every review prompt now says not to read or print the values of real `.env*` files and to answer configuration questions from the examples, from variable names (`cut -d= -f1`) or from masked output; the search for leaks uses counts and file names only.
