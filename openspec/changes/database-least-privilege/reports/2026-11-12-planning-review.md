# Independent review of the planning artifacts (2026-11-12)

Reviewer: a separate subagent with a clean context, read-only (no Docker, no database, no `.env`, no reference document), following the `adversarial-review` skill applied to planning documents and evidence. Scope: `proposal.md`, `design.md`, `tasks.md`, the six spec deltas, the reports, the H13 harness and the spike evidence, against the code, the main specs, `openspec/config.yaml` and `docs/openspec-tasks-mandatory-steps.md`.

**Verdict: PASS WITH GAPS** (accept the planning artifacts). The reviewer verified: the diff against `main` is empty and the working tree holds only this change folder and the seven untracked reference documents; the MODIFIED requirements keep their exact headers and all original scenarios; the owner decisions D1 to D8 and the instructions on the consent commit and the teacher separation are reflected without implementing them; the traceability matrix covers every requirement; `tasks.md` has Step 0 first, the mandatory steps, TDD ordering, a migration task with downgrade for the optional `0006`, the adversarial review before the real run, only groups 0 and 1 marked done, group 8 blocked and groups 16 and 17 needing separate authorisation; the claims about the code (statements of the worker, `users.role` without default, explicit commits in the document endpoints and the implicit one in consent) match; the Task 1 report matches the output and no evidence file holds a secret value.

## Findings and dispositions

| ID | Sev | Finding | Disposition |
|---|---|---|---|
| C-01 | Medium | Scenario said the application role holds no `DELETE` on `enrollments`, which the matrix grants | Corrected in `database-roles`: no `DELETE` on `document_chunks` or `ingestion_jobs`; `enrollments` `DELETE` is for the unenroll endpoint |
| C-02 | Medium | `role-based-access` delta said the mechanism was decided; DD-9 is pending; no archive rule; option A adds a fifth identity | Delta text shortened (no status note), "pending" and the archive rule and the amendment of "Four database identities exist" recorded in `design.md` (Open Questions) and at the top of `tasks.md` |
| C-03 | High | Evidence cited for adoption, rollback, catalog readability, connection limit and test-layer effects is not in the kept results (those scripts ran in the first run) | Spike summary and traceability matrix now say "observed in the first run, output not kept" and name the task that re-proves each claim (4.5, 5.3, 5.4, 5.9, 9.1, 16.2); non-existent tags removed; I found and corrected my own statement that a `B-06c` record existed (the command never ran) |
| C-04 | Medium | H3/H4 failure evidence not kept; "70 of 70" counted an attribute check | "69 refusals plus the attribute check"; H3/H4 marked first run; task 5.4 reproduces the one-chunk failure by removing `SELECT (id)` |
| C-05 | Medium | Wrong tasks/tests in matrix rows | Matrix regenerated (self-tampering 5.10, isolation 9.1, connection-limit test, document-storage 5.6) |
| C-06 | Medium | Task 1 report overstated: round C of the valid run is defective, RAM figure, round C ran at 4.98 GB, script changed after the run | Report reworded: valid for A, B, D; round C in its own file with the memory remark; "about 5 GB"; later script version noted |
| C-07 | Medium | "No application container holds the administrator password" proved only on harness files | Limit added: the real `.env` split is proved by tasks 3.1, 3.3 and 6.4 |
| C-08 | Low | Consent error status not specified; `docs/api-spec.yml` not checked | Scenario now says HTTP 500 with the standard error body; task 7.2 verifies the consent responses in `docs/api-spec.yml`; task 18.1 mentions it |
| C-09 | Low | Working command names used as normative text; proposal lists four commands but `db-grants` is a fifth | Requirement title says "The verifier"; "60 times" removed; proposal names `db-grants` as a step of `db-migrate` |
| C-10 | Low | Rollback fallback contradicts the rule that no application container holds the administrator credential | DD-12 states it is an emergency fallback to revert and rotate (`TD-038`) |
| C-11 | Low | TDD failing-run record only in 2.1; no archive task | Groups 3, 4, 6, 7, 9 and 10 record the failing run; task 19.4 archives |
| C-12 | Low | Dangling reference to this report | This file |
| C-13 | Low | A local Windows path with the user name in an output file | Replaced by `<scratch>` in the three output files |
| C-14 | Low | Missing denied-case scenarios for `document_chunks.content`/`embedding` (worker) and `alembic_version` | Two scenarios added to `database-roles` |
| C-15 | Info | No status marks for the decisions; artifacts not committed | Status paragraph added to `design.md`; the artifacts are committed in this stage |

Reviewer's conditions: 1 (C-01, C-02, C-03) and 2 (C-04 to C-07) are applied; C-08 to C-15 are applied too, so the only residual item is evidence that cannot exist yet: adoption and rollback with data, which tasks 5.3, 5.9 and 16.2 must re-prove before group 16 is authorised.
