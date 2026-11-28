# Design

## Context

- Chunks are cut per page, so `document_chunks.page_number` is exact for PDF files and null for text and Markdown. There is no notion of section or topic.
- `page_number` is the position of the page in the file (1-based), not the printed page number. Citations already show it.
- The number of pages of a document is not stored. Pages without text produce no chunk.
- When an answer cites, the stored `message_sources` are the cited fragments; when it does not, they are every retrieved one. `attribution_of` tells the two apart. A deleted chunk leaves `chunk_id` null.
- The uploaded bytes are erased once a document is terminal, so bookmarks can only be read during ingestion. Page numbers of earlier documents are available.
- PDF files are parsed in an isolated child with resource limits (`app/rag/pdf_child.py`).
- The activity read already has the window rules, the minimum group, the "weeks after a marker" rule, a `REPEATABLE READ` read-only snapshot and teacher-scoped queries (`activity_service.py`, `activity_repository.py`). The activity endpoint accepts `start` and `end`.
- `docker compose up` runs the `migrate` service, which applies new migrations to whatever volume the project uses.
- Spike of 2026-11-27 (throwaway, fictitious file): `pypdf` 7.0.0 returns bookmark titles, nesting and start pages, and an empty list when there are none. It says nothing about how many real course PDF files have bookmarks.

## Goals / Non-Goals

**Goals:** a deterministic, local, explainable topic list that works with or without bookmarks; reuse of the stored citations and of the dashboard's privacy rules; no change to chat, retrieval, embeddings or the existing dashboard.

**Non-Goals:** automatic or suggested classification, merging of topics across documents, mitigation of F8 or of the other open inference risks.

## Decisions

### D1. Two sources: bookmarks first, the teacher otherwise

| Option | Quality | Cost and data | Main problem |
|---|---|---|---|
| **Bookmarks (chosen, first source)** | the author's own structure | none external; one more bounded parse | many files have none |
| **Teacher definition (chosen, alternative)** | as good as the teacher makes it | manual work | editing can be used to cut figures (D5) |
| Heading heuristics | uneven | none external | wrong topics shown as fact; hard to test |
| Clustering of chunk embeddings | unstable | local | no readable labels; topics move when files change |
| Model over the material | likely good labels | sends whole files to the provider: up to about 500,000 input tokens per document at the 2,000,000 character limit (rough 4 characters per token) | provider terms (TD-063), no metering |

Topics from bookmarks are read at ingestion (D8). The teacher can define topics on any ready PDF, including earlier ones, because only chunk page numbers are needed. So earlier files do not need to be uploaded again.

### D2. A topic belongs to one document

Figures of equal titles are **not** added. Adding them would let a teacher delete one file, read again and obtain the part that came only through it, possibly below the minimum group (the problem V7 corrected for documents). Related documents are listed by title only.

### D3. Page ranges and citations

A topic is `(title, start_page, end_page)`, inclusive. A citation belongs to a topic when its chunk is of that document and `start_page <= page_number <= end_page`. The join is made at read time from `message_sources.chunk_id` to `document_chunks`; nothing is written on messages or chunks, so existing citations are matched without any data migration.

Against double counting:

- The figure is the number of **distinct answers**, so several cited fragments or pages of one topic count once.
- Topics the teacher defines must not overlap, so one page counts for one topic.
- A chunk never crosses a page, so a fragment has exactly one page.
- Citing two topics counts once in each: the figures are not additive, and the view says so.
- Bookmarks that start on the same page share one range and get equal figures; this is the only overlap, and it can only be removed by changing the ranges.

### D4. What a valid definition is

- Only a ready document with at least one chunk with a page. `last_page` = the highest chunk page of the document.
- 0 to 100 topics; `1 <= start_page <= end_page <= last_page`; ranges do not overlap; pages may be left without a topic.
- Title: 1 to 200 characters after collapsing whitespace; control and direction characters are refused (bookmark titles are cleaned instead).
- The whole set is replaced in one request that carries the `revision` it was read with; a stale revision is refused.
- When only titles change (the same collection of ranges as stored), it is a rename: the overlap rule is not applied to the unchanged ranges and nothing about counting changes.

For bookmarks, the end of a topic is the page before the next distinct start; the last ends at `last_page`; an entry starting after `last_page` is dropped.

