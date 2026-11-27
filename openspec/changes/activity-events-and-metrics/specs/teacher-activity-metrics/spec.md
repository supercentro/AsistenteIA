## ADDED Requirements

### Requirement: A teacher reads aggregate activity of their own subject
The owning teacher of a subject SHALL be able to read, for a bounded window, the number of questions per period, the number of active students, the share of answers with no material, the share of answers with no cited source and the appearances of cited sources per current document (answers whose cited sources include the document, once per answer; never presented as support or as demonstrated use). Nobody else SHALL read them: another teacher, a student and an anonymous caller are refused.

#### Scenario: The owner reads the activity
- **WHEN** the teacher who owns the subject asks for a window of at most 12 weeks
- **THEN** the figures of that window are returned

#### Scenario: Another teacher
- **WHEN** a teacher who does not own the subject asks
- **THEN** the answer is the same as for a subject that does not exist

#### Scenario: A student or an anonymous caller
- **WHEN** a student or a caller without a session asks
- **THEN** the request is refused

### Requirement: Figures from fewer than the minimum group are suppressed
A figure that comes from fewer than N distinct students, including none (N = 5 unless the owner decides otherwise), SHALL be withheld (null), a rate whose denominator has fewer than N students SHALL be null, and a subject with fewer than N active students in the window SHALL show no figure besides the enrolled count.

#### Scenario: A small cell
- **WHEN** a period has questions from N-1 distinct students
- **THEN** its count is withheld and the response says that figures were suppressed

#### Scenario: Exactly the minimum
- **WHEN** a period has questions from N distinct students
- **THEN** its count is shown

### Requirement: The response carries numbers and document names only
The response SHALL NOT contain the text of any question or answer, any student identifier, name or e-mail, or any figure per student, and the computation SHALL NOT store anything.

#### Scenario: No identifying field
- **WHEN** the activity of a busy subject is returned
- **THEN** no field of the response holds text of a message or an identifier of a student

### Requirement: Only current data of enrolled students is counted
The figures SHALL be computed from the data that exists when the request is made, for students enrolled in the subject, so that a conversation deleted by its student no longer counts and an unenrolled student does not count.

#### Scenario: A deleted conversation
- **WHEN** a student deletes a conversation that was counted
- **THEN** the next request no longer counts it

### Requirement: The window is whole weeks and bounded
The window SHALL be aligned to whole weeks (Monday to Sunday, UTC) and cover at most 12 weeks (84 days, within the 90-day limit), and the response SHALL state the window computed. A reversed window, a longer one or a granularity other than week SHALL be refused with a validation error, never a server error.

#### Scenario: Aligned to weeks
- **WHEN** a window from a Wednesday to a Thursday of ended weeks is requested, with no unenrolment since
- **THEN** the response covers the whole weeks that contain both days

#### Scenario: Too long
- **WHEN** a window of 13 ended weeks is requested
- **THEN** the request is refused with a validation error

### Requirement: Only ended weeks are covered
The window SHALL end no later than the last week that has ended, a week counting as ended one hour after its Sunday. A requested end inside the open week or in the future SHALL be cut there, and without parameters the window SHALL be the 12 weeks that end there, before the rule of the last unenrolment below shortens it. A start inside the open week SHALL give a window of 0 weeks.

#### Scenario: The open week
- **WHEN** the requested end is inside the current week
- **THEN** the window ends on the last ended Sunday

#### Scenario: A start in the open week
- **WHEN** the requested start is inside the current week and the end is not before it
- **THEN** the response has 0 weeks

### Requirement: Weeks up to the last unenrolment are not covered
The window SHALL start no earlier than the Monday of the week after the one that holds the last unenrolment of the subject. When no whole week remains, `weeks` SHALL be 0 with `start` the day after `end`, with no weekly cell and no window-wide figure, while the enrolled count and the current documents are still given.

#### Scenario: After an unenrolment
- **WHEN** a student was unenrolled during a week of the window
- **THEN** that week and the earlier ones are not covered

#### Scenario: No whole week
- **WHEN** the unenrolment is in the open week or in the last ended week
- **THEN** `weeks` is 0 and only the enrolled count and the document names are given

### Requirement: Only current documents are listed
The response SHALL list each ready document that the subject has when the request is made and SHALL NOT list a deleted document, even if answers cited it. This SHALL NOT be described as hiding a withheld document figure, which can still be derived or bounded (TD-069, V8 and V9).

#### Scenario: A deleted document
- **WHEN** a cited document is deleted
- **THEN** no later read lists it and no figure is added to another document with the same name

### Requirement: The capability is switched off by default
The activity route SHALL answer 404 to a teacher while the setting `TEACHER_ACTIVITY_ENABLED` is false, which is its default, and SHALL keep refusing a student (403) and an anonymous caller (401) in the same way whatever the setting is.

#### Scenario: Off
- **WHEN** a teacher asks while the setting is off
- **THEN** the answer is 404 and nothing is computed
