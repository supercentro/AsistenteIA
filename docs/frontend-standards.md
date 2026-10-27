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
  pages/        # Route-level views: LoginPage, SubjectsPage, ChatPage, TeacherSubjectPage, PrivacyPage
  components/   # Reusable UI (ChatWindow, MessageBubble, SourceChip, DocumentUploader, ...)
  hooks/        # React Query hooks (useSubjects, useChat, useConversations, ...)
  services/     # Axios API modules (one per resource), the ONLY place that calls the API
  types/        # TypeScript types derived from api-spec.yml
  lib/          # axios instance, auth token handling, utilities
  tests/        # test utils and MSW handlers
```

## 3. Coding Standards

- MUST: function components with hooks; no class components.
- MUST: components `PascalCase.tsx`, hooks `useXxx.ts`, services `xxxService.ts`; props typed with `interface XxxProps`.
- MUST: no `any` (unless justified in a comment); no API calls inside components — use hooks that call services.
- MUST: server data lives in React Query (query keys by resource + ids); local UI state in `useState`; avoid global stores unless a real need appears.
- MUST: the access token is attached by an Axios interceptor; a 401 clears the session and redirects to login.
- SHOULD: components ≤ 150 lines; extract logic into hooks.

## 4. UI / UX Rules

- MUST: Tailwind utility classes; extract repeated patterns into components, not custom CSS.
- MUST: loading, empty and error states for every data-driven view. In chat: disable the send button while a request is in flight (no duplicate sends), show a typing indicator, show the controlled "no material" response as a normal assistant message.
- MUST: every assistant message with sources shows source chips (filename + page); sources are rendered as text, never as HTML.
- MUST: render assistant/user text as plain text or sanitised Markdown (no `dangerouslySetInnerHTML` with unsanitised content).
- MUST: first-login consent screen blocks chat until accepted (`POST /users/me/consent`); the privacy page names Gemini as a processor and explains deletion options.
- MUST: deletion actions (conversation, all history, account) require explicit confirmation and state that they are irreversible.
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
- SHOULD: coverage ≥ 70% on components and hooks.

## 7. Configuration and Quality

- MUST: `tsc --noEmit`, `eslint .` and `prettier --check .` pass before commit.
- MUST: Vite env vars prefixed `VITE_`; `.env.example` committed.
- Scripts expected in `package.json`: `dev`, `build`, `test`, `test:e2e`, `lint`, `format:check`, `typecheck`.

## 8. Performance

- Route-level code splitting (`React.lazy`) for teacher and chat pages; memoise only after profiling; React Query `staleTime` tuned per resource; avoid refetching documents list except while a document is `pending/processing` (poll every few seconds, stop when settled).
