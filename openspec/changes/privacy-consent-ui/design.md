# Design

## Context

See `proposal.md` (Why). Current state, verified in the repository:

- Backend: `POST /users/me/consent` records the version and the server time (`privacy-consent` spec); `/chat` answers 403 `CONSENT_REQUIRED` without current consent. `GET /users/me` returns `consent_version` and `consent_accepted_at`. Nothing changes here.
- Frontend: the session lives in an in-memory store (`lib/session.ts`, with `setUser`); `useSession` exposes the profile; routing uses layout routes (`RequireAuth`, `RequireRole`) under `App.tsx`; every string comes from `lib/strings.es.ts`; `lib/privacyPolicy.ts` holds `PRIVACY_POLICY_VERSION = '2026-10-v1'`, kept equal to the backend default by tests on both sides. The profile consent fields are kept but not interpreted (a requirement this change replaces).
- Standards: `docs/frontend-standards.md` (consent screen blocks chat; privacy page names Gemini and explains deletion), the shared UI rules of `frontend-app-shell` (loading/error/empty states, labels, focus, 320 px, lazy chunks).

## Goals / Non-Goals

**Goals:** a student can read the policy, give an explicit and recorded consent, and is held until the consent matches the current version; the same mechanism handles a later version change; the interface is accessible and uses the existing patterns.

**Non-Goals:** the chat screen; a withdrawal endpoint or account deletion (the policy text must say honestly that they are not self-service yet); consent per purpose; showing a consent history; any backend change.

## Decisions

### D1. A layout route holds students: `RequireConsent`
A layout route inside `RequireAuth` and around the student routes renders `<Outlet />` only when the profile role is not `student` or `consent_version` equals `PRIVACY_POLICY_VERSION`; otherwise it renders `<Navigate to="/consent" state={{ from }} />`. `/consent` sits outside it (inside `RequireAuth`) and redirects to the home route when consent is already current or the user is a teacher.
*Alternatives:* a check inside each page (rejected: easy to forget on the next route, the chat page being the one that matters); a modal over the app (rejected: the app would render behind it and fire requests).
*Why the gate covers all student routes, not only the future chat:* there is no chat route yet to attach it to, and a gate defined per route is the failure mode above. The cost is that a student without consent cannot see the subject list; acceptable because the screen is one click away.

### D2. The comparison uses the UI constant, the backend stays the authority
The gate compares the profile with `PRIVACY_POLICY_VERSION`. If the two ever drift, the existing tests fail (UI constant against backend default). The backend check remains the only enforcement: the gate is usability.

