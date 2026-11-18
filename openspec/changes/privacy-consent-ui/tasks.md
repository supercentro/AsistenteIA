## 0. Branch

- [x] 0.1 Step 0: branch `feature/privacy-consent-ui` created from `main` (`f327be6`). Merge only through a Pull Request.

## 1. Tests first (frontend, Vitest + RTL + MSW)

- [x] 1.1 Unit tests for the consent rule and the session: a helper decides "held" from role and `consent_version` (student null/outdated/current; teacher never); `markConsentStale()` stores the profile with a null version and does nothing without a user. [lib/consent.test.ts, 8 tests]
- [x] 1.2 Component tests for the policy page: public (no session, no API request), shows the version, names Gemini, lists what is sent, describes deleting one conversation and all conversations, states what is not self-service; the registration screen and the consent screen contain a link to `/privacy`. [pages/PrivacyPage.test.tsx]
- [x] 1.3 Component tests for the consent screen (16 tests in the first pass): Accept disabled until the box is ticked; accept sends the current version and, on 200, replaces the profile and goes to the original target; 422 `INVALID_CONSENT_VERSION` shows the reload message and does not loop; network/5xx error shows a retry control and leaves the profile; 401 ends the session; sign-out clears it; heading receives focus. [pages/ConsentPage.test.tsx, 16 tests in the first pass, 18 after the review]
- [x] 1.4 Routing tests for the gate: student without consent and with an outdated version are sent to `/consent` from every student route (including a typed address); current consent renders the route and `/consent` redirects home; teacher never sees `/consent`; anonymous is sent to login. [pages/consentGate.test.tsx]
- [x] 1.5 API client tests: 403 `CONSENT_REQUIRED` for a signed-in student marks the consent stale and does not retry; another 403 code, and a 403 for a teacher, change nothing. [lib/consentApi.test.ts]
- [x] 1.6 Accessibility and copy tests with the existing helpers (`tests/a11y.ts`, `tests/copy.test.ts`): no inline strings, labelled tick box, no horizontal scrolling at 320 px, no tokens/emails/form values in logs or errors (shown for the network-failure path). [axe and copy detector; 320 px is verified in the browser, see reports/2026-11-17-tdd-and-mutation-evidence.md]
- [x] 1.7 Run the new tests before any implementation and record the failing run (command and failure summary) in the change report. [31 of 38 failed before the implementation, see reports/2026-11-17-tdd-and-mutation-evidence.md]

## 2. Implementation (frontend only)

- [x] 2.1 `lib/session.ts`: `markConsentStale()`; the held-student rule as a small pure helper next to `lib/privacyPolicy.ts`. [lib/consent.ts, markConsentStale in lib/session.ts]
- [x] 2.2 `lib/apiClient.ts`: on 403 `CONSENT_REQUIRED` of a signed-in student call `markConsentStale()`; no retry. [lib/apiClient.ts]
- [x] 2.3 Policy content as a typed structure in `lib/strings.es.ts` and one `PolicyView` component; the draft text is written from the behaviour verified in the code and docs, with clearly marked placeholders for the owner inputs (controller, contact, legal basis, retention beyond "until deleted"). [strings.es.ts section privacy, components/PolicyView.tsx; owner placeholders marked [A COMPLETAR ...]]
- [x] 2.4 `PrivacyPage` at `/privacy`, public and lazy-loaded, outside `RequireAuth` and `RedirectIfAuthenticated`; link from `RegisterPage`. [pages/PrivacyPage.tsx, link in RegisterPage]
- [x] 2.5 `services/consentService.ts` and `hooks/useAcceptConsent.ts` (mutation; on 200 `setUser(response)`). [services/consentService.ts, hooks/useAcceptConsent.ts]
- [x] 2.6 `ConsentPage` at `/consent` (inside `RequireAuth`, outside the gate): notice for first time versus changed policy, policy text, tick box, Accept, sign-out, error and retry states; redirects away when consent is current or the user is a teacher. [pages/ConsentPage.tsx]
- [x] 2.7 `RequireConsent` layout route around the student routes in `App.tsx`, preserving the original target through `returnTarget`. [components/RequireConsent.tsx, App.tsx]
- [x] 2.8 Run the tests from section 1 and confirm they pass. Mutation checks, each shown to fail a named test and then reverted: remove the gate; remove the 403 handler; ignore the version and hold only when null; let teachers be held. [46 passed; 4 mutations detected, see reports/2026-11-17-tdd-and-mutation-evidence.md]

