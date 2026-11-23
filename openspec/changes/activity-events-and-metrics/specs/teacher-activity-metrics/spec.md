## ADDED Requirements

### Requirement: A teacher reads aggregate activity of their own subject
The owning teacher of a subject SHALL be able to read, for a bounded window, the number of questions per period, the number of active students, the share of answers with no material, the share of answers with no cited source and the appearances of cited sources per document (answers whose cited sources include the document; never presented as support or as demonstrated use). Nobody else SHALL read them: another teacher, a student and an anonymous caller are refused.

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
- **WHEN** a window from a Wednesday to a Thursday is requested
- **THEN** the response covers the whole weeks that contain both days

#### Scenario: Too long
- **WHEN** a window of 13 weeks is requested
- **THEN** the request is refused with a validation error

### Requirement: The capability is switched off by default
The activity route SHALL answer 404 to a teacher while the setting `TEACHER_ACTIVITY_ENABLED` is false, which is its default, and SHALL keep refusing a student (403) and an anonymous caller (401) in the same way whatever the setting is.

#### Scenario: Off
- **WHEN** a teacher asks while the setting is off
- **THEN** the answer is 404 and nothing is computed
