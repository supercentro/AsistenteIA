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
A mitigation SHALL NOT be recorded as resolving a vector unless the demonstration test of that vector, unchanged, passes after it. For V1 and V3 the difference between two reads caused by one student SHALL NOT equal that student's contribution. Raising N, keeping enrolments, limiting queries and logging accesses SHALL NOT be accepted on their own.

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
