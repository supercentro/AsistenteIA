# privacy-consent-ui: independent review of the adaptation to Ley 25.326 (delta)

Date: 2026-11-18. Reviewer: a separate read-only subagent session (skill `adversarial-review`), clean context, on the uncommitted delta over `edae783` (PR #17). It read the originals of Ley 25.326, Decreto 1558/2001, Disposición 60-E/2016 and the Gemini terms, ran `PrivacyPage.test.tsx`, `ConsentPage.test.tsx` (32 passed) and `openspec validate privacy-consent-ui --strict` (valid). It could not verify the "failed before" and "mutations" claims of the report; the corrections below record them. Dispositions were added by the implementing session.

**Verdict: PASS WITH GAPS.** No blocker. Legal citations confirmed against the originals: Decreto art. 5 (revocable at any time, no retroactive effect), Decreto art. 12 (express consent), Ley arts. 14 (10 días corridos; free at intervals of at least six months) and 16 (5 días hábiles), Disposición 60-E/2016 art. 3 (the United States is not listed), and the Gemini terms of 2026-03-23. No wording of approval or conformity in the policy; version and TD-003, TD-063, TD-064 as agreed; the six placeholders are consistent.

| # | Severity | Finding | Disposition |
|---|---|---|---|
| 1 | Major | The 18-year declaration is made by accepting, but teachers never accept (D7): their account data is processed without consent, policy acceptance or age declaration; the text and TD-064 were silent | Text: "Los estudiantes lo declaran al aceptar"; TD-064 and the report record the teachers' gap and the legal question |
| 2 | Major | "hábeas data (arts. 14 y 16)": habeas data is regulated in arts. 33 onwards; arts. 14 and 16 only point to it | Text: "arts. 14, 16 y 33 y siguientes"; test and evidence table |
| 3 | Major | The text asserted the AAIP as supervisory authority; the law and decree read name the Dirección Nacional de Protección de Datos Personales and the succession was not verified in a norm | The name is removed from the text and becomes part of owner input 6; spec, evidence table, report, TD-064 |
| 4 | Minor | Revocation listed as a right of "la Ley 25.326": it comes from Decreto 1558/2001 art. 5 (the law has it only for the cession, art. 11.2) | "La Ley 25.326 y su decreto reglamentario reconocen" |
| 5 | Minor | "Estados Unidos no figura" is true for the 2016 list; the list is revised | Text: "según la lista de la Disposición 60-E/2016"; TD-063: check the current list before approval |
| 6 | Minor | The registration regime: Decreto arts. 21 and 24 leave it to later AAIP resolutions not read | TD-064 |
| 7 | Minor | Weak tests: the 18-year declaration was tested on the label string only; the existing consent tests use the same constant; the "processor" check covered one section; no test fixed the six placeholders | Added: checkbox found by its 18-year label that gates Accept; the whole policy has no "encargado del tratamiento" nor approval wording; exactly six placeholders. Six mutations of the text and one of the placeholders are detected |
| 8 | Minor | Version rule: the exception "first text" next to "any change raises the version", while the PR already holds a text | D6: the only database with an acceptance is the development one; the owner confirms before the merge (task 3.3) |
| 9 | Minor | "processor" wording survives in older artifacts | Reconciled in proposal, design, spec and task 1.2; TD-064 uses it only for the commercial role of art. 25 |
| 10 | Question | Nothing in the code tells real students from test ones | TD-003: the owner decides whether a technical barrier is wanted |
| 11 | Question | The possibility of processing abroad comes from the paid-tier terms; the free tier gives no location | Evidence table and design D8 say so |
| 12 | Minor | Gaps not recorded: teachers; security statement and contact for incidents; art. 6 d; the free-tier use of questions; the bundled 18-year declaration | TD-063 and TD-064 |

## Evidence of the corrections
- Failing run before the corrections: `npx vitest run src/pages/PrivacyPage.test.tsx src/pages/ConsentPage.test.tsx src/lib/policyPlaceholders.test.ts`: 3 failed, 34 passed, 1 skipped (the three text assertions; the three added tests passed already because the earlier text satisfied them).
- After the corrections: 37 passed, 1 skipped (the on-demand release check).
- Mutations (each detected by one test, then restored): remove the habeas data articles; remove the students' declaration; name the AAIP again; revert to "la Ley 25.326 reconoce"; add "aprobado" to the policy; remove one owner placeholder.

Not decided by the reviewer or the implementer: the legal questions listed in `2026-11-18-argentina-legal-framework.md`. The policy stays a draft and is not legally reviewed.
