# subject-enrollments Specification

## Purpose
Lets the owning teacher decide which students belong to a subject, so that enrollment can later authorise a student's access to that subject's chat and history.

## Requirements

### Requirement: Enrollment operations are exclusive to the owning teacher
Listing, adding and removing enrollments SHALL answer 401 to anonymous clients, 403 `FORBIDDEN` to students, and 404 `NOT_FOUND` to a teacher who does not own the subject, with the same 404 body as for a subject that does not exist.

#### Scenario: Student calls an enrollment endpoint
- **WHEN** a student lists, adds or removes enrollments on any subject
- **THEN** the response is 403 and nothing changes

#### Scenario: Another teacher
- **WHEN** a teacher who does not own the subject lists, adds or removes enrollments
- **THEN** the response is 404, nothing changes, and no student data is returned

#### Scenario: Anonymous client
- **WHEN** a request without a valid token calls an enrollment endpoint
- **THEN** the response is 401

#### Scenario: Malformed identifiers
- **WHEN** the owner calls an enrollment endpoint with a `subject_id` or `student_id` that is not a UUID
- **THEN** the response is 422 `VALIDATION_ERROR` and never a 5xx

### Requirement: Teachers enroll registered students by email
`POST /subjects/{subject_id}/enrollments` SHALL accept `student_email` using the same ASCII and lowercase email rules as registration, link the existing student account to the subject and answer 201 with the enrollment (`id`, `subject_id`, `student_id`, `student_email`, `created_at`).

#### Scenario: Enroll an existing student
- **WHEN** the owner enrolls the email of a registered student, typed with different letter case
- **THEN** the response is 201 with the student's id and lowercase email

#### Scenario: Invalid email
- **WHEN** the email is malformed, non-ASCII or too long
- **THEN** the response is 422 `VALIDATION_ERROR` without echoing the value and nothing is stored

#### Scenario: Missing field
- **WHEN** the body has no `student_email`
- **THEN** the response is 422

#### Scenario: Odd characters in the email
- **WHEN** the email contains NUL, lone surrogates or control characters
- **THEN** the response is 422 and never a 5xx

### Requirement: Unknown and non-student emails are indistinguishable
Enrolling an email that belongs to no account, or to a teacher, SHALL answer the same 404 `NOT_FOUND` with a fixed message that does not repeat the submitted email, and the system MUST NOT create a pre-enrollment for unregistered emails.

#### Scenario: Unregistered email
- **WHEN** the owner enrolls an email with no account
- **THEN** the response is 404, no enrollment exists, and registering that email later does not enroll it

#### Scenario: Email of a teacher
- **WHEN** the owner enrolls the email of a teacher account
- **THEN** the response has the same status, code and message as for an unregistered email, and nothing is stored

### Requirement: Duplicate enrollments are rejected
Enrolling a student already enrolled in the subject SHALL answer 409 `CONFLICT` and keep the existing enrollment, and concurrent identical requests SHALL never produce 500 or two rows.

#### Scenario: Already enrolled
- **WHEN** the owner enrolls the same student twice
- **THEN** the second response is 409 and exactly one enrollment exists

#### Scenario: Same student in two subjects
- **WHEN** one student is enrolled by two different teachers in their own subjects
- **THEN** both responses are 201

### Requirement: Teachers list their subject's enrollments
`GET /subjects/{subject_id}/enrollments` SHALL return an array with the enrollments of that subject only, ordered by creation time and then id, each with the student's id and email and no other personal data.

#### Scenario: List own subject
- **WHEN** the owner lists a subject with two enrolled students while another subject has other students
- **THEN** the response contains exactly the two enrollments of that subject, without names or credential data

#### Scenario: No enrollments
- **WHEN** the owner lists a subject without enrolled students
- **THEN** the response is 200 with an empty array

### Requirement: Teachers remove enrollments
`DELETE /subjects/{subject_id}/enrollments/{student_id}` SHALL remove that student's enrollment in that subject and answer 204, and SHALL answer 404 when the enrollment does not exist.

#### Scenario: Remove an enrollment
- **WHEN** the owner removes an existing enrollment
- **THEN** the response is 204, the student can no longer retrieve the subject (404) and their account remains

#### Scenario: Missing enrollment
- **WHEN** the owner removes a student who is not enrolled, or a random student id
- **THEN** the response is 404 and other enrollments are unchanged

#### Scenario: Enrollment of another subject
- **WHEN** the owner removes a student who is enrolled only in a different subject
- **THEN** the response is 404 and that other enrollment still exists

### Requirement: Enrollments disappear with their parents
Deleting a subject or a student account SHALL delete the related enrollments at the database level.

#### Scenario: Student account removed
- **WHEN** a student row with enrollments is deleted directly in the database
- **THEN** its enrollments are deleted and the subjects remain