### D5. Editing must not isolate earlier answers

If ranges could be moved over answers already given, a teacher could read pages 1 to 5, change to 1 to 4, read again and subtract: the answers citing page 5, whatever the group size. Rule:

- The **first** set of a document (from bookmarks or from the teacher) counts every citation in the window.
- **Any later change of ranges** (add, remove, move, split, merge, clear) sets `ranges_changed_at` on the document's set. From then on, that document's topics count only answers in weeks that start after the week of the change, with the same rule used after an unenrolment. The marker never decreases and survives clearing the set.
- A rename sets nothing.

Two reads under different ranges therefore cover different weeks and cannot be subtracted. The price: after a correction, that document's figures start again and stay empty until a whole week has ended. The view warns before saving.

| Alternative | Why not recommended |
|---|---|
| Ranges apply to all past answers on every edit | allows the subtraction above |
| Even the first set counts only forward | stricter (one chosen cut of past answers is not possible), but a teacher who defines topics sees nothing for one to two weeks and earlier citations are never used |
| No change of ranges after the first set | a mistake could only be fixed by uploading the file again |

The recommended rule leaves **one** retroactive cut per document, chosen without seeing any per-page figure. Whether to accept that is pending (Q1).

### D6. Documents without pages or without topics

| Case | Behaviour |
|---|---|
| Text or Markdown | no page numbers: no topics can be defined; listed as "no pages"; their citations count for no topic |
| Scanned PDF with no text | already fails ingestion; not affected |
| PDF with some pages without text | ranges may include them; they hold no citation |
| PDF without bookmarks, not yet defined | listed as "topics not defined", with a link to define them |
| No topic in the whole subject | the view explains both sources and shows no chart |
| Ranges changed and no whole week yet | the document is listed with the week from which it counts |
| Not ready (pending, processing, failed) | no topics can be defined; not listed |

A whole-document topic for text files was considered and left out: it would repeat the document figure the dashboard already shows.

### D7. Storage

- `document_topic_sets`: `document_id` (primary key), `subject_id` (composite foreign key to `documents(id, subject_id)`, `ON DELETE CASCADE`), `source` (`bookmarks` | `teacher`), `revision`, `ranges_changed_at` (nullable).
- `document_topics`: `id`, `document_id` (foreign key to the set, cascade), `position`, `title` (200), `start_page`, `end_page`; unique `(document_id, position)`; checks on the pages; index on the document.
- `source` stays `bookmarks` after a rename and becomes `teacher` when ranges are saved.
- Grants: worker inserts both; API reads both, inserts both, updates `document_topic_sets` and deletes `document_topics` (the set is replaced); CLI none.
- Concurrency: replacing locks the set row; two first definitions collide on the primary key and one is refused as stale; a document deleted meanwhile answers 404.
- A migration with `downgrade` (R-D7). `documents` and `message_sources` are not changed.

The set is a table of its own because the marker must outlive an empty topic list.

### D8. Bookmarks: a second run of the isolated child

The outline is read in a separate run with the same limits, after the text succeeded. A crash, kill or timeout there yields no topics and cannot fail the document. The parent validates the protocol as strictly as for pages and applies the title rules. Recursion depth and visited entries are bounded. The run is skipped when less than its timeout, plus the time of the final write, remains of the job deadline, and the lease keeps being renewed. Topics are written inside the fenced `complete` transaction. Levels: the first level with two or more entries; fewer than two usable entries or more than 100 give none.

### D9. Routes, switch and views

- `GET /subjects/{subject_id}/activity/topics`: ranking, no query parameters, in the snapshot dependency.
- `GET` and `PUT /subjects/{subject_id}/documents/{document_id}/topics`: read and replace the set. Teacher only; the write commits before answering.
- All three behind `TEACHER_ACTIVITY_ENABLED` and `TEACHER_TOPICS_ENABLED`.
- Views: the ranking, linked from the dashboard; the editor of one document, linked from the document list and from the ranking.

A `topics` field in the activity response was rejected: it changes a capability that is not archived. The window computation is shared with `ActivityService`, not copied.

### D10. Chart and editor

CSS bars as in `WeeklyQuestions.tsx`, with the table as the accessible form; no chart library (R-D8 not needed). The editor is a list of rows (title, from page, to page) with add and remove, saved as a whole. No document preview, no drag and drop, no suggestions.

