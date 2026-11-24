## ADDED Requirements

### Requirement: Each inference vector is demonstrated by a test before any mitigation
The change SHALL provide tests with fictitious data and an in-memory repository, no persistent data, that reproduce the vectors V1 (unenrolment differencing), V2 (padding with controlled accounts), V3 (window differencing) and characterise V4 (a heavy contributor), and SHALL record the failing run in `reports/` before any mitigation is written.

#### Scenario: V1, unenrolment differencing
- **WHEN** six enrolled students asked in one week 2, 2, 2, 2, 2 and 3 questions, the owner teacher reads, the student with 3 is removed from the enrolments, and the teacher reads again
- **THEN** the weekly cell goes from 13 to 10 and `active_students` from 6 to 5, so the difference is that student's exact contribution, and the test records that the vector is reproduced

#### Scenario: V2, padding with controlled accounts
- **WHEN** four accounts controlled by the teacher asked 3 questions each in a week and one real student asked 2
- **THEN** the cell shows 14 and `active_students` shows 5, the teacher subtracts the 12 it produced and recovers 2, and the same read with a real student who asked nothing shows no figure, so the presence of a figure also reveals activity

#### Scenario: V3, window differencing
- **WHEN** a student asked only in the first of 12 weeks, and the teacher reads the window of weeks 1 to 12 and then the window of weeks 2 to 13
- **THEN** `active_students` goes from 6 to 5 and the window-wide rates and document figures move, while the weekly cells of weeks 2 to 12 do not, and the test records which figures leak

#### Scenario: V4, a heavy contributor
- **WHEN** five students asked 50, 1, 1, 1 and 1 questions in a week
- **THEN** the cell shows 54 and the test records that one student is 93 % of a shown figure, as a characterisation, not as a recovery

### Requirement: F8 stays unconfirmed until it is reproduced end to end
Finding F8 (padding with controlled accounts) SHALL be recorded in TD-069 as **not confirmed** until a test with a disposable test database shows that a teacher can create student accounts, enrol them by email and make them ask questions in the teacher's own subject. A service-level reproduction alone SHALL be recorded as "arithmetic reproduced, feasibility pending".

#### Scenario: Service level only
- **WHEN** the in-memory test of V2 reproduces the recovery and the end-to-end test has not run
- **THEN** the finding reads "arithmetic reproduced, feasibility pending" and is not called confirmed

#### Scenario: End to end refutes it
- **WHEN** the end-to-end test shows that a step is not possible, such as the enrolment of an account the teacher controls
- **THEN** the finding is closed as refuted with the step that fails, and the arithmetic stays documented

#### Scenario: End to end confirms it
- **WHEN** every step succeeds on the test database with fictitious data
- **THEN** F8 is recorded as confirmed, Major, and remains open

### Requirement: A mitigation is accepted only when the vector test passes
A mitigation SHALL NOT be recorded as resolving a vector unless the demonstration test of that vector, unchanged, passes after it. For V1 the test is independence from the cut-off past, not equality of answers: after the removal every response is identical whatever any student wrote before the marker. For V3 two windows SHALL NOT differ by one student's activity. Raising N, keeping enrolments, limiting queries or logging accesses are not accepted on their own.

#### Scenario: A higher N only
- **WHEN** a change raises the minimum group from 5 to 10 and the V1 test runs with twelve students
- **THEN** the weekly difference still equals the removed student's contribution, so V1 stays open and the documentation does not call it mitigated

#### Scenario: A control that only detects
- **WHEN** a mitigation records each read and each change of enrolment but leaves the figures as they are
- **THEN** it is classified detective, the vector tests still fail, and the vectors stay open with the control listed as a partial answer

### Requirement: The right of erasure is preserved
Every mitigation SHALL keep that, after a student deletes conversations or the account, the next aggregate excludes that student's data. Nothing SHALL keep a student's activity in a figure after such a deletion, and no mitigation SHALL need data about a person that the deletion flows do not remove.

#### Scenario: A student deletes their conversations
- **WHEN** a student whose questions are in a shown cell deletes their conversations and the teacher reads again
- **THEN** the figures no longer include those questions

