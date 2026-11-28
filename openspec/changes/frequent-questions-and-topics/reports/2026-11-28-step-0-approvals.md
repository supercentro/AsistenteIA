# Step 0 Report - Approvals

- Date: 2026-11-28
- Change: frequent-questions-and-topics

## Owner decisions

Message of 2026-11-28 (planning task): R-D1 extended to this feature only, with fictitious data; PDF bookmarks as first source; manual definition of topics and page ranges as the alternative; topics per document; renaming and page ranges by the teacher; structured storage approved conceptually, migrations on disposable environments only; separate endpoint, switch and view; dashboard, five metrics and 12-week window preserved.

Message of 2026-11-28 (after the validated proposal), translated: "I approve the proposal, Q1 to Q3 as recommended; start the implementation."

| # | Answer |
|---|---|
| Q1 | The first topic set of a document counts past citations; any later change of ranges counts forward only |
| Q2 | Text and Markdown documents have no topics in this slice |
| Q3 | Authorised: write the R-D1 extension in `docs/base-standards.md` §8, `docs/backend-standards.md` §9, `openspec/config.yaml` and `docs/roadmap.md` |

Q4 (Spanish copy) was open until task 5.1.

Message of 2026-11-28 (after the implementation), translated: the Spanish copy of task 5.1 is approved, keeping the clarification that how often something is asked does not show difficulty of understanding (the ranking note says that the figures measure neither difficulty nor understanding); the independent adversarial review of task 12.1 is authorised; the five metrics of Feature 2 and the Top 5 of topics are kept; TD-073 and TD-074 stay documented as open risks and are not accepted for production. Incremental corrections of code, tests and documentation specific to this feature are authorised; standards, persistent infrastructure, secrets, GitHub Actions and OpenSpec/SpecBoot components are not to be modified.

Message of 2026-11-28 (after the independent review), translated: the warning of a change of pages is corrected to say that the figures count again from the week of the date and are shown when that week ends; TD-073 and TD-074 stay open and not accepted for production; the performance risk of the ranking is documented and not optimised; the missing size limit of JSON bodies is registered as technical debt and not corrected; all dashboard capabilities are kept. **Authorised:** commit, push and opening the Pull Request for this feature only, an incremental adversarial review of the corrections, and the CI. **Not authorised:** merge, deployment, archive, migration `0009` on a persistent database.

## Not authorised

At the time of the implementation (the last message above authorises the first three):

Commit, push, Pull Request, merge, deployment, archive, migration of a persistent database, Gemini calls, analytics with real students.

## Workspace

The branch `feature/frequent-questions-and-topics` was created from `origin/main` (`25d1d91`) in a separate git worktree (`../AsistenteIA-feature3`), because the running local containers mount the code of the main working tree. The change folder was moved there. The main working tree keeps its previous local modification and untracked files.
