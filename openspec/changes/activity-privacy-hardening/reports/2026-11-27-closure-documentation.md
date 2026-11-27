# Documentation closure of the technical integration (2026-11-27)

Documents only: no product code, contract, database, infrastructure, standard or workflow changed. Nothing is enabled, no risk is accepted or closed, no Gemini call. Not archived.

## Owner decisions applied

- Tasks 3.3 to 3.5 are rescheduled to a future change (proposed name `activity-enablement-conditions`; no change folder created). F8, F7 and the legal requirements stay open.
- Register, roadmap and artifacts reflect the merge of pull request #37 and the green CI of `main` (see `2026-11-27-original-scope.md`, "After the merge").
- The specs of the metrics and of the dashboard are reconciled with the integrated behaviour.
- The future initiative «Analítica pedagógica inteligente» is in the roadmap, grouping features 3, 4 and 7; no new feature. Its content (top 5 of topics identified from the PDF files, horizontal bars, three kinds of suggestion; R-D12) follows the owner's earlier instructions of the same day.

## Spec reconciliation (deltas never synced, edited in place)

| Spec | Before | Now | Evidence in `main` |
|---|---|---|---|
| Metrics | window of whole weeks around the requested days | also: only ended weeks (one hour of margin); only weeks after the week of the last unenrolment; possible 0 weeks | `tests/unit/test_activity_window_rule.py` |
| Metrics | silent on deleted documents | only current ready documents are listed | `tests/unit/test_activity_service.py`, `tests/integration/test_activity_deleted_documents_db.py` |
| Dashboard | "every other figure reads «Datos insuficientes»" when the subject is withheld | the tables and shares are not drawn | `TeacherActivityPage.test.tsx` |
| Dashboard | no state for a shorter history | limited history and no whole week | same |
| Dashboard | note without the limit of anonymity | says that anonymity is not guaranteed | same |

Followed `opsx:update` for coherence across the artifacts; the confirmation it asks for each edit is the owner's authorisation of this task, so edits were not confirmed one by one.

## Scan of the Git history (read only)

No secret was found. No value was printed or copied.

Method: throwaway scripts outside the repository, run on 2026-11-27 over the tips of the remote branch and pull request refs (38 distinct), 407 commits, 2513 blobs and the commit messages: patterns for provider keys, access tokens, private key blocks, signed tokens, password hashes, connection strings and assignments with a secret-like name; a literal search of the secret values of the untracked local environment files; the names of every file ever committed. The remaining matches were inspected by shape (code expressions, interface labels, test fixtures, disposable test hosts). The scripts and their output are not kept in the repository, so these results cannot be reproduced from it.

Limits: pattern based; compressed binary content is not unpacked (the three tracked images were looked at and show fictitious data); pull request texts, comments and CI logs were not scanned. Points for the owner were reported outside the repository.

## Open

- Before archiving `activity-privacy-hardening`: base standards §9.8 (no change is closed with an open Major finding) against F8, which stays open. Owner decision.
- The three task checkboxes are gone, so OpenSpec will not warn about them at archive; the roadmap entry and the "Rescheduled" section carry them.
- The same §9.8 question is to be answered for `activity-events-and-metrics` and `teacher-activity-dashboard`, whose capability F8 affects.
- Archive order proposed: `activity-events-and-metrics`, `teacher-activity-dashboard`, `activity-privacy-hardening`.
- Residual risks unchanged: V3, V6a, V6b, V8 to V12, F6, a rate of 0 or 1, enrolled minus active, TD-072, F8, F7, and a student's own erasure noticeable between reads.

## Independent review

By a separate agent, read only. **PASS WITH GAPS:** no Blocker, no Major, 8 Minor (change name of the first slice; a scenario that presumed the archive; rescheduled tasks no longer counted; stale present tense; the old F8 title and duplicated rules; two imprecisions of the metrics spec; more public detail than needed; claims without a record). They were corrected after the review and were **not** re-reviewed. The review confirmed the spec statements against the code, the merge, the CI figures and that nothing accepts, closes or mitigates a risk.

## Gates

`openspec validate --all --strict` 29 of 29. Pull request #38, commit `9d86b3a`: `backend`, `privileges` and `frontend` green on both triggers (push and pull request).
