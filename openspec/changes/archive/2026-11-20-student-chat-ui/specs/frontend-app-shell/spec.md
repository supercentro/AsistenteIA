## MODIFIED Requirements

### Requirement: Read-only subject list
The interface SHALL show the subjects returned by `GET /subjects` to students and teachers in the order received, with name and description. A student SHALL additionally get, on each card, a link to the chat of that subject and, on the list, the action to delete the whole history (capability `frontend-student-chat`), and no control to create, edit, delete or enrol. A teacher SHALL additionally get the create-subject form and a link to the page of each subject (capability `frontend-teacher-materials`), and no control to edit, delete or enrol.

#### Scenario: Subjects are shown
- **WHEN** the API returns subjects
- **THEN** each subject appears with its name and, when present, its description

#### Scenario: Student sees only the API result
- **WHEN** a student opens the list
- **THEN** exactly the subjects returned by the API are shown and nothing else is derived or fetched for other subjects

#### Scenario: Teacher sees only the API result
- **WHEN** a teacher opens the list
- **THEN** exactly the subjects returned by the API are shown

#### Scenario: Text is rendered as text
- **WHEN** a name or description contains markup, long unbroken text or line breaks
- **THEN** the markup is shown literally, long text wraps inside its container without horizontal scrolling, and line breaks are preserved in the description

#### Scenario: No management controls
- **WHEN** the list is shown to a student
- **THEN** no create, edit or enrollment control is present and the only subject links lead to the chat of that subject, and for a teacher no delete, edit or enrollment control is present

#### Scenario: Teacher sees the create form and the links only
- **WHEN** the list is shown to a teacher
- **THEN** the create-subject form and a link to each subject page are present, and no delete, edit or enrollment control is present

#### Scenario: Student sees the chat links and the history action
- **WHEN** the list is shown to a student
- **THEN** each subject has a link to its chat and the list offers the delete-history action
