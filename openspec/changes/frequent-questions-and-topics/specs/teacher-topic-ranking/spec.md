# Spec Delta

## Purpose

Lets the teacher who owns a subject identify the topics of its PDF material and see which of them the students' answers cite most, in aggregate only.

## ADDED Requirements

### Requirement: Bookmarks are the first source of topics
When a PDF is ingested, the system SHALL take its topics from the bookmarks of the file: the entries of the first level that has two or more, each with its title and the page where it starts. It SHALL NOT infer a topic from the text, from students' messages or from a model, and SHALL send nothing to an external service.

#### Scenario: A PDF with chapters
- **WHEN** a PDF whose top level has three bookmarks becomes ready
- **THEN** the document has three topics with those titles and their page ranges

#### Scenario: A single root
- **WHEN** the top level holds one entry with several children
- **THEN** the children are the topics

#### Scenario: No usable bookmarks
- **WHEN** a PDF has no bookmarks, fewer than two usable entries or more than 100
- **THEN** the document has no topics and the teacher can define them

### Requirement: Bookmark topics cover page ranges
Pages SHALL be the positions of the pages in the file. A topic from bookmarks SHALL run from its start to the page before the next distinct start, and the last one to the highest page with text. Entries that start on the same page SHALL share the range. Entries that start after the highest page with text SHALL be dropped, and pages before the first start SHALL belong to no topic.

#### Scenario: Two bookmarks on one page
- **WHEN** two bookmarks point to page 4
- **THEN** both topics have the same range

#### Scenario: Before the first topic
- **WHEN** an answer cites a page before the first bookmark
- **THEN** it counts for no topic

### Requirement: Bookmark titles are untrusted data
A bookmark title SHALL be stored without control or direction characters, with its whitespace collapsed and cut at 200 characters; an entry left empty or without a resolvable page SHALL be dropped.

#### Scenario: Hostile bookmark
- **WHEN** a bookmark title holds markup, control characters or 10,000 characters
- **THEN** ingestion does not fail and the title is shown inert and bounded

### Requirement: Reading bookmarks never fails a document
A failure, a resource limit or a timeout while reading bookmarks SHALL leave the document with no topics and with the same outcome it would have had without this capability. Topics from bookmarks SHALL be stored in the same transaction that makes the document ready.

#### Scenario: Malformed outline
- **WHEN** a PDF has readable text and a cyclic or broken outline
- **THEN** the document becomes ready with no topics

#### Scenario: Lost job
- **WHEN** a worker loses its job before the final write
- **THEN** no topic of that attempt is stored

### Requirement: The owner reads and defines the topics of a document
The teacher who owns the subject SHALL be able to read the topics of a document, with the highest page with text, and to replace the whole set with titles and page ranges, for any ready PDF, including one uploaded before this capability. No topic SHALL be suggested automatically.

#### Scenario: A PDF without bookmarks
- **WHEN** the owner saves two topics with pages on a ready PDF that has none
- **THEN** the document has those two topics

#### Scenario: Another teacher
- **WHEN** a teacher who does not own the subject reads or writes the topics
- **THEN** the answer is the same as for a document that does not exist and nothing changes

#### Scenario: Student or anonymous
- **WHEN** a student or a caller without a session reads or writes the topics
- **THEN** the request is refused with 403 or 401 and nothing changes

#### Scenario: Document of another subject
- **WHEN** the document does not belong to the subject of the address
- **THEN** the answer is 404

### Requirement: A definition is validated as a whole
A set SHALL hold 0 to 100 topics, each with a title of 1 to 200 characters (counted as code points) with at least one visible character and without control or direction characters, and `1 <= start page <= end page <= highest page with text`. A set whose page ranges differ from the stored ones SHALL NOT hold overlapping ranges. A set that breaks a rule SHALL be refused and nothing SHALL change.

#### Scenario: Overlap
- **WHEN** a request defines pages 1 to 5 and 5 to 8
- **THEN** it is refused and the stored set is unchanged

#### Scenario: Out of range
- **WHEN** a page is zero, reversed or above the highest page with text
- **THEN** it is refused

#### Scenario: Invisible title
- **WHEN** a title holds only characters that show nothing, such as zero-width or blank filler characters
- **THEN** it is refused, and a bookmark with such a title is dropped

#### Scenario: Extreme input
- **WHEN** a request holds huge numbers, control characters, extra fields or an oversized list
- **THEN** it is refused with a client error and never a server error

### Requirement: Only ready documents with pages accept topics
A document that is not ready, or that has no page numbers (text and Markdown), SHALL accept no topics.

#### Scenario: Text file
- **WHEN** the owner writes topics for a `.txt` or `.md` document
- **THEN** it is refused with a reason that says the document has no pages

#### Scenario: Not ready
- **WHEN** the document is pending, processing or failed
- **THEN** the write is refused

### Requirement: Concurrent edits do not overwrite each other
A write SHALL carry the revision it was based on. A write based on an older revision SHALL be refused.

