# Group 2 Report - Dependency and Image Pin (tasks 2.1, 2.2)

- Date: 2026-10-28
- Change: documents-schema-pgvector
- Agent: Claude Code (Sonnet 5.5), main session
- Scope: add the `pgvector` Python package and pin the database image. Models, repositories and migration `0004` were **not** implemented or run.

## Preconditions
- PR #7 head `e3e33a8`, CI green (backend and frontend, push and pull request), mergeable `CLEAN`, branch `feature/documents-schema-pgvector`, clean tree.
- Spike (group 1) hypotheses confirmed; incidents I1-I4 resolved in the artifacts (commit `5fe11b2`).

## Versions

| Item | Before | After |
|---|---|---|
| Python package `pgvector` | absent | `0.5.1` (`>=0.5.1,<0.6`, locked in `uv.lock`) |
| SQLAlchemy / psycopg / Alembic | 2.1.6 / 3.3.6 / 1.20.1 | unchanged |
| Database image (Compose and CI) | `pgvector/pgvector:pg15` (floating) | `pgvector/pgvector:0.8.7-pg15` |
| Image digest | `sha256:47af0b65960b14f1c6945aa4ccae37836c632e9a6fe0eea9160936e616e5b2e9` | identical digest |
| PostgreSQL / pgvector extension | 15.19 / 0.8.7 | 15.19 / 0.8.7 (`default_version` = `installed_version` = 0.8.7) |

## Changes
1. `backend/pyproject.toml` and `backend/uv.lock`: one new dependency, no other package changed (commit `6e105b4`).
2. `docker-compose.yml` and `.github/workflows/ci.yml`: image tag pinned; `docs/development_guide.md`: pin, upgrade procedure and troubleshooting text.
3. The magnitude experiment script is stored next to its report so the experiment can be repeated when pgvector changes.

## Data preservation evidence
The development database holds no application rows (`users`, `subjects`, `enrollments` all 0), so a canary table was used:
1. Before: `alembic_version` = 0003; tables `alembic_version, enrollments, subjects, users`; counts 0/0/0; extension 0.8.7; databases `postgres, asistenteia, asistenteia_test`.
2. A table `g2_canary` with one row was created in `asistenteia`.
3. `docker compose up -d db` recreated the container with the new tag (the image ID did not change).
4. After: the canary row was intact, `alembic_version` = 0003, counts 0/0/0, extension 0.8.7, PostgreSQL 15.19, same three databases, volume `asistenteia_db_data` (created 2026-10-27) unchanged.
5. The canary table was dropped; tables and counts equal the starting state.
`asistenteia_test` is empty between runs by design (the suite drops and truncates its own tables).

## Rebuild and runtime
- `docker compose build backend` then `up -d backend`: backend answers `/api/v1/health` with 200; inside the container `pgvector 0.5.1` imports (`pgvector.sqlalchemy`).
- `docker compose exec backend alembic current` = `0003 (head)`; `alembic check` = "No new upgrade operations detected." (the `pgvector` import has no effect on the existing models).
- Frontend container untouched.

## Quality gates (backend, after the changes)
- `ruff check` and `ruff format --check`: clean (90 files).
- `mypy --strict app tests`: no issues (89 files).
- `pytest`: 494 passed (before and after the image recreation).
- `pip-audit`: no known vulnerabilities.
- `openspec validate documents-schema-pgvector --strict` valid; `openspec validate --all --strict` 13 of 13.
- Frontend gates not rerun: no frontend file or dependency changed. CI runs them on the PR.

## Status of the spike incidents
| Incident | Decision | State |
|---|---|---|
| I1 `alembic check` blind spots | keep `alembic check`; catalog assertions in migration tests | Specified (spec `document-storage`, tasks 3.1 and 3.4); implemented in group 3 |
| I2 data in database error text | never log or return `exc.orig`; controlled errors; log spies with real SQL exceptions | Specified (both specs, task 3.2b and 5.2); implemented in groups 3 and 5 |
| I3 extreme magnitudes | evidence-based range `1e-6 <= norm <= 1e6` (validation + CHECK) | Experiment done (`2026-10-28-magnitude-experiment.md`); specs and design updated; implemented in groups 3 and 5 |
| I4 hand-finished migration | explicit import, `CREATE TYPE`/`DROP TYPE`, no edit of published migrations | Specified (design); implemented in group 3 |

## Pending risks
- Group 2 pins the image but CI on the PR must confirm that the pinned tag works in GitHub Actions (checked after the push).
- The valid vector range depends on pgvector 0.8.7; upgrades must rerun the experiment (documented in the development guide).
- The norm-range CHECK slightly narrows what an embedding model may store (documented norm range `1e-6..1e6`); real model outputs (norm about 1 to 20) are far inside it.
- Write-path error translation and the shared validation helper are inherited by change 6.

## Outcome
- Tasks 2.1 and 2.2: PASS. Groups 3 to 12 not started.
