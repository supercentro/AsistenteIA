# Pre-push audit and CI readiness (J2), 2026-11-14 — NOTHING WAS PUSHED

Range audited: `origin/main..3152acb` (the 70 commits that `git push -u origin feature/database-least-privilege` would publish; `origin/main` = `3b312e4` is an ancestor of HEAD, the branch does not exist on the remote). 449 files, +38 393 / -144 lines. Method: every added line of every commit (`git log -p`, 242 557 lines) scanned with pattern rules, plus the real secret values compared in memory (never printed). The scanner is kept outside the repository because it reads the real env files.

| Check | Result |
|---|---|
| Remote | `origin` = `https://github.com/supercentro/AsistenteIA.git`, private, default branch `main`, the user has ADMIN; branch absent on the remote; 12 remote branches, none equal to this one |
| File names that look sensitive (`.env*` except examples, dumps, keys, `.pre-17b`, `Backups/`, credentials files) | none; the only tracked env-like files are the 8 `*.example` |
| Real env files | `backend/.env`, `backend/.env.db`, `backend/.env.worker`, `frontend/.env` exist locally and are ignored by git (`.gitignore` `.env`, `.env.*`) |
| PostgreSQL backups / binaries / files over 1 MB | none (no dump, no archive, no image, no document) |
| The seven untracked reference documents | in no commit of any ref; they stay untracked |
| Private keys, AWS/GitHub/Slack/OpenAI/Google tokens | 0 |
| The real secret values (administrator password, JWT secret) in added lines of the 70 commits / in tracked files at HEAD / in untracked files | 0 / 0 / 0 |
| JWT-like string | 1, in a pytest failure trace of group 7; its signature part is truncated and does not match the real JWT secret (HMAC checked, result printed as a boolean only) |
| URL-with-password pattern | 1 770 added lines, all synthetic: test fixtures (`tstadmin:<password>`, `CHANGE_ME`), shell templates (`$PA`, `%s`, `{ADMIN}`), documentation and masked output (`***`); none holds a value |
| Secret-like assignments | 83 added lines: field declarations (`SecretStr`), variable names, `*_not_a_secret` CI throw-away values, test accounts at `example.com` |
| Personal data | the Windows user name and profile paths appear in **2 evidence files** (24 added lines): `reports/group-12/windows-unit-full.txt` and `reports/group-17a/g17a-replica-output-run1-superseded.txt` (tool paths, temp folders, a session id). No personal e-mail address, no computer name. The static-test file only contains the patterns it searches for |
| Commit identity | the 70 commits carry the same author name as `main`; the e-mail of the commits is the one configured locally (the last commits of `main` use a `users.noreply.github.com` address): the owner should confirm it is the address to publish |

**Verdict of the scan: no real credential and no sensitive file; two residual items for the owner's decision** (the user name in two evidence files; the author e-mail of the new commits). Publishing is irreversible in practice (history, caches, forks of a private repository, logs).

## Workflow `.github/workflows/ci.yml` (reviewed, parsed, not run)

- Triggers: `push` (every branch) and `pull_request`; `permissions: contents: read`; no `${{ secrets.* }}` anywhere (the only `secrets.` text is Python's `secrets.token_urlsafe`); `persist-credentials: false`; actions pinned by tag (`checkout@v4`, `setup-uv@v5`, `setup-node@v4`), SHA pinning is not required on this repository.
- `backend` (30 min): PostgreSQL service with throw-away values, lint, format, mypy strict, unit and integration tests; the dependency audit is non-blocking. `frontend` (30 min): lint, format, typecheck, API types, coverage thresholds, build, Playwright against mocked responses. Both ran green on `main` (last run success).
- `privileges` (40 min): two PostgreSQL services created only for the job (ports 5433 and 5434, throw-away administrator password `*_not_a_secret`), `privilege_gate.sh` with `set -euo pipefail`; `assert_disposable_cluster.py` refuses a cluster that is not local, empty and exclusive and requires the two clusters to be different; bootstrap, migrations to 0006 with grants, `db-verify`, drift self-check and the role-bound suites run only on those clusters; `check_results.py` fails on any failed, errored or skipped test or fewer tests than the floors (60 / 400 / 480) and appends the table to the job summary (`$GITHUB_STEP_SUMMARY`); the summary step runs `if: always()`.
- Not proven: the job has never run on GitHub (TD-045); timing, runner networking and service readiness are the unknowns. Branch protection is unavailable on this plan (403), so a green `privileges` run is advisory, not binding.

## Command that would be run after the owner's explicit authorisation

```bash
git push -u origin feature/database-least-privilege      # branch only: no pull request, no force, no tags
gh run list --branch feature/database-least-privilege --limit 5
gh run watch <run-id> --exit-status
gh run view <run-id> --log > <outside-the-repo>/ci.log   # read it before copying any excerpt into the reports
```

Acceptance and failure handling: as in `ci-remote-proposal.md` (all three jobs green; the `privileges` summary shows every suite with at least its floor and none skipped; on failure no pull request, reproduce locally, fix test-first, push again). To undo the publication of the branch: `git push origin --delete feature/database-least-privilege` (the owner's decision; fetched copies and Actions logs cannot be recalled).

## Addendum (owner's decisions after the audit): sanitization of the local history, still nothing pushed

Decisions: do not publish the Windows user name or personal paths found in the two evidence files; keep the existing author e-mail of the commits.

- **Method**: `git filter-branch --index-filter` over `origin/main..HEAD` only; for the two files (`reports/group-12/windows-unit-full.txt`, `reports/group-17a/g17a-replica-output-run1-superseded.txt`) the blob of every commit is rewritten byte for byte except: the repository path becomes `<repo>`, the profile path `C:/Users/<name>` becomes `<home>` and any remaining occurrence of the user name becomes `<user>`. Line counts are unchanged (218 and 231), the test results in those files are unchanged. `origin/main`, the other local branches and the seven untracked reference documents were not touched. Recovery references kept locally: `refs/backup/pre-j2-sanitize` and `refs/original/refs/heads/feature/database-least-privilege` (both point at the pre-rewrite head; they are not published by a branch push and can be deleted once the owner is satisfied).
- **Effect**: 71 commits before and after (the audit commit included); the first 45 keep their SHA; the 26 from `1628bca` on were rewritten (author, e-mail, dates and subjects identical). The tree differs from the pre-rewrite tree only in those two files. References to the old short SHAs in 40 tracked documents (46 occurrences) were updated to the new ones in one follow-up commit.
- **Scan of the rewritten range**: user name 0 (blobs of every commit and added lines), profile path with the user 0, repository/course path in the two files 0, credentials and sensitive file names 0 (same results as above). **Not in the authorised scope and still present**: the course folder path (`…/Trabajo/Cursos/Liders/…`, no user name) in `reports/group-15/red-pg01.txt`, `reports/group-9/red-coverage.txt` and `reports/group-17a/expected/README.txt`; the synthetic `C:/Users/someone` fixtures and the regexes of the leak tests.