#### Scenario: Two tabs
- **WHEN** two writes are based on the same revision
- **THEN** one is applied and the other is refused as stale

#### Scenario: Deleted meanwhile
- **WHEN** the document is deleted at any point before the write ends
- **THEN** the answer is 404 and no topic remains

### Requirement: Renaming changes no figure
A write that keeps the same page ranges and changes only titles SHALL NOT change which answers are counted.

#### Scenario: Rename
- **WHEN** the owner corrects a title
- **THEN** the topic keeps its figure and starting date

### Requirement: Changed page ranges count only forward
The first set of a document SHALL count every citation in the window. Any later change of ranges, including adding, removing, splitting, merging or clearing, SHALL make that document's topics count only answers of weeks that start after the week of the change. That limit SHALL never move back, also when the set is cleared and defined again.

#### Scenario: First definition
- **WHEN** a document without topics is defined and answers of earlier ended weeks cited it
- **THEN** those answers count

#### Scenario: Moved boundary
- **WHEN** a range is changed from pages 1-5 to 1-4
- **THEN** no figure of that document covers an answer given before the change

#### Scenario: Clear and define again
- **WHEN** the set is emptied and then defined again
- **THEN** answers given before the emptying are not counted

#### Scenario: Other documents
- **WHEN** one document's ranges change
- **THEN** the figures of other documents do not change

### Requirement: Topics are deleted with the document
Deleting a document SHALL delete its topics.

#### Scenario: Deleted document
- **WHEN** a document is deleted
- **THEN** its topics no longer exist and the counts of other documents' topics do not change

### Requirement: Only the owner reads the ranking
The teacher who owns the subject SHALL be able to read its topic ranking. Another teacher, a student and an anonymous caller SHALL be refused.

#### Scenario: The owner
- **WHEN** the owning teacher asks with both switches on
- **THEN** the ranking is returned

#### Scenario: Another teacher
- **WHEN** a teacher who does not own the subject asks
- **THEN** the answer is the same as for a subject that does not exist

#### Scenario: Student or anonymous
- **WHEN** a student or a caller without a session asks
- **THEN** the request is refused with 403 or 401

### Requirement: The window is the one of the dashboard
The ranking SHALL cover only ended weeks (one hour of margin), at most 12, only after the week of the last unenrolment, and SHALL state its window. No request parameter SHALL change it. With no whole week, or no topic defined in the subject, the ranking SHALL be empty and no message SHALL be read.

#### Scenario: Parameters
- **WHEN** a request adds `start`, `end` or any other parameter
- **THEN** the window is the same as without it

#### Scenario: After an unenrolment
- **WHEN** a student was unenrolled in a week of the window
- **THEN** that week and earlier ones are not counted

#### Scenario: No topic in the subject
- **WHEN** the subject has no topic
- **THEN** no question or answer is read

#### Scenario: No whole week
- **WHEN** the unenrolment is in the open or last ended week
- **THEN** `weeks` is 0 and the ranking is empty

### Requirement: A topic counts answers that cited it
The figure of a topic SHALL be the number of distinct answers, to currently enrolled students in the counted weeks, that cited at least one fragment of its document on a page of its range. An answer SHALL count once per topic, and once in each topic it cited. Retrieved fragments that were not cited SHALL NOT count.

#### Scenario: Two fragments of one topic
- **WHEN** an answer cites two fragments or two pages of the same topic
- **THEN** the topic counts it once

#### Scenario: Two topics
- **WHEN** an answer cites fragments of two topics
- **THEN** each counts it once

#### Scenario: No cited source
- **WHEN** an answer has no material or only retrieved fragments
- **THEN** it counts for no topic

#### Scenario: Deleted conversation
- **WHEN** a student deletes a conversation that was counted
- **THEN** the next read no longer counts it

### Requirement: At most five topics are ranked
The ranking SHALL hold at most five topics, ordered by figure, with ties broken by title, document name, document identifier and start page. Each SHALL state its document, its pages and the week from which it is counted. It SHALL NOT say how many topics were left out or withheld.

#### Scenario: Six eligible topics
- **WHEN** six topics can be shown
- **THEN** only the first five of that order are returned

#### Scenario: Fewer
- **WHEN** only two topics can be shown
- **THEN** two are returned and nothing fills the other places

### Requirement: Small groups are withheld
A topic SHALL appear only if at least 5 distinct students are behind its figure. With fewer than 5 active students in the window the ranking SHALL be empty.

#### Scenario: Four students
- **WHEN** a topic was cited in 30 answers to 4 students
- **THEN** it does not appear

#### Scenario: Exactly five
- **WHEN** 5 students are behind a topic and the subject has 5 active students
- **THEN** it can appear

### Requirement: A topic belongs to one document
Topics of different documents SHALL be counted separately even if their titles match. Each ranked topic SHALL list the other current documents that have a topic with the same title, compared without case or extra whitespace, with no figure.