## 3. Policy text: owner inputs and approval

- [x] 3.1 Table in the change report that maps every statement of the policy text to the code or document that proves it (what is stored, what is sent to Gemini, deletion routes, citation snapshots). [reports/2026-11-17-policy-evidence-table.md]
- [ ] 3.2 Owner supplies the six placeholders (controller and domicile, legal basis with legal review, Google conditions and basis of the international transfer with legal review, account retention, backups, means to exercise the rights and contact of the supervisory authority) and approves the final text. `POLICY_RELEASE_CHECK=1 npx vitest run src/lib/policyPlaceholders.test.ts` must pass. The agent cannot do this task; the change is not merged and TD-003 is not closed before it is done.
- [ ] 3.3 Owner confirms or rejects the version string (D6: unchanged recommended). Teachers not gated (D7) was confirmed on 2026-11-18.

## 4. Mandatory steps

- [x] 4.1 Step N: review and update existing frontend tests that depend on the profile consent fields or on the routes, and the pair of tests that keep the UI constant equal to the backend default. [existing tests adapted (shared studentUser now consented; unconsentedStudent and outdatedStudent added); the UI/backend version pair tests still pass]
- [x] 4.2 Step N+1: run the frontend suite with coverage thresholds and the backend consent tests (`test_consent*`), verify the database state before and after (the change touches no table), and save the report in `reports/`. [reports/2026-11-17-step-4-2-unit-test-and-db-verification.md]
- [x] 4.3 Step N+2: manual calls with curl against the local stack, on test accounts created for the check (the accounts cannot be removed through the API, so the data is not restored: documented in the report): `POST /users/me/consent` (200, 422 `INVALID_CONSENT_VERSION` with `details.current_version`, 401), `/chat` without consent (403 `CONSENT_REQUIRED`) and with it; save the report and restore the data it created. [reports/2026-11-17-step-4-3-curl-testing.md]
- [x] 4.4 Step N+3: Playwright MCP run by the agent on the local stack (register a student, sign in, held at `/consent`, read `/privacy`, accept, reach the subjects; a teacher is not held; 320 px viewport; keyboard only) and the committed Playwright Test specs (mocked API for the gate and the failures; one real-backend spec that accepts consent). Save the report. [reports/2026-11-17-step-4-4-e2e-verification.md]
- [x] 4.5 Step N+4: update `docs/frontend-standards.md` (new pages, the rule that any change of the policy text raises the version in the same change), `docs/technical-debt.md` (TD-003: what this change resolves and what remains until 3.2), and check `docs/api-spec.yml` for divergence. `readme.md` and `prompts.md` only with the owner's approval. [docs/frontend-standards.md, docs/technical-debt.md (TD-003 stays open), docs/api-spec.yml wording; readme.md and prompts.md untouched]
- [x] 4.6 Independent adversarial review (personal data and consent): separate session, report with findings, fixes and verdict; no open blocker or major. [first pass FAIL (4 Major), corrected, delta re-check PASS WITH GAPS (minor documentation points fixed); reports/2026-11-17-adversarial-review.md]
- [x] 4.7 Final verification of the MUST gates of `docs/base-standards.md` section 9, re-run after the last change: `npm run lint`, `format:check`, `typecheck`, `check:api-types`, `test:coverage`, `build`, `openspec validate privacy-consent-ui --strict`, and the CI jobs of the pull request. [lint, format:check, typecheck, check:api-types, test:coverage (22 files, 287 passed, 1 on-demand skipped, 98.07 percent), build, Playwright mocked 16 passed, openspec validate --all --strict 21 passed; Linux CI to be confirmed on the pull request]

## 5. Corrections after the independent review (`reports/2026-11-17-adversarial-review.md`)

