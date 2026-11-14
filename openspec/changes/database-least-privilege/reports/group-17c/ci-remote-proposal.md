# Proposal: first remote validation of the `privileges` job (group 17 final preflight; NOT executed)

Prepared with read-only questions to GitHub (`gh repo view`, `gh api .../actions/permissions`, `.../branches/main/protection`, `gh workflow list`, `git ls-remote`, `gh run list`). **Nothing was pushed, no pull request was opened, no setting was changed.** It complements `../group-17a/ci-first-run.md`, which describes what the three jobs do and the acceptance numbers.

## Facts found on the remote (read only, 2026-11-13)

| Fact | Value | Consequence |
|---|---|---|
| Repository | `supercentro/AsistenteIA`, **private**, default branch `main`, the user has `ADMIN` | the owner can push, delete a branch and read runs |
| GitHub Actions | enabled, all actions allowed; "SHA pinning required" is off | the workflow runs as soon as a branch with `.github/workflows/ci.yml` is pushed; mutable action tags are allowed |
| Workflows | `CI` and `Dependency Graph` are active | both may run on a push; only `CI` matters here |
| `main` | last three runs of `CI` green (latest at `3b312e4`); 62 + 1 = 63 commits behind this branch by the local view | the baseline workflow is healthy |
| **Branch protection** | the API answers **403 "Upgrade to GitHub Pro or make this repository public to enable this feature"** | **the `privileges` job cannot be made a required check on this private repository with the current plan.** The gate would be advisory, not binding, until the plan changes or the repository is made public (rulesets are subject to the same limit). TD-045 must say so; the control becomes a manual rule: no merge to `main` without a green `privileges` run, written in the pull request checklist |
| Other branches | many `feature/*` and `docs/*` branches exist on the remote | pushing one more branch is routine |

## Proposal (for the owner to authorise; commands for the day)

1. **Before the push** (read-only, local):
   - `git status` clean apart from the seven untracked reference documents; `git log -1` recorded; `openspec validate --all --strict`; the unit and integration commands of the development guide green.
   - The classification of secret-looking additions (`g17c-secret-classification.md`): no real value in any local commit or in the working tree. **If that file says NO-GO, do not push.**
   - Decide the retention of the branch: the push publishes 63 commits (reports, evidence, tools; no backups, no `.env`). Anything in them becomes remote history.
2. **Push the branch only**, without a pull request (this fires the `push` workflow once and not the `pull_request` one):
   ```bash
   git push -u origin feature/database-least-privilege
   ```
3. **Watch** (read-only commands):
   ```bash
   gh run list --branch feature/database-least-privilege --limit 5
   gh run watch <run-id> --exit-status
   gh run view <run-id> --log > <TMP>/ci-privileges.log      # keep it OUTSIDE the repository first, read it, then copy the clean excerpt into the reports
   ```
   Expected duration: `backend` about 5 to 10 minutes, `frontend` about 5 minutes, `privileges` well under 40 minutes (the local steps took about 54 s, 124 s and 4 min). A private repository consumes the free-plan minutes of the account (about 20 to 30 minutes per run); a re-run costs the same.
4. **Acceptance** (all three): jobs `backend`, `privileges` and `frontend` green; the `privileges` summary shows every report present with at least the floors (unit 60, role suites 400, roles mode 480) and none skipped; counts in line with `ci-first-run.md` (about 149, 439 and 484).
5. **If it fails**: do not open a pull request, do not merge. Keep the log in `reports/`, reproduce locally with the Linux runner scripts of groups 15 to 17 or `group-10/run_gate_local.sh`, fix with a failing test first, push again (each push is a new run). A red run for an infrastructure reason is re-run once (`gh run rerun <id> --failed`) and recorded as such.
6. **Undo the publication if needed** (the owner's decision, not automatic): `git push origin --delete feature/database-least-privilege` removes the branch; commits that were already fetched elsewhere, and the Actions logs, cannot be recalled.
7. **After a green run**: the owner decides the pull request. Without branch protection the merge rule is procedural: the pull request description must link the green `privileges` run, and nobody merges with a red or missing one.

## Risks and open points

- The workflow and its scripts were validated only locally; this run is the first remote evidence (TD-045). Timing, runner networking and the readiness of the service containers can differ.
- Free-plan limits: minutes, and the impossibility of required checks; upgrading the plan or making the repository public are decisions outside this change.
- `actions/*@v4`, `astral-sh/setup-uv@v5` are mutable tags (allowed here); pinning by SHA remains in TD-045.
- A push does not deploy anything. `docker-compose.yml` and the application code are not affected by the run.
- The CI `backend` job runs the ordinary integration tests with `ALLOW_SUPERUSER_DATABASE_ROLE=true` for the child processes (15.2): if a test fails with "refusing to start" the fixture must pass `superuser_exception()`.