### Cost

No model call and no Gemini use. One extra bounded parse per PDF, at most 100 short rows per document, and one aggregate read of the same order as the activity read (computed in the process, TD-070, unmeasured). The real cost is the teacher's time for files without bookmarks.

## Impact compared with the previous proposal

| Area | Bookmarks only | Added by the manual alternative |
|---|---|---|
| Data model | one table | a second table for revision and marker; wider API grants (insert, update, delete) |
| Backend | extraction, ranking | two routes (one writes), validation, concurrency, per-document counting start |
| Frontend | one view | an editor view with validation, warning and conflict handling; links in the document list; roughly double the frontend work (judgement, not measured) |
| Privacy | fixed topics | teacher-chosen ranges: new attack surface, handled in D5 |
| Earlier files | upload again | defined in place |

Implementation order keeps a usable increment first: storage, teacher definition, ranking, views, then bookmark reading.

## Pending decisions

Approved on 2026-11-28 (owner): R-D1 extension limited to this feature and fictitious data; bookmarks first; manual alternative; topics per document; renaming and ranges by the teacher; storage conceptually, migrations only on disposable environments; separate endpoint, switch and view.

| # | Pending | Recommended | Needed before |
|---|---|---|---|
| Q1 | Does the first set of a document count past citations? (D5) | yes; later range changes count forward only | task 1 |
| Q2 | Text and Markdown without topics (D6) | accept for this slice | task 1 |
| Q3 | Edit `openspec/config.yaml` and the standards with the approved R-D1 wording (an OpenSpec file, outside the limits of the planning request) | authorise it with the start of implementation | task 0.3 |
| Q4 | Spanish copy of both views | drafted in task 5.1 | task 5 |

## Risks / Trade-offs

- **[F8 gets worse]** With controlled accounts a teacher pads a group and learns **which topic** one real student's answers cited; with teacher-defined ranges the topic can be a single page. The minimum group does not stop it. → Not mitigated, not accepted. Switches off, fictitious data only; register as a new debt entry linked to TD-071. `base-standards.md` §9.8 does not allow closing a change with an open Major finding: expect this change not to be archivable while the review confirms it.
- **[One retroactive cut]** A first definition chosen on purpose (for example, every page but one), compared with the dashboard's document figure over the same weeks, can bound how many answers cited only the excluded pages. Also possible with bookmarks that skip first pages. → Not mitigated (Q1 stricter option removes the chosen form); characterised by a test and registered.
- **[Combining figures]** Topic counts next to the weekly and per-document figures can bound a withheld topic. → Same treatment.
- **[Reads a week apart]** The window slides, so two reads differ by the weeks that entered and left. → Family of TD-069.
- **[Figures with different starts]** After a change, one ranking can compare a document counted over 2 weeks with another over 12. → Each row states its start; the ranking says so.
- **[Corrections cost data]** Fixing a wrong page empties that document's figures for one to two weeks. → Warning before saving.
- **[Wrong page numbers]** The teacher may type printed numbers. → The editor says which numbering is used and shows `last_page`.
- **[Teacher does not define]** Files without bookmarks stay out and bias the ranking. → The view lists them.
- **[Attribution quality]** Answers without a valid marker are not counted (TD-062), and a cited fragment does not prove what the student asked. → The label says what is counted.
- **[Frequency read as difficulty]** → Fixed note and forbidden-word test.
- **[Earlier activity]** Counts answers written under earlier policies (TD-072). → Blocks real use.
- **[Titles]** Teacher or file controlled text: never sent to a model, never logged, rendered as text.
- **[Errors]** Extraction errors give no topics; bad input to the routes never gives a server error.

## Migration Plan

Migration and grants are applied only to disposable databases until the owner authorises more. Because `docker compose up` runs `migrate`, the branch is not started against a persistent volume: verification uses a separate Compose project or containers with disposable volumes, and the owner's stack and demo are not touched. Rollback: switches off (immediate); `downgrade` drops the two tables and their data only. That data includes `ranges_changed_at`: after a downgrade, an upgrade and a new definition, citations from before a change count again, so a read taken before the rollback could be subtracted from one taken after it. After a rollback the topics switch stays off unless the markers are restored. Deploying needs its own authorisation.