- [x] 5.1 Tests first: a late acceptance of an earlier session does not change the open session; the policy link opens in a new tab with `noopener`; a 403 `CONSENT_REQUIRED` from a page request takes a consented student to `/consent` with the changed-policy notice; a release check that fails while the policy has owner placeholders. Run and record the failing run. [4 failed tests and 1 failed file before the corrections, see reports/2026-11-17-tdd-and-mutation-evidence.md]
- [x] 5.2 Code: capture the token that sent the acceptance and apply the response only if it is still current; `markConsentStale` keeps the acceptance time and the consent screen picks the notice from it; the policy link opens in a new tab; the release check on placeholders. [hooks/useAcceptConsent.ts, lib/session.ts, pages/ConsentPage.tsx, lib/policyPlaceholders.ts]
- [x] 5.3 Policy text: remove "de forma definitiva" and state the backup position as an owner input; add the deletion of conversations with a subject or an account; qualify the purpose statement (similarity scores kept for quality analysis; technical logs without message content); complete the list of rights and the complaint to the supervisory authority; update the evidence table. [strings.es.ts privacy section and reports/2026-11-17-policy-evidence-table.md]
- [x] 5.4 Record in `docs/technical-debt.md` (TD-003) that withdrawing consent is not as easy as giving it (GDPR Art. 7(3)); the owner decides whether to accept it or to add a withdrawal flow in another change. [docs/technical-debt.md TD-003]
- [x] 5.5 Correct the wording of tasks 1.3, 1.6 and 4.3 and of the reports where the review found overstatements; re-run the gates of 4.7. [tasks 1.3, 1.6, 4.3 and the step 4.3 and TDD reports corrected]

## 6. Adaptation to Ley 25.326 (Argentina), 2026-11-18

- [x] 6.1 Read the sources and record the frame, the article mapping, the Gemini terms and the production conditions. [reports/2026-11-18-argentina-legal-framework.md]
- [x] 6.2 Tests first (6 tests in `pages/PrivacyPage.test.tsx`): audience over 18, obligation and effect of not accepting, processing outside Argentina without asserting a processor role, rights with legal deadlines and revocation, no GDPR-only rights, over-18 declaration in the tick box. [6 failed before the text, 14 passed after; 4 mutations of the text detected, see reports/2026-11-18-argentina-legal-framework.md]
- [x] 6.3 Policy text in `lib/strings.es.ts`: sections `audience`, `mandatory` and `rights` added; Gemini no longer called processor; transfer disclosure; legal-basis, Google and rights placeholders reworded; tick box declares being over 18. [strings.es.ts]
- [x] 6.4 Artifacts and documents: proposal, design (D6, D7, D8, D9), spec (new requirement and scenarios), evidence table, `docs/technical-debt.md` (TD-003 updated, TD-063 and TD-064 added), `docs/frontend-standards.md`, `docs/development_guide.md`. [done]
- [x] 6.5 Independent review of the adapted text and the artifacts (separate read-only session): PASS WITH GAPS, three Major and several Minor findings. [reports/2026-11-18-adversarial-review-argentina.md]
- [x] 6.7 Corrections of the review: habeas data cited with arts. 33 onwards; the AAIP name removed from the text (owner input 6); the age declaration of students only; "Ley 25.326 y su decreto" for the rights; softened sentence on the United States; teachers, bundled declaration, art. 6 d, security statement, the free-tier use of the questions and the registration regime recorded in TD-063 and TD-064; tests strengthened (checkbox by its 18-year label, six placeholders, no processor or approval wording anywhere); the gates re-run. [done]
- [ ] 6.6 Legal review of the points marked "legal" in the report (basis of the processing, consent for the transfer, rights wording, registration, consent at registration). Owner task; not done by the agent.

- [x] 6.8 Stages recorded (owner decision of 2026-11-18): MVP with fictitious data only, pilot with real students over 18 possibly with one Argentine institution whose responsibilities are defined before it is enabled; no multi-institution scope. [proposal.md, design D9, reports/2026-11-18-argentina-legal-framework.md, TD-003, TD-063, TD-064, docs/development_guide.md]

## Workflow follow-up

- Open the pull request against `main`; merge only with the owner's authorization and after 3.2.
- After the merge: `/opsx:archive privacy-consent-ui`; close TD-003 in `docs/technical-debt.md` only with the owner's decision.
- The chat screen is a separate change; real students still must not use the chat until it exists, TD-003 is closed and the Gemini measurements are reviewed.
