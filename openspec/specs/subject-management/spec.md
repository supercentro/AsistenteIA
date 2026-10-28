# subject-management Specification

## Purpose
Lets teachers create and delete the subjects they teach, and lets teachers and enrolled students see only the subjects they are entitled to, so that all later material and conversations can be scoped by subject.

## Requirements

### Requirement: Teachers create subjects
The system SHALL let an authenticated teacher create a subject with a name and an optional description, owned by that teacher, answering 201 with the subject.

#### Scenario: Teacher creates a subject
- **WHEN** a teacher sends `POST /subjects` with a valid name and description
- **THEN** the response is 201 with `id`, `name`, `description`, `teacher_id` equal to the caller and `created_at`

#### Scenario: Description is optional
- **WHEN** a teacher creates a subject without a description
- **THEN** the response is 201 and `description` is null

#### Scenario: Student cannot create a subject
- **WHEN** a student sends `POST /subjects`
- **THEN** the response is 403 `FORBIDDEN` and no subject is stored

#### Scenario: Anonymous client cannot create a subject
- **WHEN** a request without a valid token sends `POST /subjects`
- **THEN** the response is 401 and no subject is stored

### Requirement: Subject input is validated
The subject name SHALL be trimmed, 1 to 150 characters, single-line plain text without control, line-separator or bidirectional characters. The description SHALL be at most 2000 characters without NUL or control characters other than line breaks. Invalid input SHALL answer 422 `VALIDATION_ERROR` without echoing the submitted values.

#### Scenario: Blank or oversized name
- **WHEN** a teacher sends a name that is empty after trimming or longer than 150 characters
- **THEN** the response is 422 and nothing is stored

#### Scenario: Control characters in the name
- **WHEN** a teacher sends a name containing NUL, a line separator or a bidirectional control
- **THEN** the response is 422 and not 500

#### Scenario: Name is trimmed
- **WHEN** a teacher sends the name "  Algebra  "
- **THEN** the stored and returned name is "Algebra"

#### Scenario: Name length boundary
- **WHEN** a teacher sends a name of exactly 150 characters and then one of 151 characters
- **THEN** the first response is 201 and the second is 422

#### Scenario: Invalid description
- **WHEN** a teacher sends a description longer than 2000 characters, or containing NUL or another control character other than a line break
- **THEN** the response is 422 and nothing is stored

#### Scenario: Description with line breaks
- **WHEN** a teacher sends a description containing line breaks and a tab between words
- **THEN** the response is 201 and the inner line breaks and tabs are kept

#### Scenario: Description whitespace
- **WHEN** a teacher sends a description with leading or trailing whitespace, or one that is blank
- **THEN** surrounding whitespace is trimmed and a blank description is stored and returned as null

#### Scenario: Odd text never causes a server error
- **WHEN** a name or description contains lone UTF-16 surrogates, NUL, bidirectional controls or line separators
- **THEN** the response is a 4xx validation error and never a 5xx

### Requirement: Subject names are unique per teacher
The system SHALL reject a second subject with the same trimmed, case-sensitive name for the same teacher with 409 `CONFLICT`, while different teachers MAY use the same name.

#### Scenario: Duplicate name for the same teacher
- **WHEN** a teacher creates a subject with a name they already use
- **THEN** the response is 409 `CONFLICT` and the existing subject is unchanged

#### Scenario: Same name for another teacher
- **WHEN** two different teachers create subjects with the same name
- **THEN** both responses are 201

#### Scenario: Concurrent duplicate creation
- **WHEN** two identical creations race for the same teacher and name
- **THEN** exactly one succeeds and the other answers 409, never 500

### Requirement: Listing shows only the caller's subjects
`GET /subjects` SHALL return, for a teacher, only the subjects they teach and, for a student, only the subjects they are enrolled in, ordered by name and then id, as a plain array without pagination.

#### Scenario: Teacher lists their subjects
- **WHEN** a teacher with two subjects lists subjects while another teacher also has subjects
- **THEN** the response contains exactly the caller's two subjects

#### Scenario: Student lists enrolled subjects
- **WHEN** a student enrolled in one of three existing subjects lists subjects
- **THEN** the response contains only that subject

#### Scenario: Empty list
- **WHEN** a user with no subjects lists subjects
- **THEN** the response is 200 with an empty array

#### Scenario: Anonymous client
- **WHEN** a request without a valid token lists subjects
- **THEN** the response is 401

### Requirement: Subject retrieval hides inaccessible subjects
`GET /subjects/{subject_id}` SHALL return the subject to its owner teacher or to a student enrolled in it, and SHALL answer 404 `NOT_FOUND` with the same body whether the subject does not exist or is not accessible to the caller. A malformed identifier SHALL answer 422.

#### Scenario: Owner teacher
- **WHEN** the owning teacher requests their subject
- **THEN** the response is 200 with the subject

#### Scenario: Enrolled student
- **WHEN** an enrolled student requests the subject
- **THEN** the response is 200 with the subject

#### Scenario: Another teacher
- **WHEN** a teacher who does not own the subject requests it
- **THEN** the response is 404 `NOT_FOUND`, identical to the response for a non-existent id

#### Scenario: Student not enrolled
- **WHEN** a student who is not enrolled requests the subject
- **THEN** the response is 404 `NOT_FOUND`, identical to the response for a non-existent id

#### Scenario: Malformed identifier
- **WHEN** the path identifier is not a UUID
- **THEN** the response is 422 `VALIDATION_ERROR`

### Requirement: Only the owner deletes a subject
`DELETE /subjects/{subject_id}` SHALL be restricted to teachers: a student receives 403, a teacher who does not own the subject receives 404, and the owner receives 204. Deleting a subject SHALL delete its enrollments.

#### Scenario: Owner deletes the subject
- **WHEN** the owning teacher deletes a subject that has enrolled students
- **THEN** the response is 204, the subject and its enrollments no longer exist, and the students' accounts remain

#### Scenario: Another teacher cannot delete
- **WHEN** a teacher who does not own the subject deletes it
- **THEN** the response is 404 and the subject still exists

#### Scenario: Student cannot delete
- **WHEN** a student deletes any subject
- **THEN** the response is 403 and the subject still exists

#### Scenario: Deleting twice
- **WHEN** the owner deletes the same subject a second time
- **THEN** the response is 404

### Requirement: Teachers with subjects cannot be removed
The database SHALL protect a subject's teacher reference so that deleting a teacher account that still owns subjects fails instead of removing the subjects.

#### Scenario: Teacher row with subjects
- **WHEN** a teacher who owns a subject is deleted directly in the database
- **THEN** the deletion is rejected and the subject remains
