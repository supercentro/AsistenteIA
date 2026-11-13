# Step 13: manual endpoint testing with curl on a disposable instance (2026-11-13)

Branch `feature/database-least-privilege`, code at `1628bca` (no functional code was changed in this step). Authorised scope: tasks 13.1 to 13.3. The development database `asistenteia`, its worker, volumes, `.env` files and images were not touched (the real `docker-compose.yml` was read, never modified, and `docker compose up` was never run on the real project); nothing was pushed; the new workflow has not run on GitHub Actions, so nothing here is remote validation. Evidence: `group-13/g13-output.txt` (the full log, secrets masked), `run_g13.sh` and `compose.g13.override.yml` (reproducible).

## 13.1 The disposable instance

| Item | Value |
|---|---|
| Docker project | `g13scratch`: its own network (`g13scratch_default`) and volume (`g13scratch_db_data`); no network, volume or credential of the real stack |
| Images | `asistenteia-backend:g13-branch` (target `api`, built from the working tree) for `bootstrap`, `migrate`, `backend` and `cli`; `asistenteia-worker:g13-branch` = the worker image of `main` with `backend/app` of this branch copied over it (`uv.lock` is unchanged, so the dependencies and the baked embedding model are the same). Both tags were removed at the end |
| Database | PostgreSQL 15.19 + pgvector 0.8.7, **not published**; database named `asistenteia` *inside the scratch cluster* (the compose commands fix that name); the real `asistenteia` and `asistenteia_test` were never connected |
| Real commands | `db-bootstrap`, `db-migrate` (Alembic to **0006** and the grants) and `db-verify` ran through the real Compose one-shots; the stack started with `up -d` (cold start, rc 0) |
| Identities | API as `asistente_app`, worker as `asistente_worker`, administrative command as `asistente_cli` (profile `cli`, run on demand), migrator `asistente_migrator`, administrator only in `db` and `bootstrap`; none is a superuser except the container administrator |
| Credentials | synthetic random values generated per run in an empty directory outside the repository, deleted at the end; never printed |
| Network exposure | the API only on `127.0.0.1:58734` (a free temporary port; never 8000, 5173 or 5442); PostgreSQL and the worker publish nothing; no frontend |
| Data | synthetic only (accounts `student1@example.com`, `teacher1@example.com`, ..., a course "Calculus", three tiny generated documents) |

## 13.2 Results: 101 checks, 101 passed, 0 failed (expected against obtained in the log)

HTTP code and business state (the `curl` commands are `curl -s -X <METHOD> http://127.0.0.1:<port>/api/v1<path> [-H "Authorization: Bearer <token>"] [-H 'Content-Type: application/json' -d '<json>'] [-F file=@<file>;type=<type>]`; the script prints each request and the check, and redacts passwords and tokens):

| Scenario | Request and result |
|---|---|
| Health | `GET /health` 200 `{"status":"ok"}` |
| Unauthenticated | `GET /users/me`, `GET /subjects`, `POST /subjects` 401 |
| Public registration | `POST /auth/register` 201, role `student`, stored role `student`; a payload that asks for `"role":"teacher"` 201 and **stored `student`**; duplicate email 409 and one row; invalid body 422 |
| Login and JWT | 200 with a token for both students; wrong password 401; `GET /users/me` 200 with the caller's id; tampered token 401 |
| Teachers by the administrative command | `docker compose run --rm -T --no-deps cli create-teacher --email ... --password-stdin` creates two teachers (stored role `teacher`); a duplicate is refused ("nothing was changed", one row); both teachers log in (200) |
| Consent | wrong version 422 `INVALID_CONSENT_VERSION` and nothing stored; current version 200 with the **stored version and a stored time**; again 200 (idempotent); a teacher 200; unauthenticated 401 |
| Subjects | student `POST /subjects` 403, nothing stored; teacher 201 and the stored row owned by that teacher; duplicate name 409, one row; list 200 (one subject); other teacher: list empty, `GET` 404, `DELETE` 404 and the subject still stored; non-enrolled student `GET` 404; unauthenticated 401 |
| Enrollments | student 403; other teacher 404; unknown student 404; enrol 201 and stored; duplicate 409, one row; second enrol 201; list 200 (two); student list 403; enrolled student `GET` subject 200; `DELETE` one 204 and the other stays; `DELETE` again 404; the removed student `GET` subject 404 |
| Documents | student upload 403; unauthenticated 401; other teacher 404; `.exe` upload 415; nothing stored by the refused ones; TXT, Markdown and PDF uploads 202, persisted; the worker (role `asistente_worker`) processed all three to `ready`; chunks created, the PDF chunks carry page numbers; no job keeps the uploaded bytes and no lease remains; teacher list 200 (3 ready); student list 403; other teacher list 404; refused deletes (other teacher 404, student 403) leave the document; `DELETE` 204 removes the document, its chunks and its job; `DELETE` again 404 |
| Subject deletion | `DELETE` 204; the subject, its enrollments, documents, chunks and jobs are gone; again 404; the four accounts remain |

