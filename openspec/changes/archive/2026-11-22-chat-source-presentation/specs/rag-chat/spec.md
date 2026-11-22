## ADDED Requirements

### Requirement: The answer says whether its sources were cited or only retrieved

The chat answer and each assistant message of the history SHALL carry `attribution`: `cited` when the stored sources are exactly the chunks whose valid marker appears in the answer, and `retrieved` when the answer holds no valid marker and its sources are the retrieved chunks. The field SHALL be absent or null when there are no sources, and the sources themselves SHALL NOT change.

#### Scenario: A cited answer
- **WHEN** 3 chunks are retrieved and the answer cites `[2]`
- **THEN** `attribution` is `cited` and `sources` has the entry of rank 2

#### Scenario: An answer without a valid marker
- **WHEN** the answer contains no valid marker, with 3 chunks retrieved
- **THEN** `attribution` is `retrieved` and `sources` has the 3 retrieved chunks

#### Scenario: A refusal in words without markers
- **WHEN** the answer says that the material has no information and holds no marker
- **THEN** `attribution` is `retrieved`

#### Scenario: No sources
- **WHEN** the message is a question or a "no material" answer
- **THEN** `attribution` is absent or null

### Requirement: The flag is derived from the stored answer and the stored ranks

The flag SHALL be derived from the stored answer text and the stored ranks, with no stored column, so that a message gets the same flag in the answer of the chat and in the history, including messages stored before the field existed.

#### Scenario: Same flag in the history
- **WHEN** the student reads the history of a conversation
- **THEN** each assistant message has the same `attribution` that its chat answer had

#### Scenario: A message stored before the field existed
- **WHEN** an old answer was stored with every retrieved rank because its list marker `[1, 2]` was not recognised then
- **THEN** its derived `attribution` is `retrieved`
