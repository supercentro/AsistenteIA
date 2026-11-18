# privacy-consent-ui: evidence for every statement of the policy text (task 3.1)

The text is in `frontend/src/lib/strings.es.ts`, section `privacy`. This table maps each statement to the code or document that proves it. A statement without evidence would be removed. Checked on 2026-11-17 against `main` at `f327be6`.

| Statement in the policy | Evidence |
|---|---|
| Account data stored: name, email, password | `docs/data-model.md` (table `users`: `name`, `email`, `password_hash`) |
| The password is stored with a one-way transformation, never in clear | `docs/data-model.md`: `password_hash` text not null (Argon2id); `docs/base-standards.md` 9.3 (argon2) |
| Conversations: each question and each answer | `docs/data-model.md` (`conversations`, `messages` with role `user` or `assistant`) |
| Per answer, the cited sources: file name, page and a reference to the fragment | `docs/data-model.md` (`message_sources`: `document_filename` and `page_number` snapshots, `chunk_id`) |
| The accepted policy version and the acceptance time are stored | `docs/data-model.md` (`consent_version`, `consent_accepted_at`); spec `privacy-consent` |
| Data used to give the service; per cited source the position and similarity score are kept for quality analysis; technical logs carry no message content | scope of the approved MVP (`docs/base-standards.md` section 8); `docs/data-model.md` (`message_sources.rank` and `score` "allow RAG quality analysis"; "Application logs must not contain message content or document text" is a rule of the project, not yet shown by a test of this change) |
| Gemini receives the question, the recent messages and the relevant fragments with file name and page | `backend/app/services/prompt_builder.py`, `build_prompt(history, chunks, user_message)`; chunk header `[n] [Source: file, p.N]`; history bounded by `CHAT_HISTORY_MESSAGES` (default 10) in `backend/app/core/config.py` |
| Name, email and password are not sent | `build_prompt` takes only `history`, `chunks` and `user_message`; no user field reaches it |
| Nothing is sent to Gemini before the policy is accepted | `RAGService.prepare` calls `_check_consent` first (line 132), before enrollment, embedding and retrieval; the LLM call comes after; spec `rag-chat` (consent scenarios) |
| Gemini is the service that receives the data | `docs/data-model.md` "Third-party processing". **Changed on 2026-11-18:** the text no longer says Google "acts as processor": under the free tier the terms read on 2026-11-18 say that Google uses the content to improve its products, so the role cannot be asserted (see the Argentine adaptation table below) |
| Conversations are kept until deleted | `docs/data-model.md` "Retention: conversation data lives until the user deletes it or the account is deleted" |
| Deleting a document by the teacher removes its fragments; answers keep file name and page | `docs/data-model.md` (referential actions: chunks cascade with the document; `message_sources.chunk_id` SET NULL; snapshots) |
| Conversations are deleted with the subject or with the account | `docs/data-model.md` referential actions: `conversations.subject_id` CASCADE and `conversations.student_id` CASCADE |
| After unenrolment conversations stop showing and are not deleted; re-enrolment restores them; deletion still possible | `docs/data-model.md` "Visibility"; spec `conversation-history` |
| One conversation can be deleted; all conversations can be deleted | `DELETE /conversations/{id}` and `DELETE /users/me/conversations` in `docs/api-spec.yml`; tests `test_conversations_api.py` |
| Deleting a conversation removes its messages and sources from the application database (no claim about backups) | `docs/data-model.md` (cascades `messages.conversation_id`, `message_sources.message_id`); "no soft delete" |
| The account cannot be deleted and consent cannot be withdrawn without help | `DELETE /users/me` is defined in `docs/api-spec.yml` but is **not implemented** (the running backend exposes only `GET /users/me`, `POST /users/me/consent` and `DELETE /users/me/conversations`); the spec `privacy-consent` has no revocation (see divergence below) |

## Argentine adaptation (2026-11-18)

Sources read the same day: Ley 25.326 and Decreto 1558/2001 (original texts, `argentina.gob.ar/normativa`), Disposición 60-E/2016 and the AAIP page on international transfers, the Gemini API terms (`aistudio.google.com/docs/terms`, effective 2026-03-23). Full mapping in `2026-11-18-argentina-legal-framework.md`.

| Statement in the policy | Evidence | Legal review |
|---|---|---|
| The service is only for people over 18 and accepting declares it | owner decision of 2026-11-18; the Gemini terms forbid clients aimed at or likely to be used by people under 18 (section "Age Requirements"); the tick box carries the declaration | no (a declaration; the application does not verify age) |
| Account data is needed; accepting is needed to use the assistant | the gate holds a student at `/consent` (`RequireConsent`); the backend answers 403 `CONSENT_REQUIRED` | yes: art. 6 asks for the consequences of providing and of refusing the data |
| Gemini may process the data outside Argentina, including countries not recognised as adequate; according to the list of Disposición 60-E/2016 the United States is not among them | Disposición 60-E/2016 art. 3 (2016 text; the list is revised periodically and later acts were not read); the Gemini terms (paid services) say data may be stored transiently in any country where Google or its agents have facilities; the terms give **no location for the unpaid services**, so the possibility is inferred from the paid terms | yes: basis of the transfer (art. 12 of the law, art. 12 of the decree) is an owner input |
| Rights: access in 10 calendar days, free at intervals of six months; rectification, update, suppression in 5 business days; revocation without retroactive effect; habeas data | Ley 25.326 arts. 14 and 16; Decreto 1558/2001 art. 5 (revocation; the law itself has revocation only for the cession, art. 11.2); habeas data regulated in arts. 33 onwards, with arts. 14 and 16 pointing to it | yes: wording and who answers |
| The text refers to the supervisory authority without naming it | the original texts of the law and the decree name the Dirección Nacional de Protección de Datos Personales; the succession by the AAIP was not verified in a norm, so the name is owner input 6 (changed after the review of 2026-11-18) | yes |
| The text no longer says Google is a processor | the Gemini terms (unpaid services): content used to improve products, human review possible, no data processing addendum; paid services: Google states it acts as processor for prompts and responses | yes: the role depends on the service contracted (TD-063) |

## Statements deliberately not made

- No promise about where deletion happens in the interface: the chat screen does not exist yet. The text must be re-checked when it lands.
- No statement that backups are erased: backups of the database exist for development and the production policy is unknown. The text says "from the application database" and carries an owner placeholder about backups (the word "definitive" was removed after the independent review).
- No statement about how Google keeps or uses the data: left as an owner placeholder.

## Owner inputs still open (task 3.2), six markers `[A COMPLETAR POR LA INSTITUCIÓN ...]` in the text

1. Controller: name, domicile and contact (art. 6 b).
2. Legal basis of the processing, with legal review.
3. Google's conditions for this processing (service contracted, data processing addendum, retention, use of the data), place of processing and basis of the international transfer, with legal review.
4. Maximum retention of accounts, if any.
5. Backups: whether they exist, for how long, when deleted data leaves them.
6. The concrete means and the person who attends the requests of access, rectification, suppression and withdrawal, and the contact of the supervisory authority.

## Divergence to report (not fixed here)

`docs/api-spec.yml` defines `DELETE /users/me` ("right to erasure"), and `docs/data-model.md` and the approved scope (deletion of personal data) assume that an account can be deleted, but the endpoint is not implemented and no screen exists for it. The policy says so honestly. Whether to build account deletion is a product decision for a later change.