After every write the script read the scratch database with the administrator (read-only statements) and compared the stored state; the final state of the scratch database was `users=4 subjects=0 documents=0 chunks=0 jobs=0`. No password, token or document content is in the output (a scan for token and password patterns found nothing).

## 13.3 Isolation, secrets and `db-verify` (same run)

- The API role is refused (`permission denied`) when it inserts a teacher, updates `users.role`, creates a table or a role, and when it connects to the database `postgres`. The worker is refused on `users`, `subjects`, deleting `documents` and DDL. The CLI role is refused on `documents`, `ingestion_jobs` and updating `users.role`, and can read the accounts. Nine of nine unauthorised statements were refused; no forged table, role or user exists afterwards.
- Sessions during the run: `asistente_app=1`, `asistente_worker=1`; no runtime or migrator role is a superuser.
- Secrets by service (names only): `db` holds `POSTGRES_*`; `backend` `DATABASE_URL`, `JWT_SECRET`, `CORS_ORIGINS`; `worker` its `DATABASE_URL` and limits and no JWT; `bootstrap` the administrator URL and the four role passwords; `migrate` `MIGRATION_DATABASE_URL`; `cli` `CLI_DATABASE_URL` only.
- `db-verify`: no findings, before the tests and after them.
- Published ports at the end: only the API on `127.0.0.1:58734`.

## Cleanup

Identity checked before removal: containers `g13scratch-worker-1`, `-backend-1`, `-migrate-1`, `-bootstrap-1`, `-db-1`; network `g13scratch_default`; volume `g13scratch_db_data`; none of them outside the project. `docker compose down -v --remove-orphans` removed them (containers, networks and volumes left: 0), the two temporary image tags were removed, the other containers of the machine (the real `asistenteia-db-1`, `asistenteia-worker-1`, `asistenteia-postgres` and other projects) were identical before and after, and the credential files were deleted.

## Incidents and deviations

- The first attempt failed before any request: the script passed the build context to the Windows Docker client in MSYS path form, so the images were not built, the stack did not start and every request returned 000. Nothing was left behind (checked), no code was involved; the script now uses a Windows path and fails explicitly if a build fails. The log of that attempt was overwritten by the passing run, which is the one recorded.
- No functional code was changed and no expected result differed from the obtained one: there were no regressions to analyse.
- The development database is read-only verified after the run (`group-13/snapshot-dev-after.txt`, `snapshot-dev-diff.txt`): the deterministic part is identical to the baseline of step 12; revision 0005, no drift, no new role, 0 rows.
- Limits: it exercised the API as built from this branch on a scratch cluster, not the real development stack (that happens, if authorised, in groups 16 and 17); the worker image is main's image plus this branch's code, which is equivalent only while the lock file is unchanged (it is); the real browser frontend was not started (not applicable to this change). GitHub Actions has not run the workflow.
