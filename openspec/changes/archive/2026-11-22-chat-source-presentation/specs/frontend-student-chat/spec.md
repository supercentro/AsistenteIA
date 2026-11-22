## MODIFIED Requirements

### Requirement: Sources are shown as provided, without guarantees
Each assistant message SHALL list the sources given by the API: file name, page when there is one, and the snippet in an expandable detail. The interface SHALL NOT state or imply that a source proves a statement, and SHALL show a neutral note that the information must be checked in the original document.

#### Scenario: Answer with sources
- **WHEN** an answer has sources
- **THEN** each source shows its file name and page (when not null) and an expandable snippet shown as text, in the order given by the API

#### Scenario: Source whose document was deleted
- **WHEN** a source has no chunk or document id
- **THEN** it is shown the same way, with its stored file name and page

#### Scenario: Neutral wording
- **WHEN** sources are shown
- **THEN** no text says that they support, prove or guarantee the answer, and a note says that the information must be checked in the original

#### Scenario: Sources are text
- **WHEN** a file name or snippet contains markup or direction characters
- **THEN** it is shown as text and never interpreted

## ADDED Requirements

### Requirement: Cited sources show their marker and retrieved fragments are shown apart
Sources cited by the answer (`attribution` cited) SHALL be shown under a label that says material cited in the answer, each with its marker number. Sources that were only retrieved (`attribution` retrieved, absent or null) SHALL be shown apart, collapsed, under a label that says the answer does not indicate which fragments it used, without marker numbers.

#### Scenario: Answer with cited sources
- **WHEN** an answer has sources with `attribution` cited
- **THEN** each source shows its marker number, in the order given by the API, under the label of material cited in the answer

#### Scenario: Answer with retrieved fragments only
- **WHEN** an answer has sources with `attribution` retrieved
- **THEN** they are inside a collapsed detail whose label says that the answer does not indicate which fragments it used, each with file name, page and snippet but no marker number

#### Scenario: Answer from an older server without the field
- **WHEN** the API gives sources and no `attribution`
- **THEN** they are shown as retrieved material, without marker numbers