#### Scenario: Same title in two files
- **WHEN** two documents have a topic "Normalization"
- **THEN** their figures are not added and each lists the other as also having it

### Requirement: The ranking says what it leaves out
The response SHALL name the current ready documents without topics, with the reason (not defined, or no pages), and the documents counted from a later week than the window, with that week. It SHALL otherwise hold only the window, the minimum group, the ranked topics and the number of topics defined in the subject.

#### Scenario: Mixed material
- **WHEN** a subject has a defined PDF, an undefined PDF and a text file
- **THEN** the last two are listed with their different reasons

#### Scenario: Recently changed
- **WHEN** a document's ranges changed and no whole week has ended since
- **THEN** its topics are not ranked and the document is listed with the week from which it will count

### Requirement: Responses carry no student data
No response of this capability SHALL hold message text, student identifiers or per-student figures. Reading SHALL store nothing. Titles SHALL be shown as plain text and SHALL NOT be written to logs or sent to a model.

#### Scenario: Busy subject
- **WHEN** the ranking of a subject with many conversations is returned
- **THEN** no field holds text of a message or anything that identifies a student

### Requirement: Topic analytics are switched off by default
The three routes SHALL answer 404 to a teacher unless `TEACHER_ACTIVITY_ENABLED` and `TEACHER_TOPICS_ENABLED` are both true; both default to false. A student and an anonymous caller SHALL be refused the same way whatever the settings are.

#### Scenario: Topics switch off
- **WHEN** activity is on and topics are off
- **THEN** the topic routes answer 404 and the activity and document routes work as before

### Requirement: The views are separate and switched off by default
The ranking and the topic editor SHALL be their own teacher views, linked only when both frontend switches are true: the ranking from the activity dashboard, the editor from each ready PDF of the document list and from the ranking. Opening the dashboard or the document list SHALL send no topic request. The ranking SHALL send one request per load, without polling, parameters or kept responses.

#### Scenario: Switch off
- **WHEN** the topics switch is false
- **THEN** there is no link, both addresses show the not-found page and no request is sent

#### Scenario: Student address
- **WHEN** a student opens either address
- **THEN** the forbidden page is shown and no request is sent

#### Scenario: Dashboard unchanged
- **WHEN** the dashboard loads with topics on
- **THEN** it sends its one activity request and shows its five metrics as before

### Requirement: The editor is simple and warns before losing figures
The editor SHALL let the teacher add, rename and remove rows of title, first page and last page, state that pages are positions in the file and show the highest one, report refused input without losing what was typed, and ask for confirmation before saving changed ranges of a document whose topics were saved before (also if they were later cleared), saying from when figures will count again and that they are shown once that week has ended. It SHALL be usable by keyboard.

#### Scenario: Warning
- **WHEN** the teacher changes a page of a document that has topics
- **THEN** nothing is sent until the warning is confirmed

#### Scenario: Defining again after clearing
- **WHEN** the teacher defines topics on a document whose set was emptied
- **THEN** the same warning is shown

#### Scenario: Rename only
- **WHEN** only titles changed
- **THEN** no warning about figures is shown

#### Scenario: Stale
- **WHEN** the save is refused as stale
- **THEN** the teacher is told to reload and the typed rows stay visible

#### Scenario: Reload fails
- **WHEN** the reload after a stale save fails
- **THEN** the typed rows stay as they were and the failure is shown

#### Scenario: Save in progress
- **WHEN** a save has been sent and not answered
- **THEN** the rows cannot be changed, so nothing typed is discarded

#### Scenario: Focus
- **WHEN** the teacher cancels the warning or a save succeeds
- **THEN** the keyboard focus is on a control or heading of the editor

### Requirement: Figures are readable without the drawing
The ranking SHALL show a horizontal bar per ranked topic and a table with caption and headers holding the same topics, figures, documents, pages and starting weeks. Bars SHALL be hidden from assistive technology, nothing SHALL depend on colour alone, and an accessibility scan of both views SHALL report no violation.

#### Scenario: Table equivalent
- **WHEN** bars are shown
- **THEN** each value and document name is also text

### Requirement: The ranking states what the figures mean
The view SHALL say that a figure counts answers that cited material of the topic; that figures of different topics do not add up; that it does not measure difficulty, understanding or all that students asked; that only documents with topics are covered; and that figures are aggregated, which does not guarantee anonymity. Copy is approved by the owner.

#### Scenario: Wording
- **WHEN** the labels are scanned
- **THEN** none presents a topic as difficult, hard, understood or learned

### Requirement: Every state is explained
The ranking SHALL handle loading, error with retry, forbidden, not found, no topics defined, not enough data and no whole week, and SHALL never draw a bar or a zero for a topic that was withheld.

#### Scenario: No topics defined
- **WHEN** the subject has no topic
- **THEN** the view explains that topics come from bookmarks or from the teacher and lists the documents with their reason

#### Scenario: Not enough data
- **WHEN** topics exist and none can be shown
- **THEN** it reads «Datos insuficientes» with no chart
