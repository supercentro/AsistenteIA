# Proposal

## Why

The chat is implemented and archived (`chat-rag-endpoint`), and the backend already refuses it without current consent (403 `CONSENT_REQUIRED`). But no student can give that consent: the interface has no privacy-policy text, no disclosure that questions, history and retrieved fragments are sent to Gemini, and no consent screen. This is the remaining part of TD-003 (`docs/technical-debt.md`) and the condition that keeps the chat closed to real students. `docs/frontend-standards.md` already requires it: "first-login consent screen blocks chat until accepted; the privacy page names Gemini as a processor and explains deletion options".

## What Changes

- A public **privacy-policy page** (`/privacy`) with the policy text of the current version, in Spanish, from the single copy module. It names Gemini as processor and says what is sent to it, what is stored, for how long, and how a person can delete conversations.
- A **consent screen** (`/consent`): shows the policy version and text, an explicit unchecked tick box, and an "Accept" action that calls `POST /users/me/consent` with the UI version constant. A sign-out control is offered; nothing else is reachable without accepting.
- A **consent gate** for students: a signed-in student whose profile `consent_version` differs from the current version is redirected to `/consent` from every student route and returns to the original target after accepting. This is also the **re-acceptance flow** when the version changes.
- A student request answered with 403 `CONSENT_REQUIRED` (the policy changed during a session) sends the student to `/consent`.
- Links to the policy from the registration screen and the consent screen.
- The consent fields of the profile, which the interface kept without interpreting, are now used for the gate (modifies `frontend-session-auth`).
- Documentation: `docs/frontend-standards.md` (new pages), `docs/technical-debt.md` (TD-003 status), `docs/api-spec.yml` only if a divergence is found.

Out of scope (not added): the chat screen (a separate change), a consent-withdrawal endpoint, account deletion, per-purpose consent, a consent history, a backend change of any kind, and the text becoming legal advice (see Impact).

## Capabilities

### New Capabilities
- `frontend-privacy-consent`: privacy-policy page, consent screen, consent gate and re-acceptance for students.

### Modified Capabilities
- `frontend-session-auth`: the consent fields of the profile are now read to decide the gate (the requirement that forbade interpreting them is replaced).

## Impact

- **Authorization / isolation:** none changed. The backend stays the authority (403 `CONSENT_REQUIRED`); the gate is a usability layer. A consent write affects only the caller's account (existing behaviour). Teachers are not gated (assumption below).
- **Personal data (GDPR):** this change is what makes the consent informed. It adds no new personal data; the evidence stored is unchanged (version and acceptance time). The policy text must be accurate about what the system does today; items only the owner can state are listed in the design as open decisions.
- **External services:** the text discloses Gemini as processor. No call to any external service is added.
- **Contracts:** `docs/api-spec.yml` and `docs/data-model.md` do not change (the endpoint and the profile fields already exist).
- **Code:** frontend only (pages, one layout route, copy module, tests). No backend, migration, infrastructure or secret change.

### Assumptions to confirm (see design)
1. Only students are gated: teachers send no conversational data to Gemini.
2. The version string stays `2026-10-v1`: no real student has accepted anything, and changing it would touch about 17 backend test files. Any later change of the text must raise it.
3. The policy text is a draft written from the system's behaviour; the controller's identity, contact, legal basis and retention period must be supplied and the text approved by the owner before the change is merged.
