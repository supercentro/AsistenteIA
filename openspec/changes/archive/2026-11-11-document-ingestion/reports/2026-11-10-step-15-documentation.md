# Group 15: technical documentation

Branch `feature/document-ingestion`. Task 15.1 (with the `update-docs` skill), plus the correction of the Migration Plan authorised by the user (commit `b1cc470`, through `/opsx:update`). No group after 15 was run; migration `0005` was not applied to the development database.

## Migration Plan (`design.md`)
Item 1 of "Migration Plan" said the development database would be migrated in the verification group after a backup. It now records that `0005` was verified on the isolated test database, on a scratch database and on a disposable PostgreSQL container (group 13); that `asistenteia` stays at `0004`; that no backup or restore of it was performed; and that applying `0005` to it later needs the user's independent approval, a verified backup (with a restore test) and a recovery procedure. Architecture and scope are unchanged.

## Documents updated
| Document | What changed |
|---|---|
| `docs/backend-standards.md` | Stack rows (pinned `pypdf`, `python-multipart`, model baked into the worker image); the documented exception to "services do not commit" (explicit commit before `202`/`204`); the Ingestion section rewritten from the stale "background task" text to what exists (decision order, durability, worker lease/fencing/lock order, PDF isolation, text normalisation, chunking 100/20 with the 128-token limit, embeddings, closed failure catalogue, logs); failure row; privacy note on temporary bytes; measured performance |
| `docs/development_guide.md` | Every ingestion variable (all of `.env.example` is present), the `worker` service and the model image, migration `0005` and the rule for the development database, a new "Document ingestion" section (run/stop, limits and their effects, database timeouts, `EMBEDDING_THREADS`, Linux-only PDF child, pins and the `pypdf` upgrade rule, bytes in dead tuples/WAL/backups with the queries, `VACUUM FULL` as manual maintenance, how to verify without touching the development database), the `realmodel` command, a Linux note, two troubleshooting entries |
| `docs/data-model.md` | Already described `ingestion_jobs`, `error_code`, the 12 codes and the cascades; two stale pointers now point to the real sections |
| `docs/api-spec.yml` | Reviewed, **no change**: it already holds the final upload/list/delete contract with all status codes and `details.reason` values; `npm run check:api-types` ("types up to date") and the contract tests confirm the generated types and the implementation agree |
| `docs/technical-debt.md` | TD-023 and TD-027 resolved with evidence; TD-024 untouched; new TD-029 to TD-037 |
| `docs/lessons-learned.md` | Statuses of L19 to L22 brought up to date; new L24 to L27 |

## Consistency checks
- All 33 defaults of `config.py` equal `.env.example` (script) and each variable of `.env.example` appears in the development guide (script). The numbers of the guide and the standards (10 MB, 50 documents, 100 jobs, 200 MB, 4 uploads, 120/20 s, 3 attempts, 120 s lease, 600 s deadline, 768 MB, 300 pages, 2,000 chunks, 15/60/30 s) match the settings; the specs name the settings and state the same values where they give numbers.
- The SQL of the retention queries was run against a disposable PostgreSQL 15 container and returned rows without error (the table was a stand-in with the same name).
- `openspec validate document-ingestion --strict` valid; `--all --strict` 15 of 15.

## Technical debt
- **TD-023 resolved.** Evidence run in the Linux image against PostgreSQL: the cap of 50 documents (`409`), the cap of 2,000 chunks (`TOO_MANY_CHUNKS`, also seen with a real 600 KB upload), the upload, queue, pending-bytes and in-flight limits, and the statement and idle-in-transaction timeouts (the engine tests, including a statement cancelled over the timeout). One subject can hold at most 50 x 2,000 = 100,000 chunks. The search cost with very large corpora stays in TD-022 (change 12).
- **TD-027 resolved for the ingestion flow.** The normaliser, the chunker and the service reject content with no visible character. The flow-level evidence did not exist for look-alike blanks, so a test was added (`test_ingestion_service.py::TestFailures::test_text_that_only_looks_blank_is_rejected_before_the_database`, 4 cases: U+00A0, U+0085, zero-width/U+2003/U+FEFF, bidirectional marks). It passed on its first run (existing behaviour) and fails when the visibility test is replaced by an ASCII strip (mutation: 2 of 4 cases fail; source restored, diff empty). The CHECK of `document_chunks` is unchanged by decision.
- **TD-024** unchanged (the helper `validate_embedding` that ingestion reuses is the one the entry describes).
- **New:** TD-029 bytes in WAL/backups (Medium), TD-030 PDF isolation bounded and Linux-only, including that the Compose worker receives the whole `backend/.env` (Medium), TD-031 PDF variety, TD-032 no OCR (accepted), TD-033 embedding model validated on a small corpus (Medium), TD-034 no deduplication or fairness, TD-035 upload limiter in memory (TD-002 family), TD-036 Dependabot alert #1, TD-037 timing-sensitive tests. Each row names impact, current mitigation, the change that resolves it and the status.

## Dependabot alert #1 (TD-036)
`npm ls`: `minimatch` 10.2.6 is reached through `typescript-eslint` 8.72.1 -> `@typescript-eslint/typescript-estree` 8.72.1 (other copies, 3.1.5 and 5.1.9, are outside the vulnerable range `>=7.0.0 <11.0.1`). Advisory GHSA-g3hv-75wg-m249: denial of service by globparts amplification, moderate. `npm audit` lists 7 moderate findings, all the same chain. The registry on 2026-11-10: latest stable `typescript-eslint` 8.72.2 (affected, depends on `minimatch ^10.2.2`); only the prerelease `8.72.3-alpha.7` depends on `^11.0.1`; `minimatch` 11.0.1 supports Node 18, 20 and 22 or later. `npm audit fix --force` would propose `typescript-eslint` 8.36.0, a downgrade, and was not run. **No dependency was changed.**

Recommendation for task 17.3, in this order: (a) wait for and apply a stable `typescript-eslint` that depends on `minimatch >= 11.0.1`, then run `npm audit`, lint, typecheck, tests and build and commit it separately; (b) if none is available when the change closes, ask the user to approve an `overrides` entry for `minimatch` 11.0.1 or later (a major version, with the same checks); (c) otherwise the user's formal acceptance, written in `docs/technical-debt.md`. The alert is not dismissed.

## Lessons (L24 to L27)
L18 to L23 reviewed: their problems and evidence still hold; the statuses of L19 to L22 changed from pending to implemented/accepted because the pending items were done (CI on Linux, worker lock order, heartbeat, operations guide and TD-029). New lessons, each verifiable and not covered by an earlier one: L24 (the response leaves before a `yield` dependency exits; explicit commit), L25 (a late edit after the last green gate broke CI), L26 (files that no test reads and test seams), L27 (verification tasks and the development database). Candidates not recorded because an existing lesson covers them or they are one-off: heredoc and quoting mishaps (L15), Windows/Linux differences (L19), the mutation harness (L23), coverage by exclusion rules.

## Not done, by scope
- `docs/base-standards.md` was not touched. L18 left a decision open (adding `--no-cache` to section 9.6) and L25 suggests turning the "repeat the gates after the last change" practice into a rule; both need the user's decision, since `base-standards.md` is outside this group's list.
- `readme.md` and `prompts.md` untouched; the seven reference documents untouched.

## Results
Targeted tests (ingestion service, engine timeouts, quota and pending-bytes, normaliser, chunker): 159 passed. Gates after the last change: `ruff check --no-cache` clean, `ruff format --check` 169 files, `mypy --strict app tests` 169 files, `pip-audit` no known vulnerabilities; frontend `check:api-types` up to date.
