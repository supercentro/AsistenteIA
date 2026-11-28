# Proposal

## Why

The activity dashboard tells a teacher how much students ask and which documents answers cite, but not what the questions are about. The owner wants the five most consulted topics of a subject, with the topics taken from the teacher's PDF files (R-D12), as the first slice of Feature 3 (`docs/roadmap.md`). Many PDF files have no bookmarks, so bookmarks alone would leave the ranking empty.

## What Changes

- When a PDF is ingested, its topics are read from the bookmarks (outline) of the file, each with a page range. No model is called.
- The owning teacher can define the topics of a ready PDF (titles and page ranges) when it has none, rename topics and change their page ranges. This also works for PDF files uploaded before this change.
- A new aggregate read gives the owning teacher up to five topics of the subject, ranked by the number of answers that cited material of each topic, with the document and pages of each topic and the other documents that have a topic with the same title.
- A change of the page ranges of a document that already had topics counts only from the next whole week, so that two reads cannot be subtracted to isolate earlier answers. Renaming changes no figure.
- A new view shows the ranking as horizontal bars with a table of the same figures and lists the documents without topics, with the reason. A second view edits the topics of one document.
- The window is the one of the dashboard: only ended weeks, at most 12, only after the last unenrolment. The minimum group of 5 applies.
- Off by default behind a switch of its own (`TEACHER_TOPICS_ENABLED`, `VITE_TEACHER_TOPICS_ENABLED`), effective only when the activity switches are also on. Reading bookmarks at ingestion is not behind the switch: it processes no student data.
- The existing dashboard does not change: its endpoint, response, five metrics and requests stay as they are. Its page and the document list only gain a link.

## Capabilities

### New Capabilities
- `teacher-topic-ranking`: identification and definition of the topics of a subject's PDF files and the aggregate ranking of the most consulted ones for the owning teacher.

### Modified Capabilities

None. The activity capabilities are still change deltas (not archived, `docs/base-standards.md` §9.8), and their behaviour does not change.

## Scope

**Out of scope:** grouping of the questions themselves (later part of Feature 3); comprehension difficulties (Feature 4) and teaching recommendations (Feature 7), which stay in the roadmap; topics for text or Markdown files (they have no pages); topics found by headings, clustering or a model; suggested or automatic classification of any kind; topics spanning several documents; date selector, export, comparison between periods; any per-student figure or question text; use with real students.

**Approved scope:** on 2026-11-28 the owner approved extending R-D1 to this feature only, with fictitious data. The wording of `docs/base-standards.md` §8, `docs/backend-standards.md` §9, `openspec/config.yaml` and `docs/roadmap.md` does not say so yet; applying it is the first task, before any code.

**Approved by the owner on 2026-11-28:** R-D1 extension; bookmarks as first source; manual definition as the alternative; topics per document; renaming and page ranges by the teacher; structured storage, conceptually, with migrations on disposable environments only; separate endpoint, switch and view. Pending decisions are in `design.md`.

## Acceptance criteria

The scenarios of `specs/teacher-topic-ranking/spec.md` are the criteria. In short:

1. A PDF with bookmarks becomes ready with its topics; without them, or if reading them fails, it becomes ready without topics.
2. The owner of a subject can define and rename the topics of a ready PDF and set their page ranges; invalid, overlapping or stale input is refused without changing anything.
3. Text and Markdown files, and documents that are not ready, accept no topics; the ranking names the documents without topics and why.
4. The ranking counts each answer once per topic it cited, shows at most five, and never a topic with fewer than 5 distinct students behind it.
5. After the page ranges of a document with topics change, no figure of that document covers an answer given before the change; renaming changes no figure.
6. Only the owner reads or edits; no response has message text, student identifiers or per-student figures.
7. The window matches the dashboard's and no parameter changes it.
8. Both switches off by default; with them off no ranking is computed and no topic route, view or link is available.
9. Everything is readable and usable without the drawing and by keyboard; no label presents frequency as difficulty or understanding.
10. No call to Gemini or any external service is added.

## Impact

- **Authorization and isolation:** three new teacher-only routes, scoped by teacher and subject in the repository (`docs/base-standards.md` §9.4); another teacher or an unknown subject or document answers 404.
- **Personal data:** a new derived processing of students' chat (which material their answers cited, in aggregate). It stores nothing about students. It makes the open risk F8 reveal **what** a real student asked about, down to a page range the teacher chooses (`design.md`, "Risks"). It needs the policy text, legal evaluation and consent version before real students.
- **External services:** none added.
- **Data model:** new tables `document_topic_sets` and `document_topics` (migration, grants) → `docs/data-model.md`.
- **API:** new `GET /subjects/{subject_id}/activity/topics` and `GET`/`PUT /subjects/{subject_id}/documents/{document_id}/topics` → `docs/api-spec.yml` and regenerated frontend types.
- **Backend:** PDF child and loader, ingestion service and job repository, a topic repository, two services, two routers' endpoints, `db_privileges.py`.
- **Frontend:** ranking view, topic editor view, services, hooks, strings, one link on the dashboard and one per ready PDF in the document list.
- **Standards (task 0):** `docs/base-standards.md` §8, `docs/backend-standards.md` §9, `openspec/config.yaml` context, `docs/roadmap.md`.
- **Dependencies:** none new (`pypdf` 7.0.0 is already pinned).
