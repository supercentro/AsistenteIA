## ADDED Requirements

### Requirement: The page is separate, for teachers, and behind two switches
The application SHALL serve `/subjects/:subjectId/activity` only to a signed-in teacher and only when the frontend switch `VITE_TEACHER_ACTIVITY_ENABLED` is true. With it false (the default) the route SHALL show the not-found page, no link to it SHALL be rendered and no request SHALL be sent. The backend switch stays mandatory: the page never assumes it is on.

#### Scenario: Switch off
- **WHEN** the frontend switch is false and a teacher opens the address
- **THEN** the not-found page is shown, no activity request is sent and the subject page has no link to it

#### Scenario: A student
- **WHEN** a signed-in student opens the address
- **THEN** the forbidden page is shown and no activity request is sent

#### Scenario: Not signed in
- **WHEN** a caller without a session opens the address
- **THEN** the login page is shown and no activity request is sent

#### Scenario: Another teacher's or an unknown subject
- **WHEN** the endpoint answers 404 for the subject
- **THEN** the same not-found view is shown for both cases

### Requirement: The page is not part of the enrolments screen
The link to the page SHALL be rendered outside the enrolments section of the subject page and never next to the enrol or unenrol controls, and opening the page SHALL NOT refresh or show the list of enrolments. Changing an enrolment SHALL NOT refetch the activity.

#### Scenario: Placement
- **WHEN** the subject page is rendered with the switch on
- **THEN** the link is in the header area and no enrolment control is inside the activity page

#### Scenario: Enrolment change
- **WHEN** a teacher unenrols a student on the subject page
- **THEN** no activity request is sent

### Requirement: One request per load and no comparison
The page SHALL send one GET per load, with no `start`, `end` or `granularity` parameter, SHALL NOT poll or refetch on focus or reconnection, SHALL NOT retain the response after the teacher leaves, and SHALL NOT offer a date selector, an export, a comparison with another period or a change between weeks.

#### Scenario: One request
- **WHEN** the page loads
- **THEN** exactly one request without query parameters is sent

#### Scenario: Focus
- **WHEN** the window loses and regains focus
- **THEN** no new request is sent

#### Scenario: Leaving and returning
- **WHEN** the teacher leaves the page and returns
- **THEN** a new request is sent and the previous response is not shown or used

### Requirement: Suppressed figures read «Datos insuficientes»
A figure that the endpoint returns as null SHALL be shown as the text «Datos insuficientes», never as zero, an empty bar or a dash. A count is never zero when shown (the endpoint withholds it); a rate of 0% is a real figure and is shown as such. A bar SHALL be drawn only for a non-null figure.

#### Scenario: A week
- **WHEN** a week count is null
- **THEN** its row reads «Datos insuficientes» and has no bar

#### Scenario: Whole subject
- **WHEN** `active_students` is null
- **THEN** only the enrolled count is shown with an explanation and every other figure reads «Datos insuficientes»

#### Scenario: Rates and documents
- **WHEN** a rate or a document figure is null
- **THEN** it reads «Datos insuficientes»

### Requirement: Labels are neutral
The labels SHALL describe what is counted and SHALL NOT attribute quality, correctness, learning or demonstrated use: «Preguntas por semana», «Estudiantes activos», «Respuestas sin material encontrado», «Respuestas sin fuente citada» and «Veces que una respuesta citó el documento». A fixed note SHALL say that the document figure counts citations and does not measure understanding or use. The copy is approved by the owner before implementation.

#### Scenario: No judgement words
- **WHEN** every label and heading of the page is scanned
- **THEN** none contains a word of the forbidden list kept in the tests (quality, error, wrong, good, bad, useful, learning, understood)

### Requirement: Every figure is accessible without the drawing
Every figure SHALL be available as text in a table or list with a caption and headers, bars SHALL be decorative and hidden from assistive technology, no information SHALL depend on colour alone, the page SHALL be usable with the keyboard alone, and an accessibility scan SHALL report no violation.

#### Scenario: Table equivalent
- **WHEN** the weekly bars are rendered
- **THEN** a table with the same values is present and the bars are hidden from assistive technology

#### Scenario: Scan
- **WHEN** the page is scanned in the loaded, empty, suppressed and error states
- **THEN** no accessibility violation is reported

### Requirement: Every state is handled
The page SHALL show a loading state, an error state with a retry control for a failure other than 401, 403 and 404, the forbidden page for 403, the not-found view for 404 and 422, and a clear explanation when everything is suppressed. A 401 ends the session as elsewhere.

#### Scenario: Failure
- **WHEN** the request fails with a server error
- **THEN** an error message with a retry control is shown

#### Scenario: Everything suppressed
- **WHEN** the endpoint withholds every figure
- **THEN** the enrolled count, the fixed privacy note and the explanation are shown, with no bar

### Requirement: The page states its privacy limits
The page SHALL show a fixed note with the minimum group returned by the endpoint, that figures are aggregated and that they can change between consultations, and SHALL NOT show or compute any per-student figure, rate of change or ranking of students.

#### Scenario: Note
- **WHEN** figures are shown
- **THEN** the note names the minimum group of the response

#### Scenario: No derived individual figure
- **WHEN** the page is rendered
- **THEN** it shows only values of the response, with no value derived from two responses
