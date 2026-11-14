# Classification of the 14 secret-looking additions (final preflight before 17B, 2026-11-13)

**No value is printed or stored here.** The analysis ran in memory (`classify_secrets.py`, kept outside the repository because it reads the real files): it read, without printing them, the real administrator password (`POSTGRES_PASSWORD`, `DATABASE_URL` passwords of `.env` and `.env.worker`) and the real `JWT_SECRET`, and compared every candidate and every added line of the local history with them. The two scopes are the commits a push would publish (`main..HEAD`) and every local ref.

## Result

| Question | Answer |
|---|---|
| How many matches in the commits a push would publish (`main..HEAD`, the scope of 17A, without `openspec/`)? | **14**, in 8 files, all of the kind "URL with a password" |
| Is any of them a real credential? | **No.** The comparison with the real administrator password and the real JWT secret found **0** added lines in the whole local history and **0** files in the working tree (tracked or not ignored, reports and the seven untracked documents included) that contain a real value |
| Real values compared | 6 (names not printed) |
| In the Git history? | yes, all 14 are in local commits; **none is on the remote** (`git merge-base --is-ancestor` against `origin/main`: the commits are local only) |
| Required action | none for these 14; see "Broader scope" for 11 more that the owner should know |

## The 14 matches (file, kind, classification, commit, count)

| File | Kind | Classification | Commit | Count |
|---|---|---|---|---|
| `backend/tests/integration/test_least_privilege_coverage.py` | URL password | synthetic test fixture (throw-away URL of a test) | `2ae972b` | 1 |
| `backend/tests/unit/test_db_admin_commands.py` | URL password | synthetic test fixture | `c6f5f3a` | 1 |
| `backend/tests/unit/test_db_admin_connection.py` | URL password | synthetic test fixture | `c6f5f3a` | 1 |
| `backend/tests/unit/test_db_admin_target_guard.py` | URL password | synthetic: the value says so (`never-used-...`) | `e0aafd3` | 1 |
| `backend/tests/unit/test_migration_settings.py` | URL password | synthetic test fixture | `71a5be0` | 4 |
| `backend/tests/unit/test_superuser_refusal.py` | URL password | synthetic: the value says so (`never-printed-...`) | `aa515b5` | 1 |
| `backend/tests/unit/test_teacher_provisioning.py` | URL password | synthetic test fixture | `f75edad` | 2 |
| `backend/tests/unit/test_test_database_environment.py` | URL password | synthetic test fixture | `a95b29e` | 3 |

Why a pattern hit at all: these fixtures need a password of at least 16 characters because the settings classes reject shorter ones, so the tests carry long made-up values. They are not false positives of the pattern but they are not secrets either.

## Broader scope (every local ref), for completeness

Another 11 matches exist in older or other places; none equals a real value either:

| File | Kind | Classification | Where it lives |
|---|---|---|---|
| `.github/workflows/ci.yml` | `KEY=value` and URL password (6) | synthetic, named as such (the CI throw-away database password) | `e0e115a` is **already on `origin/main`** (the CI password has been public to the remote since the beginning; it protects an ephemeral service container); `501a8f3` is local |
| `docs/development_guide.md` | `KEY=value` (1) | synthetic, named as such (an example) | `d4ff154`, already on `origin/main` |
| `openspec/.../group-11/mutate_regression.py` | URL password (2) | synthetic (made-up URLs of a mutation script) | `58f633c`, local |
| `openspec/.../group-17a/tools/test_prepare_env_files.py` | `KEY=value` (2) | synthetic: made-up `not-a-real-secret-...` JWT value and a made-up administrator password of the self-test | `56ef0a7`, local |

## Verdict for the push

**GO from the point of view of secrets**: no real credential and no value that could be one is in any local commit or in the working tree; nothing real was ever in a commit. This does not cover the credential of the incident of 2026-11-13 (its value lives only in a local subagent transcript outside the repository, see `../2026-11-13-credential-exposure-incident.md`), which the scan also looked for and did not find in the repository.

Caveats: the scan covers the added lines of the local history and the working tree, not the Docker images, the container logs, the `~/.claude` transcripts or any other machine; the 14 + 11 fixtures are public once pushed (harmless). A secret scanner such as `gitleaks` would be a stronger gate for the remote history; it was not installed and was not added.