#### Scenario: A student deletes the account
- **WHEN** the account of a student is deleted and the teacher reads again
- **THEN** the enrolled count and every figure exclude the student, and no row about the student remains in anything the mitigation added

### Requirement: Controls are classified and each residual risk is stated
The design SHALL classify each control as preventive, detective or organisational, and SHALL state for each vector what remains after it: V1, V2, V3, V4 and the departure of a student by their own choice. A residual risk SHALL NOT be omitted or described as mitigated by a control that does not pass its test.

#### Scenario: The classification is complete
- **WHEN** the design is reviewed
- **THEN** every control has one class and every vector lists its residual risk, including that V2 has no technical fix without an identity control

### Requirement: Decisions that change an approved decision wait for the owner
No migration, change of the response or its parameters, retention of an enrolment after unenrolment, identity verification of students, persistent access record or change of a figure's precision SHALL be implemented without the owner's recorded approval. Keeping enrolments reverses the approved D-M5 and SHALL be presented as an option.

#### Scenario: Option A without approval
- **WHEN** the work reaches a task that needs a migration or keeps an enrolment after unenrolment and no approval is recorded
- **THEN** the task stays blocked and nothing is implemented

### Requirement: The change enables nothing
Both switches `TEACHER_ACTIVITY_ENABLED` and `VITE_TEACHER_ACTIVITY_ENABLED` SHALL stay false by default, and the capability SHALL NOT be used with real students. Enabling needs a separate decision after the vectors are resolved or accepted, the policy text exists, the legal review is done and the consent version exists.

#### Scenario: Defaults
- **WHEN** the change is complete
- **THEN** `backend/.env.example` and `frontend/.env.example` keep both switches false and no test or document enables them

### Requirement: Figures cover only whole weeks that start after the last unenrolment
The aggregate SHALL compute every figure over the requested whole weeks that have ended and whose start is at or after the first Monday 00:00 UTC strictly after the subject's `last_unenrolment_at`, and the response window SHALL report those effective weeks, which may be fewer than requested or none. With a null marker only the ended-weeks rule applies.

#### Scenario: A removal in the middle of a week
- **WHEN** the teacher removes a student on a Wednesday and reads at once
- **THEN** the week of that Wednesday and every earlier week are withheld, `window.start` is the next Monday or later and `window.weeks` is smaller than requested

#### Scenario: A removal exactly on a Monday 00:00
- **WHEN** the marker is a Monday at 00:00:00 UTC
- **THEN** the week that starts at the marker is also withheld, so the first effective week is the following Monday

#### Scenario: No whole week remains
- **WHEN** the marker is inside the current week or inside the last ended week
- **THEN** `window.weeks` is 0, `window.start` is the day after `window.end`, `questions` is empty, every window-wide figure is null, `enrolled_students` is shown and `suppressed` is true

#### Scenario: An old marker and a null marker
- **WHEN** the marker is more than 13 weeks old, or null
- **THEN** the window and every figure are those of a subject without any removal, still limited to ended weeks

### Requirement: The marker is non-personal, monotonic and written with the unenrolment
`last_unenrolment_at` SHALL be a nullable timestamp of the subject with no reference to a student. The route that removes an enrolment SHALL set it in the same transaction, before deleting the enrolment (order: subject, then enrolment), to the database clock and never to an earlier value, whether or not the student had asked anything. A removal that deletes nothing SHALL roll it back. No other path SHALL delete an enrolment.

#### Scenario: A student without activity
- **WHEN** the teacher removes a student who never asked anything
- **THEN** the marker is set exactly as for an active student and the response is the same

#### Scenario: A rollback or a failure
- **WHEN** either statement fails or the transaction rolls back
- **THEN** the enrolment is still present and the marker is unchanged

#### Scenario: Nothing deleted
- **WHEN** the teacher removes a student who is not enrolled and receives 404
- **THEN** the marker is unchanged

#### Scenario: Operations that do not move it
- **WHEN** a read, an enrolment, a re-enrolment, a deletion of conversations or of an account takes place
- **THEN** the marker is unchanged

#### Scenario: Two removals
- **WHEN** two removals happen one after the other or at the same time
- **THEN** the marker holds the later value and never decreases

#### Scenario: Another path
- **WHEN** the code is searched for deletions of enrolments
- **THEN** the only one is the repository method that sets the marker, apart from the cascade of a deleted subject or account