### D3. 403 `CONSENT_REQUIRED` re-opens the gate
The API client, on a 403 whose code is `CONSENT_REQUIRED` for a signed-in student, calls a new `markConsentStale()` in `lib/session.ts`, which stores the profile with `consent_version: null`. The gate then redirects reactively; no refetch and no automatic retry (a retry after acceptance is the user's action). Other 403 answers are untouched. *Alternative:* refetch `GET /users/me` (rejected: an extra request that returns what the error already said).

### D4. Accepting
`useAcceptConsent` (React Query mutation) sends `POST /users/me/consent` with the constant and, on 200, calls `setUser(response)`, which releases the gate; the page then navigates to `state.from` (validated by the existing `returnTarget` helper) or the home route. 422 `INVALID_CONSENT_VERSION` is shown as "the policy changed, reload the page" and does not loop; network/5xx errors show the retry control of the shared error state; 401 follows the existing session-end path.

### D4b. Corrections after the independent review
The acceptance is applied only if the session that sent it is still the open one (the token is captured when the request starts and compared when the answer arrives), the same rule the 401 and 403 paths already follow. `markConsentStale` keeps the acceptance time, so the consent screen can tell "never accepted" (no time) from "the policy changed" (a time with no current version). The policy link on the consent screen opens in a new tab because a full page load ends the memory-only session. A release check fails when the policy still contains owner placeholders (run on demand, not in the regular suite, so the draft can be reviewed).

### D5. Policy content
The policy is a typed structure (title, sections of paragraphs and lists) in the Spanish copy module, rendered by one component used by `/privacy` (public, outside `RequireAuth`, lazy chunk) and by the consent screen. One source, so the text a person accepts is the text they can read later.

Content, written from what the system does today (each statement is checked against the code and docs when the text is drafted):
- what is stored: account data, the conversations and messages, the fragments cited by each answer, the consent version and time;
- what is sent to Gemini: the question, the recent history of the conversation and the retrieved fragments; nothing else; no call is made without consent;
- audience and obligation (Ley 25.326 art. 6): the service is only for people over 18; which data is needed and what not accepting means (a held student can only read the policy and sign out);
- the rights of Ley 25.326 (access, rectification, update, suppression, revocation of the consent without retroactive effect, habeas data) with the legal deadlines, and the supervisory authority (AAIP);
- retention: until the person deletes it; deleting one conversation, deleting all conversations (`DELETE /users/me/conversations`); deletion of a document by the teacher removes its fragments but conversation citations keep a snapshot (design D5 of `chat-rag-endpoint`) — the text must say so;
- not self-service today: account deletion and withdrawal of consent (contact the controller);
- the controller, its contact, the legal basis and any retention period beyond "until deleted" are **owner inputs** and appear as marked placeholders until supplied.

### D6. Version string stays `2026-10-v1` (open decision, still not confirmed by the owner)
The text of this change is the first one ever published, and it was rewritten for Ley 25.326 before any release; no real student has accepted any text, and the only database that holds an acceptance is the development one (test accounts). **Owner decision of 2026-11-18: keep `2026-10-v1` provisionally for the MVP; it is not a definitive policy, and the definitive version needs the owner's confirmation before the pilot.** Recommendation: keep it. No real student has accepted anything, so nobody holds a consent that was given without the text; the development database holds test accounts only. Raising it would change the backend default and about 17 backend test files for no protective effect. The rule for the future is stated in the policy module and in `docs/frontend-standards.md`: any change of the text raises the version in the same change. *Alternative:* raise now to `2026-11-v1` (rejected for cost; revisit if the owner knows of a real acceptance).

### D7. Teachers are not gated (confirmed by the owner on 2026-11-18)
Teachers upload material (processed by the local embedder) and never send conversational data to Gemini, so the consent that the policy describes does not apply to them. If the owner wants teachers to accept the same text, the gate condition changes in one place.

### D8. Legal frame and what the text may claim
Frame: Ley 25.326, Decreto 1558/2001 and the AAIP dispositions (Disposición 60-E/2016 on international transfers; Resoluciones 4/2019 and 255/2022 on criteria); the GDPR is a complementary reference. Details, article mapping and sources are in `reports/2026-11-18-argentina-legal-framework.md`.

- The text states facts of the system and the content that art. 6 requires: purpose and recipients, the identity of the controller (owner input), whether the data is needed and the effect of not accepting, and the rights. It cites the articles it relies on only where the law text was read.
- The text does **not** assert: that Google is a processor (that depends on the Gemini service contracted; the free tier is not covered by a data processing addendum and may use the data to improve products), a legal basis, a transfer mechanism, a retention period or a backup position. These are owner inputs marked `[A COMPLETAR ...]`, and the first three need legal review.
- The list of rights follows the law and its decree (access, rectification, update, suppression, revocation of consent from Decreto 1558/2001 art. 5, habeas data from art. 33 onwards). Portability and restriction of processing belong to the GDPR and are not listed. The text does not name the supervisory authority: the law and the decree read name the Dirección Nacional de Protección de Datos Personales and the succession by the AAIP was not verified in a norm, so the name is part of owner input 6.
- The sentence about the United States cites the list of Disposición 60-E/2016 (2016 text); the current list must be checked before approval (TD-063). The possibility of processing abroad comes from the terms of the paid services; the free-tier terms give no location.
- The tick box also declares being over 18, in the same box as the acceptance of the policy (a bundled declaration: a lawyer must say whether it must be separate). The application does not verify age; evidence kept: version and time only. Teachers are not asked to accept or to declare their age (D7), although their account data is processed: recorded in TD-064.

### D9. MVP and pilot: stages and conditions (the pilot conditions are not met by this change)
Owner decision of 2026-11-18. **MVP:** operated by the independent developer, with fictitious users, documents and data only; the free Gemini tier is acceptable and the policy may stay a draft. **Pilot:** real students over 18, possibly with one Argentine educational institution; who is the controller, who is the processor and which contract binds them are defined before the pilot is enabled, and nothing in this change defines them. Support for several institutions and a commercial offer are outside this change (a later decision). The change makes the screens and the text exist; it does not make a use with real students lawful. Conditions for the pilot, recorded in `docs/technical-debt.md`:
1. TD-003: policy approved (owner and legal review); chat closed to real students until then. The MVP with fictitious data does not need the approval.
2. TD-063: Gemini with billing enabled (the free tier only with fictitious users and documents); contractual terms, retention, use of the data and place of processing evaluated; basis of the international transfer (the United States is not in the list of adequate countries of Disposición 60-E/2016 art. 3); processor contract if the pilot institution is the controller (art. 25).
3. TD-064: effective ways to exercise the rights and to withdraw the consent within the legal deadlines; account deletion (`DELETE /users/me` in the contract, not implemented; no database role may delete from `users`); consent at registration (the account data is collected before the consent screen); registration of the database with the AAIP (arts. 21 and 24) if it applies; who is the controller and who the processor in the pilot.

## Risks / Trade-offs

- **The text is not legal advice.** It is a draft from the system's behaviour; wrong or missing statements would make the consent uninformed. Mitigation: the text is an internal draft for the MVP (fictitious data only, run by the developer) and is never presented as approved; an explicit task for the owner to supply the placeholders and approve the text **before the pilot with real students** (not before the merge, owner decision of 2026-11-18); the change does not close TD-003 by itself.
- **Account data is collected at registration, before the consent screen.** The registration screen links to the policy but does not ask for acceptance. Whether art. 5 requires the consent earlier is a legal question recorded in TD-064; this change does not alter the registration flow.
- **Blocking the subject list** for students without consent (D1). Mitigation: the consent screen is the only step; copy explains why.
- **Consent obtained earlier by API calls** (dev accounts) will pass the gate without having seen the text (D6). Acceptable in development; irrelevant for real users.
- **Drift between UI and backend versions:** covered by the existing paired tests; the gate fails closed in the worst case (a student asked to accept again, `422` shown, no loop).
- **A long policy on a 320 px viewport:** plain semantic headings and lists, no tables, tested at 320 px.
- **Mocked tests do not prove the real API:** one real-backend test (existing `real-backend.spec.ts` pattern) accepts consent against the local stack.
