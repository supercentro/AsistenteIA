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
| Gemini acts as processor | `docs/data-model.md` "Third-party processing" and `docs/frontend-standards.md` (the privacy page names Gemini as processor) |
| Conversations are kept until deleted | `docs/data-model.md` "Retention: conversation data lives until the user deletes it or the account is deleted" |
| Deleting a document by the teacher removes its fragments; answers keep file name and page | `docs/data-model.md` (referential actions: chunks cascade with the document; `message_sources.chunk_id` SET NULL; snapshots) |
| Conversations are deleted with the subject or with the account | `docs/data-model.md` referential actions: `conversations.subject_id` CASCADE and `conversations.student_id` CASCADE |
| After unenrolment conversations stop showing and are not deleted; re-enrolment restores them; deletion still possible | `docs/data-model.md` "Visibility"; spec `conversation-history` |
| One conversation can be deleted; all conversations can be deleted | `DELETE /conversations/{id}` and `DELETE /users/me/conversations` in `docs/api-spec.yml`; tests `test_conversations_api.py` |
| Deleting a conversation removes its messages and sources from the application database (no claim about backups) | `docs/data-model.md` (cascades `messages.conversation_id`, `message_sources.message_id`); "no soft delete" |
| The account cannot be deleted and consent cannot be withdrawn without help | `DELETE /users/me` is defined in `docs/api-spec.yml` but is **not implemented** (the running backend exposes only `GET /users/me`, `POST /users/me/consent` and `DELETE /users/me/conversations`); the spec `privacy-consent` has no revocation (see divergence below) |

## Statements deliberately not made

- No promise about where deletion happens in the interface: the chat screen does not exist yet. The text must be re-checked when it lands.
- No statement that backups are erased: backups of the database exist for development and the production policy is unknown. The text says "from the application database" and carries an owner placeholder about backups (the word "definitive" was removed after the independent review).
- No statement about how Google keeps or uses the data: left as an owner placeholder.

## Owner inputs still open (task 3.2), six markers `[A COMPLETAR POR LA INSTITUCIÓN ...]` in the text

1. Controller: name, address and contact.
2. Legal basis of the processing.
3. Google's terms for this processing and where it takes place.
4. Maximum retention of accounts, if any.
5. Backups: whether they exist, for how long, when deleted data leaves them.
6. The concrete means to exercise the rights and the competent supervisory authority.

## Divergence to report (not fixed here)

`docs/api-spec.yml` defines `DELETE /users/me` ("right to erasure"), and `docs/data-model.md` and the approved scope (deletion of personal data) assume that an account can be deleted, but the endpoint is not implemented and no screen exists for it. The policy says so honestly. Whether to build account deletion is a product decision for a later change.
