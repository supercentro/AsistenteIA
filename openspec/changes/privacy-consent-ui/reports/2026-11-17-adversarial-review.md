# privacy-consent-ui: independent adversarial review (task 4.6)

Reviewer: a separate read-only subagent session (skill `adversarial-review`), clean context, on the uncommitted tree of `feature/privacy-consent-ui`. It ran the frontend unit suite (282 passed); it did not run the Playwright suites. The report below is its content, condensed; dispositions were added by the implementing session.

**Verdict of the first pass: FAIL** (four Major, no Blocker). No gate bypass, redirect loop or open redirect was found; the profile is replaced only from the API response.

| # | Severity | Finding | Disposition |
|---|---|---|---|
| 1 | Major | A late acceptance response overwrites whichever session is open (`useAcceptConsent` calls `setUser` without checking that the session is the one that sent the request) | Fix: capture the token when the request starts and apply the answer only if it is still current (task 5.2); test first (5.1) |
| 2 | Major | The policy link on the consent screen is a plain link: a full page load ends the memory-only session and silently signs the student out | Fix: open in a new tab with `noopener` (5.2), test (5.1), spec scenario added |
| 3 | Major | Deletion is described as definitive although backups exist and their erasure is unknown; "how to delete" refers to a screen that does not exist yet | Text: remove "definitiva", backup position as owner input (5.3). The re-check of where to delete stays a condition for closing TD-003 (already in `docs/frontend-standards.md` and task 3.2) |
| 4 | Major | Retention omits that conversations are deleted with a subject or an account (`conversations.subject_id` and `student_id` cascade) | Text and evidence table (5.3) |
| 5 | Major | Withdrawing consent is not as easy as giving it (GDPR Art. 7(3)); the list of rights is incomplete (erasure, restriction, portability, complaint to the authority) | Rights list completed as owner input (5.3); gap recorded in TD-003 (5.4); the owner decides whether to accept it or to build a withdrawal flow in another change |
| 6 | Minor | After a 403 `CONSENT_REQUIRED` the consent screen shows the first-time notice, not the changed-policy notice (the spec says changed) | Fix: `markConsentStale` keeps the acceptance time; notice chosen from it (5.2); test (5.1) |
| 7 | Minor | "Data used only to give the service" is unqualified (similarity score kept for analysis; logs) | Text qualified (5.3) |
| 8 | Minor | Nothing technical stops the placeholders from shipping | Release check test, run on demand (5.1, 5.2) |
| 9 | Minor | Report honesty: 4.3 "restore" ticked although the data cannot be restored and `/chat` 200 was not exercised; 1.3 counts 15 tests, the file has 16; 1.6 "no values in logs" is shown for the network-failure path only; only one test detects the "hold teachers" mutation | Wording corrected (5.5) |
| 10 | Minor | Policy tests compare the rendered text with the same constants, so they cannot detect a false claim | Accepted as limited; the evidence table is the control |
| 11 | Question | With no relevant fragment the question is not sent to Gemini (no history is loaded either); the text over-discloses, the safe direction | Left as is; owner may confirm |
| 12 | Question | D6 (version string unchanged) and D7 (teachers not gated) unconfirmed | Remain open for the owner (task 3.3) |

Gaps the reviewer noted against the spec: the 403 mid-session path was not tested end to end through the gate (added in 5.1); keyboard and 320 px are covered by the browser run and the committed mocked spec only (jsdom cannot show them).

## Delta re-check (second pass)

A second read-only session verified findings 1 to 9 against the corrected tree and ran the unit suite (287 passed, 1 skipped). **Verdict of the delta: PASS WITH GAPS**; findings 1 to 8 resolved, no new code defect.

Minor points found and fixed afterwards: the evidence table said no account-deletion endpoint is in `docs/api-spec.yml` (false: `DELETE /users/me` is defined there but not implemented in the backend; wording and divergence note corrected); the number of owner inputs is six, not four (TD-003 and task 3.2 updated); stale counts in task 1.3 and in the gates line of the TDD report.

Open items that depend on the owner and are not defects: the six policy inputs and the approval of the text (task 3.2), the assumptions D6 and D7 (task 3.3), accepting or scheduling the Art. 7(3) withdrawal gap, and whether the over-disclosure when no fragment is relevant is acceptable.

Divergence to report: `DELETE /users/me` is in the contract and the approved scope but not implemented.
