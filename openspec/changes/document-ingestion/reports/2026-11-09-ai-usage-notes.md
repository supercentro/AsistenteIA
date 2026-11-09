# AI usage notes: document-ingestion

Working notes for a later `prompts.md` proposal (that file needs the user's approval and is not touched here). Tool: Claude Code (Sonnet 5.5), OpenSpec workflow, SpecBoot skills.

**Status of this file: summaries.** The literal user prompts are in `reports/2026-11-09-user-prompts-verbatim.md`, copied unchanged from the session transcript. This file keeps short notes written afterwards by the assistant; nothing here is a quotation unless it is in quotation marks and says so. Created on 2026-11-09 (task 0.3), after groups 1 and 2; the notes of those groups are written from the reports and the commit history, not from memory.

## Sources used for these notes
- Reports of the spike in this folder (`2026-11-08-spike-*.md`) and of group 2 (`2026-11-08-group-2-dependencies-and-images.md`, `2026-11-08-tdd-evidence.md`).
- Commit history of `feature/document-ingestion` (`git log main..HEAD`).

## Decisions by the user (summaries)
- Exploration (2026-11-08): read-only exploration of the ingestion change; scope confirmed; decisions D1 to D10 (separate worker, persistent PostgreSQL queue, durable `202`, local CPU embedding model, limits and quotas, duplicates allowed, strict UTF-8, token-based chunking, isolated PDF parsing, stable error codes) approved with additional mandatory decisions (bytes in the database and the WAL consequence, hard limits under concurrency, fencing tests, calibrated model evaluation, conditional `408`).
- Planning approval (2026-11-08): architecture approved with mandatory adjustments; spike prepared but not run until a later authorisation.
- Spike authorisation: publish the planning, run only tasks 1.1 to 1.10 in isolated resources, stop on a failed hypothesis.
- Spike approval (2026-11-09 UTC): model approved for the MVP with a later evaluation on real material; chunking 100/20 kept; API and worker images separate (362 MB and 2.80 GB as reference); `EMBEDDING_THREADS` from the CPU quota; worker batch 16, lease 120 s, deadline 600 s with safe renewal and fencing; PDF limits 768 MB, 20 s CPU, 30 s wall clock, 8 MB output, 300 pages; queue 100, 200 MB, 4 uploads in flight; upload deadlines 120 s total and 20 s idle; `pypdf` 7.0.0 as candidate; PostgreSQL timeouts 15 s, 60 s and 30 s; no `VACUUM FULL` in the sweep.
- Group 2 and groups 0 and 3: group 2 approved (the 3.22 GB worker image accepted as the initial size; the temporary Compose profile kept until group 8); groups 0 and 3 authorised together.

## AI findings and corrections during the change (summaries)
- Spike: `torch` must use as many threads as the CPU quota (about 33 times slower otherwise); the default `torch` wheel makes the worker image 9.4 GB; the model ignores tokens beyond 126; FastAPI 0.162 sends the response before the `yield` dependency exits, so the explicit commit before `202` is required; Starlette answers multipart errors with `400`, not the contract's `422`; `bytea` of 10 MB writes about 21 MB of WAL and the bytes remain in table files, WAL and base backups after clearing.
- Planning update: the update replaced the sweep's `VACUUM FULL` by autovacuum plus monitoring, added the lease heartbeat and fencing tests, and differentiated the `422` reasons.
- Group 2: the advisory list of `pypdf` was read in full (five advisories fixed only in 7.0.0, which settled the version); adding `langchain-core` brought `httpx2`, which changed the types of Starlette's `TestClient` and broke `mypy --strict` until `httpx2` joined the dev group; two worker image builds failed with transient DNS errors and a lower download concurrency fixed them; a settings test of the assistant was wrong (deadline below lease) and was corrected, not the rule.
- Process: group 0 was not executed when the branch was created; it was authorised on 2026-11-09 and recorded late, with the deviation stated in `2026-11-09-group-0-baseline.md`.

## For a later `prompts.md` proposal
Candidate significant interactions: the exploration with decisions D1 to D10; the spike (hypotheses H1 to H10, none failed); the planning update; the group 2 dependency and image work. The wording must come from the literal record, not from this file.