### Requirement: A read after a removal cannot be subtracted from a read before it
For every pair of worlds that differ only in messages created before the marker in force, written by any student including the removed one, every response read after the removal SHALL be identical: figures, window, `enrolled_students` and `suppressed`. Equality between answers before and after SHALL NOT be required. The proof uses random classes with fixed seeds and adds no dependency.

#### Scenario: Other students differ
- **WHEN** the messages of the other students before the removal differ between two worlds, the student is removed and the teacher reads
- **THEN** the two responses are identical

#### Scenario: The removed student differs
- **WHEN** only the removed student's earlier messages differ and the student is re-enrolled after the removal
- **THEN** the two responses are identical

#### Scenario: Random sequences
- **WHEN** many classes, removals, re-enrolments and reads are generated with fixed seeds
- **THEN** no response after a removal depends on any message created before the marker

#### Scenario: A weaker formulation is rejected
- **WHEN** the worlds differ only in the removed student's messages and the student is not re-enrolled
- **THEN** the responses are identical even without any mitigation, so this formulation alone is not accepted as evidence

#### Scenario: The property fails without the rule
- **WHEN** the filter of the effective window is removed
- **THEN** the test fails for removals with and without re-enrolment, and that mutation check is recorded

### Requirement: No question of a removed student is dated at or after the marker
A chat turn and an unenrolment of the same student and subject SHALL be ordered so that either the turn is persisted before the removal, with `created_at` below the marker, or the turn is refused. The marker SHALL be taken after the existing per-student, per-subject lock and SHALL NOT add a second advisory lock.

#### Scenario: The turn first
- **WHEN** a turn holds the lock and the removal waits
- **THEN** after both commit every message of the student has `created_at` below the marker

#### Scenario: The removal first
- **WHEN** the removal commits and the waiting turn proceeds
- **THEN** the turn is refused and no message is added

#### Scenario: Lock order with an upload
- **WHEN** a removal runs while a document upload holds the subject row
- **THEN** both complete without a deadlock

#### Scenario: Lock order with the deletion of the subject
- **WHEN** a removal and the deletion of the same subject run at the same time
- **THEN** one waits for the other and neither fails with a deadlock

### Requirement: Permissions and exposure stay minimal
The application role SHALL be allowed to update the marker column of `subjects` and no other new column, and no response about a subject SHALL carry the marker. The migration SHALL have a working `downgrade`, set the marker to the migration time for existing subjects that already hold conversations (their history cannot be shown to have been unread) and leave it null for the others.

#### Scenario: The role
- **WHEN** the role-bound suites run
- **THEN** the application role can update `description` and `last_unenrolment_at` of `subjects` and nothing else new, and the other roles gain nothing

#### Scenario: Exposure
- **WHEN** a subject is read by its teacher or by an enrolled student
- **THEN** the response has no marker field

#### Scenario: The migration
- **WHEN** it is applied to a database with subjects and then reversed
- **THEN** each subject with conversations has the migration time as marker, each subject without conversations has none, and the column is gone after the downgrade

### Requirement: The dashboard states the limit of the history
When the response has fewer weeks than the 12 the page requests, the page SHALL say that the weeks before a recent change of enrolments are not shown, and with 0 weeks it SHALL say that there are no whole weeks yet. It SHALL NOT show a withheld figure as zero, and with no weeks it SHALL hide the window line and the table. It SHALL always say «Se muestran solo semanas completas.» The copy was approved by the owner on 2026-11-23.

#### Scenario: Fewer weeks
- **WHEN** the response has 5 weeks
- **THEN** the page shows the weeks it has and the note «Por un cambio en las inscripciones, solo se muestran las semanas posteriores a ese cambio.»

#### Scenario: No weeks
- **WHEN** the response has 0 weeks
- **THEN** the page shows the enrolled count, «Datos insuficientes» in the window-wide cards and the note «Por un cambio en las inscripciones, todavía no hay semanas completas para mostrar.», with no window line, no table and no bar

