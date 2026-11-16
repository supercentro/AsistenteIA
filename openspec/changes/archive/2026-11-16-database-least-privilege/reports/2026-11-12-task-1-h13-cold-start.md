# Task 1: cold start of the planned Compose flow (H13)

Date 2026-11-12. Branch `feature/database-least-privilege` at `3b312e4` (`main`). Executed by the agent; no code, migration, `docker-compose.yml` or `.env` file of the project was changed.

## What was run

`reports/h13/run_h13.sh` reads the real `docker-compose.yml` and layers `reports/h13/compose.h13.override.yml` on it, under its own Compose project (`g27h13`): own network, own named volume, no published port, temporary random credentials in a directory outside the repository, no real `.env` file. The real images `asistenteia-backend:latest` and `asistenteia-worker:latest` (code of `main`) run the real API and the real worker; `reports/h13/bootstrap_standin.py` and `migrate_standin.py` stand in for the planned `db-bootstrap` and `db-migrate`, which do not exist yet (they follow the behaviour required by the `database-roles` spec: administrator with `search_path = pg_catalog`, client-side SCRAM verifiers, `RESET ALL`, `PUBLIC` closed on every database, global default privileges, extension; Alembic then the grants in one transaction). The frontend is excluded by a profile. Free memory before the valid run: 6.06 GB (requirement: 6 GB).

Evidence files: `h13/h13-output.txt` (the full run with the memory gate satisfied; valid for rounds A, B and D, its round C is defective and is superseded), `h13/h13-output-roundC.txt` (round C repeated after fixing the harness defect; configuration only, nothing started, run with about 5 GB free because it starts no container), `h13/h13-output-unplanned-run.txt` (see Deviations). The committed `run_h13.sh` is the later version (round C fixed); `h13-output.txt` was produced by the earlier one. The outputs contain variable names and counts, never values.

## Results

| Scenario | Result |
|---|---|
| Configuration | valid; 0 published ports; 0 rendered references to the real `backend/.env*` files; `docker-compose.yml` unchanged |
| A1 cold start from nothing (no container, no volume) | `up -d` rc 0: `db` healthy -> `bootstrap` exited 0 -> `migrate` exited 0 (`Running upgrade 0004 -> 0005`, 14 grants in one transaction) -> backend healthy and worker healthy; sessions by role `asistente_app=1`, `asistente_worker=1`; revision `0005`; the three roles have minimal attributes; no other database is open to `PUBLIC` |
| A2 real write under the application role | `POST /auth/register` -> HTTP 201, one row stored, role stored `student`, row removed afterwards |
| A3 worker idle for 20 s | 0 log lines about database errors or permission problems |
| A4 secrets by container (names; values searched, not printed) | `db`: `POSTGRES_*`, holds the administrator password; `bootstrap`: all passwords (by design); `migrate`: migrator URL only (it still needs `JWT_SECRET` today because Alembic reads the API settings, fixed by task 3); `backend`: application-role URL and JWT, no administrator or migrator password, no `TEST_DATABASE_URL`; `worker`: worker-role URL only, no JWT |
| A5 second `up -d` | the finished `bootstrap` started again (`ALTER` instead of `CREATE`), the ACL/catalog fingerprint is equal, the backend and the worker containers were not recreated |
| A6 environment change | `docker compose restart worker` kept the old `LOG_LEVEL`; a plain `up -d` recreated the worker with the new value |
| A7 credential rotation | after changing the worker password in both files and running `up -d`: the worker was recreated and healthy, the bootstrap applied the new password, the old password was refused by the server and the new one logged in as `asistente_worker` |
| B migrate fails (wrong migrator password) | `up -d` rc 1, `migrate` exit 1; `backend` and `worker` were **created but never started** (state `created`, 0 running); after fixing the password `up -d` rc 0 and both became healthy |
| C bootstrap in an inactive profile (configuration only; from `h13-output-roundC.txt`) | without the profile: `service "migrate" depends on undefined service "bootstrap": invalid compose project`; with `--profile admin`: valid |
| D second cold start from nothing | same result as A1 (repeatability); teardown left no container, volume or network in any round |

Conclusion: the planned flow works as the `dev-environment` delta specifies, and the three Compose behaviours that shape the design are now recorded with a reproducible harness (one-shots restart on every `up`; `restart` does not apply a changed environment; a dependency on a service in an inactive profile invalidates the project).

## Limits

- The bootstrap and migrate are stand-ins: they prove the Compose behaviour, not the commands. Task 6.4 repeats the run with the real commands.
- The API ran from the image, not from the source bind mount of the real file (the override empties the mounts); the residual risk of the writable mount is not exercised.
- `bootstrap` shows `EMBEDDING_MODEL_PATH` among its variables because the worker image defines it; it is not a secret and goes away when the real command uses the backend image.
- The frontend was not started.
- A4 inspects the environment files generated by the harness. That the **real** `backend/.env` still holds the administrator password and `TEST_DATABASE_URL` is recorded by the spike (tag `A-04`); the split of the real files is proved by tasks 3.1, 3.3 and 6.4.

## Deviations (recorded, no data or service affected)

1. **An unplanned second run with the memory gate bypassed.** After the valid run, a fix to the harness inserted the `H13_ONLY=C` shortcut after rounds A and B; the shortcut run therefore executed A and B again with about 5 GB free (4.98 GB measured by the script of the round C that followed) instead of the 6 GB required. It finished normally, left nothing behind and gave the same results; I stopped the task as soon as I noticed and kept its output as `h13-output-unplanned-run.txt`. The script was fixed (shortcut before round A, separate output file, round C writes no container).
2. Harness defects fixed along the way, none in the design: the first attempt aborted before starting anything (a comment in `.env.worker.example` mentions `CHANGE_ME`, and the run directory was checked before it was created); round C of the first run used an incomplete override file and reported a file error instead of the profile message (the repeated round C in `h13-output-roundC.txt` is the evidence); the round B text said "not created" while Compose creates the dependants and never starts them.
3. Free memory after the valid run was 4.59 GB, i.e. below 6 GB; the other processes of the host (WSL, browsers) account for the difference.

## Cleanup

`docker compose -p g27h13 down -v` in every round: 0 containers, 0 volumes and 0 networks left; the environment files of the run were deleted; the real stack (`asistenteia-db-1` at revision `0005`, `asistenteia-worker-1`) was not touched and stayed healthy.
