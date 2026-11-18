# privacy-consent-ui: adaptation to Ley 25.326 (Argentina)

Date: 2026-11-18. Not legal advice: it records what was read, what the text now says, what is still open and which points need a lawyer. The policy is a draft and is not presented as approved.

## Context decided by the owner
Argentine MVP, only for people over 18, commercial projection for Argentine educational institutions. Gemini API in the **free tier**, only with fictitious users and documents. Teachers are not asked for the chat consent. TD-003 stays open and the chat stays closed to real students.

## Sources read (2026-11-18)
- Ley 25.326 and Decreto 1558/2001: original texts on `argentina.gob.ar/normativa` (the 2000 and 2001 texts as published). **Later amendments and the consolidated text were not checked.**
- Disposición 60-E/2016 (full text read) and the AAIP page on international transfers.
- Gemini API terms at `aistudio.google.com/docs/terms` ("Effective March 23, 2026"; `ai.google.dev/gemini-api/terms` redirects there). The documents they refer to (data processing addendum, Google Privacy Policy, API terms) were **not** read.
- Not read: Resoluciones AAIP 4/2019, 255/2022, 34/2019, 198/2023, 159/2018 (known only through summaries and the AAIP page).

## Article mapping

| Requirement | Source | State in the product |
|---|---|---|
| Consent free, express and informed, given after the information of art. 6 | Ley 25.326 art. 5.1 | The consent screen shows the policy before the tick box. Gap: the account data is collected at registration, before it (TD-064) |
| Consent may be revoked at any time, without retroactive effect | Decreto 1558/2001 art. 5 | Stated in the policy. No way to withdraw in the application (TD-064) |
| Information: purpose and recipients; existence of the database and identity and domicile of the controller; whether the data is mandatory; consequences of providing or refusing; rights of access, rectification and suppression | Ley 25.326 art. 6 | Purpose, recipients, obligation, effect of not accepting and rights: in the text. Controller: owner input. Consequence of inaccurate data: not stated (legal review) |
| Data adequate and not excessive; destroyed when no longer needed | art. 4 | Retention text and owner input on retention and backups |
| Security and confidentiality measures | arts. 9 and 10 | Not part of the policy; covered by backend standards. Not re-verified in this stage |
| Transfer of data to a third party needs consent; the transferee has the same obligations | art. 11 | Gemini is described as the service that receives the data; its role is not asserted (TD-063) |
| International transfer to a country without adequate protection is prohibited, except express consent of the holder (decree) or an approved contract | art. 12, Decreto art. 12, Disposición 60-E/2016 arts. 1 to 3 | The United States is not in the list of adequate countries (art. 3). The text discloses the possible processing abroad. The basis is an owner input with legal review (TD-063) |
| Service provider: use the data only as the contract says; contract with confidentiality and security | art. 25, Decreto art. 25 | Applies when an institution is the controller and AsistenteIA the processor, and to Google as sub-processor. Not asserted (TD-063) |
| Access in 10 calendar days, free at intervals of at least six months | art. 14 | Stated in the text. No self-service and no defined owner of the requests (TD-064) |
| Rectification, update and suppression in 5 business days | art. 16 | Stated in the text. Same gap |
| Registration of the databases | arts. 21 and 24 | Not decided: whether it applies to the controller is a legal question (TD-064) |
| Sanctions | art. 31 | Not assessed (the amounts in the original text are from 2000) |

## Gemini terms (read 2026-11-18)

| Point | Unpaid services (free tier) | Paid services |
|---|---|---|
| Use of prompts and responses | Google uses them to provide, improve and develop products and models | Google states it does not use them to improve its products |
| Human review | Reviewers may read and annotate the inputs and outputs | Not stated |
| Data processing addendum / roles | Not covered | Prompts and responses are processed under the addendum for products where Google is a processor; other data (account, billing, usage) under controller-to-controller terms |
| Retention | No period given | Logged "for a limited period" (no length), for abuse prevention, safety and legal disclosure; may be stored transiently or cached in any country where Google or its agents have facilities |
| Warning on personal data | The page warns against submitting sensitive, confidential or personal information | Not stated |
| Age | Users must be 18 or older, and clients aimed at or likely to be used by people under 18 are not allowed | same |
| Billing condition | Access through a Cloud project with active billing counts as a paid service | |

Consequence: with the free tier, Google cannot be described as a processor and the data may be used for Google's own purposes, which does not fit art. 25. The free tier is acceptable only with fictitious data.

## Conditions for a production use (recorded in `docs/technical-debt.md`)
1. TD-003: policy approved by the owner after legal review; chat closed to real students until then.
2. TD-063: Gemini with billing enabled, terms and addendum evaluated, basis of the international transfer decided, processor contract if an institution is the controller.
3. TD-064: ways to exercise the rights and to withdraw the consent in the legal deadlines; account deletion; consent at registration; registration with the AAIP; controller and processor roles per institution; the age is a declaration.

## What changed in the product
- Review: `2026-11-18-adversarial-review-argentina.md` (PASS WITH GAPS, corrected the same day).
- Text (`strings.es.ts`): sections `audience`, `mandatory` and `rights` added; Gemini no longer called processor; disclosure of possible processing abroad; placeholders reworded (legal review marked); the tick box declares being over 18.
- Artifacts: proposal, design (D6, D7, D8, D9), spec (a requirement and scenarios), tasks (section 6), evidence table, `docs/technical-debt.md` (TD-003 updated, TD-063 and TD-064 added), `docs/frontend-standards.md`, `docs/development_guide.md`.
- Not changed: backend, API contract, `PRIVACY_POLICY_VERSION`, infrastructure, secrets, databases, skills, hooks, standards of OpenSpec/SpecBoot, `readme.md`, `prompts.md`.

## Tests and mutations
Six tests written first (`pages/PrivacyPage.test.tsx`): 6 failed before the text, the file passes (14 tests) after. Four mutations of the text were each detected by one test: legal deadline changed, over-18 declaration removed, processing abroad removed, Gemini called "encargado del tratamiento" again.

## Points that need a lawyer (not decided by the agent)
1. The legal basis, and whether art. 5 allows the account data to be collected at registration without the consent screen.
2. Whether the express consent of the policy is a valid basis for the transfer to Google, or an approved contract is needed.
3. The wording of the rights, the deadlines and who answers; whether the AAIP is the authority to name and its contact.
4. Whether the database must be registered and who is the controller in a commercial use.
5. The role of Google under the contracted service and the processor contract between institution and AsistenteIA.
6. The consequence of inaccurate data (art. 6 d), not stated.
7. Teachers: their account data is processed without a consent, a policy acceptance or an age declaration (D7).
8. Whether the over-18 declaration may share one tick box with the acceptance of the policy, or must be separate.
9. The name of the supervisory authority and its succession (not named in the text after the review).
10. A security statement (arts. 9 and 10) and a contact for security incidents, absent from the policy.

## Caveats
Original texts, not consolidated; summaries for the AAIP resolutions; Gemini terms change over time (re-read before any production decision); the list of adequate countries may be updated by the AAIP.