### Requirement: F1 stays open until the demonstration passes
F1 SHALL NOT be recorded as mitigated, even only for the unenrolment form, until the non-interference tests pass unchanged, the mutation checks are recorded and the independent adversarial review has no open Blocker or Major. F8, window differencing, F6 and F7 SHALL stay open whatever the result.

#### Scenario: The code is merged but a test fails
- **WHEN** the non-interference test fails or is skipped
- **THEN** F1 stays open and TD-069 does not change its status

#### Scenario: Everything passes
- **WHEN** the tests, the mutation checks and the review are complete
- **THEN** TD-069 records the unenrolment form of F1 as mitigated by A2, and F8, V3, F6 and F7 are listed as still open

### Requirement: An activity read uses one snapshot
The read of the activity SHALL run in one snapshot, one read-only transaction at REPEATABLE READ or one statement, so that the marker and the facts it filters come from the same moment. A read that overlaps the commit of a removal SHALL return either the whole pre-removal answer or the post-removal answer, never the old marker with the new cohort.

#### Scenario: A removal commits in the middle of a read
- **WHEN** a separate session commits a removal between two statements of a read
- **THEN** the read returns the answer of the instant it started, with the student counted and the earlier weeks shown

#### Scenario: A read after the commit
- **WHEN** a read starts after the removal committed
- **THEN** the weeks before the marker are withheld and the student is not counted

#### Scenario: The mutation check
- **WHEN** the read is split into separate snapshots
- **THEN** the race test fails and the mutation check is recorded

### Requirement: Candidate V5 is demonstrated before any rule against it
Candidate V5, two reads in the same open week that differ by what was asked in between and the first questions of an enrolled student showing at once, SHALL be demonstrated with an in-memory test and recorded as confirmed or refuted. The rule against it, that only ended weeks are shown (A2b), was decided on 2026-11-23 and is the requirement "Only ended weeks are shown".

#### Scenario: Two reads in one week
- **WHEN** five students asked 2 questions each this week, the teacher reads, one more question is asked and the teacher reads again
- **THEN** the cell of the week goes from 10 to 11 and the test records that the vector is reproduced

#### Scenario: A newly enrolled student
- **WHEN** a sixth student is enrolled, the teacher reads, the student asks once and the teacher reads again
- **THEN** the cell goes from 11 to 12 and `active_students` from 5 to 6, which is the addition form of F1

#### Scenario: The decision
- **WHEN** V5 is recorded as reproduced
- **THEN** TD-069 notes the addition form, and A2b closes it with its own tests

#### Scenario: Whole weeks only
- **WHEN** the page shows any figures
- **THEN** the note «Se muestran solo semanas completas.» is visible next to the window

### Requirement: Only ended weeks are shown
The window SHALL end with the last week that has ended, a week counting as ended one hour after its Sunday (UTC); the open week SHALL NOT be shown, a requested end inside it SHALL be clamped, and a response SHALL depend only on messages created before the start of the current week, apart from the enrolled count.

#### Scenario: Two reads in one week
- **WHEN** five students asked 2 questions each, the teacher reads, one more question is asked in the same week and the teacher reads again
- **THEN** the two responses are identical

#### Scenario: A newly enrolled student
- **WHEN** a sixth student is enrolled in the open week and asks once between two reads
- **THEN** the two responses are identical except `enrolled_students`

#### Scenario: The boundary
- **WHEN** the teacher reads on Monday at 00:59:59 UTC and on Monday at 01:00:00 UTC
- **THEN** the responses differ by exactly one week: the second has the week that ended the Sunday before, and the margin of one hour lets a chat transaction that began before midnight commit first

#### Scenario: An end inside the open week
- **WHEN** the request has an `end` inside the current week
- **THEN** the window ends on the last ended Sunday

#### Scenario: The mutation check
- **WHEN** the open week is let through
- **THEN** the temporal property fails and the check is recorded

### Requirement: The loss of availability is documented
The documents of the change SHALL state, with the figures measured on the reference model, that after a removal no figure is shown for 7 to 14 days (mean about 11) and that the full window of 12 weeks returns after 12 to 13 weeks, that the data stays stored, and that a mistaken enrolment corrected by a removal has the same effect.

#### Scenario: The documents
- **WHEN** `docs/data-model.md` and the design are read
- **THEN** the durations, the reason and the absence of any loss of stored data are stated
