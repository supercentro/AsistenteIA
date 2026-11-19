---
description: Frontend standards for AsistenteIA (React, TypeScript, Tailwind, React Query, testing).
globs: frontend/**
alwaysApply: false
---

# Frontend Standards

Legend: **MUST** blocks merge; **SHOULD** is recommended. API contract: [`api-spec.yml`](./api-spec.yml).

## 1. Technology Stack

| Area | Choice |
|---|---|
| Framework | React 18 + TypeScript (`strict: true`), built with Vite |
| Styling | Tailwind CSS; Headless UI for accessible primitives |
| Server state | TanStack React Query; Axios as HTTP client |
| Routing | React Router |
| Forms | React Hook Form + Zod (schemas mirror API validation) |
| Testing | Vitest, React Testing Library, MSW (API mocking), Playwright Test (committed E2E suite; Playwright MCP/CLI are agent verification tools, see `base-standards.md` §9.2) |
| Quality | ESLint (typescript-eslint, react-hooks, jsx-a11y), Prettier |

Versions are pinned via `package-lock.json`.

## 2. Project Structure

```
frontend/src/
  pages/        # Route-level views: LoginPage, RegisterPage, PrivacyPage (public), ConsentPage, SubjectsPage (teachers also get the create form), TeacherSubjectPage (teachers: upload and document status), ForbiddenPage, NotFoundPage (later: ChatPage)
  components/   # Reusable UI (ChatWindow, MessageBubble, SourceChip, DocumentUploader, ...)
  hooks/        # React Query hooks (useSubjects, useChat, useConversations, ...)
  services/     # Axios API modules (one per resource), the ONLY place that calls the API
  types/        # api.generated.ts (generated from api-spec.yml, committed, never edited by hand) and api.ts (named aliases)
  lib/          # session.ts (token + profile, memory only), apiClient.ts, apiError.ts, queryClient.ts, schemas.ts, returnTarget.ts, strings.es.ts
  tests/        # test utils and MSW handlers
```

## 3. Coding Standards

- MUST: function components with hooks; no class components.
- MUST: components `PascalCase.tsx`, hooks `useXxx.ts`, services `xxxService.ts`; props typed with `interface XxxProps`.
- MUST: no `any` (unless justified in a comment); no API calls inside components — use hooks that call services.
- MUST: server data lives in React Query (query keys by resource + ids); local UI state in `useState`; avoid global stores unless a real need appears.
- MUST: the access token lives only in `lib/session.ts` (one in-memory store; no `localStorage`, `sessionStorage`, cookies, IndexedDB or URL) and is attached by the Axios interceptor to API requests that are not marked `public` (login, registration); the UI never decodes the token and takes the role from `GET /users/me`.
- MUST: a 401 on a protected request ends the session once (`endSession`), clears the query cache and the router sends the user to login (declarative guards, no imperative redirects from the interceptor); a 401 from login or registration is a form error.
- MUST: the session ends when `expires_in` elapses (timer plus a check before every request); an expired token is never sent.
- MUST: every failure is converted to `ApiError` (status, stable `code`, `Retry-After` seconds); the Spanish text is chosen by `code` and then by status class in `strings.es.ts`; the server `message` and `details` are never displayed or logged. Diagnostics log only method, path (no query) and status.
- MUST: query keys that hold user data include the user id; React Query does not retry 4xx and retries network errors and 5xx once.
- MUST: payload types come from `src/types/api.generated.ts` (`npm run generate:api`; `npm run check:api-types` fails in CI when it is stale). Do not duplicate them by hand; type test fixtures and mocks with them.
- MUST: a post-login return target comes from router state only and is accepted only as a plain internal path (`lib/returnTarget.ts`).
- SHOULD: components ≤ 150 lines; extract logic into hooks.

## 4. UI / UX Rules

- MUST: Tailwind utility classes; extract repeated patterns into components, not custom CSS.
- MUST: loading, empty and error states for every data-driven view. In chat: disable the send button while a request is in flight (no duplicate sends), show a typing indicator, show the controlled "no material" response as a normal assistant message.
- MUST: every assistant message with sources shows source chips (filename + page); sources are rendered as text, never as HTML.
- MUST: render assistant/user text as plain text or sanitised Markdown (no `dangerouslySetInnerHTML` with unsanitised content).
- MUST: forms use React Hook Form with Zod schemas that mirror the limits of `api-spec.yml` without being stricter or looser (login password 1 to 128, registration password 10 to 128); failed submits focus the first invalid field and link errors with `aria-describedby`; submit controls are disabled while a request is pending.
- MUST: first-login consent screen blocks chat until accepted (`POST /users/me/consent`); the privacy page names Gemini as the service that receives the questions, the recent history and the fragments (its role as processor depends on the Gemini service contracted, TD-063), explains the deletion options and the rights of Ley 25.326, and states that the service is only for people over 18. The text never asserts what only the owner or a lawyer can state: those items stay as `[A COMPLETAR ...]` placeholders until approved.
- MUST: a student whose `consent_version` is not `PRIVACY_POLICY_VERSION` is held at `/consent` by the `RequireConsent` layout route around every student route; teachers are not held; a 403 `CONSENT_REQUIRED` from the API re-opens the gate (`markConsentStale`). The gate is usability only: the backend stays the authority.
- MUST: any change of the policy text raises `PRIVACY_POLICY_VERSION` (UI constant and backend default, kept equal by tests) in the same change, so every student accepts the new text (the first text, introduced by `privacy-consent-ui`, has not been released, so it does not raise it). The policy text lives in the copy module (`privacy` section) and is rendered by one component (`PolicyView`) for `/privacy` and for the consent screen. When the chat screen exists, re-check the text about where conversations are deleted.
- MUST: deletion actions (document, conversation, all history, account) require explicit confirmation and state that they are irreversible. The confirmation is an inline panel in the row (a `role="group"` that takes the focus and returns it to the trigger on cancel); no modal dependency is installed.
- MUST: the document list of a subject refreshes by itself every 3 seconds only while some document is `pending` or `processing` (`useDocuments`), never in a background tab and never after the page is left; the status is always shown as text; the Spanish explanation of a `failed` document is chosen by `error_code` and the server `error_message` is never shown.
- MUST: an upload sends one file in the single multipart field `file` and the client decides neither type nor size (the API does); the upload 422 is explained from the closed list of `details.reason` values, which `ApiError.reason` keeps only when it is one of them.
- MUST: accessibility — semantic elements, labels on inputs, keyboard navigation, visible focus, `aria-live` for new chat messages, sufficient contrast.
- MUST: UI strings live in one constants/i18n module (Spanish copy), not scattered in JSX.
- SHOULD: responsive layout, mobile-first.

## 5. Security

- MUST: no secrets in the frontend; only `VITE_API_URL` (public) is configured.
- SHOULD: keep the JWT in memory plus a refresh strategy; if `localStorage` is used for the MVP, document the XSS trade-off in the PR and keep strict content rendering rules above.
- MUST: role-based routes hide teacher/student screens, but the backend remains the authority (never rely on UI checks).

## 6. Testing Standards

- MUST (unit/component, Vitest + RTL + MSW): `ChatWindow` (send, loading, error, no-material), `MessageBubble` (sources chips), `DocumentUploader` (accepted/rejected file, status display), consent gate, delete confirmation dialog. Query by role/label, not by CSS class or test ids when avoidable.
- MUST (E2E, Playwright Test, before final delivery): teacher logs in → creates subject → uploads a text document (wait for `ready`) → enrols a student → student logs in, accepts consent, asks a question → sees an answer with a source chip. The E2E run uses a fake LLM/embedder configured in the backend test profile (no external calls).
- SHOULD: E2E for deleting a conversation and verifying it disappears.
- MUST (CI): coverage thresholds of 70 % on `src/components` and `src/hooks` (`npm run test:coverage`), the generated types up to date (`npm run check:api-types`) and the mocked browser suite (`npm run test:e2e`, API stubbed with `page.route`, no backend).
- MUST: behaviour that depends on the real server (CORS, `Authorization`, 401, token expiry, readable response headers) is verified against the running stack, not only with mocks: agent-run report plus the gated spec `e2e/real-backend.spec.ts` (`E2E_REAL_BACKEND=1`, `E2E_SHORT_TOKEN=1` with a backend running `JWT_EXPIRE_MINUTES=1` in an isolated environment).
- SHOULD: accessibility scans with `vitest-axe` (colour contrast is disabled: jsdom cannot evaluate it) on every new screen.

## 7. Configuration and Quality

- MUST: `tsc --noEmit`, `eslint .` and `prettier --check .` pass before commit.
- MUST: Vite env vars prefixed `VITE_`; `.env.example` committed.
- Scripts expected in `package.json`: `dev`, `build`, `test`, `test:e2e`, `lint`, `format:check`, `typecheck`.

## 8. Performance

- Route-level code splitting (`React.lazy`) for teacher and chat pages; memoise only after profiling; React Query `staleTime` tuned per resource; avoid refetching documents list except while a document is `pending/processing` (poll every few seconds, stop when settled).
