# frontend-app-shell Specification

## Purpose
Defines the authenticated application frame, the shared loading, error and empty states, and the read-only subject list, together with the accessibility, responsive and copy rules every screen follows, so that later changes add screens on a common, tested base.

## Requirements

### Requirement: Authenticated layout with role navigation
A signed-in user SHALL see a layout with the application name, a navigation that depends on the role from the profile, the user's name and a sign-out control. Navigation items for features that do not exist yet SHALL NOT be shown.

#### Scenario: Student navigation
- **WHEN** a student is signed in
- **THEN** the navigation offers the subject list and sign-out only

#### Scenario: Teacher navigation
- **WHEN** a teacher is signed in
- **THEN** the navigation offers the subject list and sign-out only, with copy that matches a teacher

#### Scenario: Unknown routes
- **WHEN** any visitor opens a route that does not exist
- **THEN** the Spanish not-found view is shown with a link back to the start

### Requirement: Read-only subject list
The interface SHALL show the subjects returned by `GET /subjects` to students and teachers in the order received, with name and description, plus the role-specific entry points described in the scenarios below (capabilities `frontend-student-chat` and `frontend-teacher-materials`). It SHALL NOT offer control to edit or delete a subject from the list.

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

#### Scenario: Student entry points
- **WHEN** the list is shown to a student
- **THEN** each card has a link to the chat of that subject and the list has the action to delete the whole history

#### Scenario: Teacher sees the create form and the links only
- **WHEN** the list is shown to a teacher
- **THEN** the create-subject form and a link to each subject page are present, and no delete, edit or enrollment control is present

#### Scenario: Student sees the chat links and the history action
- **WHEN** the list is shown to a student
- **THEN** each subject has a link to its chat and the list offers the delete-history action

### Requirement: Shared loading, error and empty states
Every data-driven view SHALL show a loading state while waiting, an error state with a retry control when the request fails, and an empty state when there is nothing to show.

#### Scenario: Loading
- **WHEN** the subject request is in flight
- **THEN** a loading indicator with a polite status announcement is shown and no empty or error state appears

#### Scenario: Empty list
- **WHEN** the API returns an empty list
- **THEN** a Spanish empty message appropriate to the role is shown

#### Scenario: Failure and retry
- **WHEN** the request fails
- **THEN** a Spanish error is announced to assistive technology with a retry control, and activating it sends the request again

#### Scenario: Session expires while loading
- **WHEN** the request is answered with 401
- **THEN** the error state is not shown and the login flow of session expiry takes over

### Requirement: All user-facing text comes from one Spanish module
Every string shown to the user, including labels, buttons, notices, error messages and accessible names, SHALL come from the single Spanish copy module and not be written inline in components.

#### Scenario: No inline copy
- **WHEN** the components and pages are inspected by an automated check
- **THEN** no user-visible Spanish literal is found outside the copy module

### Requirement: Accessible forms and screens
Every input SHALL have a visible label, validation errors SHALL be tied to their fields and announced, a failed submit SHALL move focus to the first invalid field, everything SHALL be operable with the keyboard with a visible focus indicator, and each screen SHALL have a single level-one heading.

#### Scenario: Labels and errors
- **WHEN** a form is shown and then submitted with invalid values
- **THEN** each input has an accessible name, each error is associated with its input and announced, and focus moves to the first invalid field

#### Scenario: Keyboard use
- **WHEN** a user completes login, registration and sign-out with the keyboard only
- **THEN** every step is reachable and activatable in a logical order

#### Scenario: Automated accessibility check
- **WHEN** an automated accessibility scan runs on the login, registration, subject list and not-found screens
- **THEN** it reports no serious or critical violations

### Requirement: Responsive layout
The screens SHALL be usable from a 320 px wide viewport up to desktop widths without horizontal page scrolling.

#### Scenario: Narrow viewport
- **WHEN** a screen is rendered at 320 px width
- **THEN** the form controls, navigation and subject cards fit the viewport and no horizontal scrollbar appears on the page

### Requirement: Loading of screens is split by route
Authentication screens and the authenticated area SHALL be loaded on demand so that a visitor does not download code for screens they cannot open.

#### Scenario: Lazy loading
- **WHEN** the production build is inspected
- **THEN** the login, registration and authenticated screens are emitted as separate chunks
