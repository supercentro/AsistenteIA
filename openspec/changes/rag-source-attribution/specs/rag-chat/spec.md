## MODIFIED Requirements

### Requirement: The sources of an answer are the chunks it cites

Each context block SHALL carry its retrieval rank as `[n]` and the model SHALL be told to cite the blocks it used that way. A citation is `[n]` or a comma-separated list `[n, m]`; a range such as `[1-3]` is not a citation. The response and `message_sources` SHALL hold only the chunks whose valid marker appears in the answer, with their retrieval rank; with no valid marker they SHALL hold all the retrieved chunks.

#### Scenario: Only the cited chunks are the sources
- **WHEN** 3 chunks are retrieved and the answer cites `[2]`
- **THEN** `sources` has one entry, with `rank` 2 and the filename, page and snippet of the second chunk, and one `message_sources` row is persisted

#### Scenario: Invalid citation markers are ignored
- **WHEN** the answer contains `[9]` or `[0]` and no valid marker, with 3 chunks retrieved
- **THEN** no chunk is selected by them and the sources are the 3 retrieved chunks

#### Scenario: Answer without citation markers
- **WHEN** the answer contains no marker
- **THEN** the sources are all the retrieved chunks that were in the prompt, ordered by rank

#### Scenario: A list of ranks cites each of them
- **WHEN** 3 chunks are retrieved and the answer cites `[1, 3]`
- **THEN** `sources` has the entries of ranks 1 and 3

#### Scenario: Adjacent markers cite each of them
- **WHEN** 3 chunks are retrieved and the answer cites `[1][2]`
- **THEN** `sources` has the entries of ranks 1 and 2

#### Scenario: A range is not a citation
- **WHEN** 3 chunks are retrieved and the answer contains `[1-3]` and no other marker
- **THEN** no chunk is selected by it and the sources are the 3 retrieved chunks

#### Scenario: A list with an invalid rank keeps the valid ones
- **WHEN** 3 chunks are retrieved and the answer cites `[2, 9]`
- **THEN** `sources` has the entry of rank 2 only

## ADDED Requirements

### Requirement: Markers of other turns and of documents are not citations of the current turn

The prompt SHALL carry a bracketed number `[n]` only as the rank label of a context block of the current turn. A citation marker found in the replayed history, in the text of a retrieved chunk or in a filename SHALL be rewritten in the prompt as `(n)`, keeping the rest of the text. Stored messages, stored chunks and the snippets of the sources SHALL NOT change.

#### Scenario: A marker of a previous answer does not collide
- **WHEN** the history holds an assistant answer that cites `[2]` and the new turn retrieves chunks
- **THEN** the prompt shows that answer with `(2)` in its place and its other words unchanged, and the only `[2]` of the prompt is the label of the second context block

#### Scenario: A marker written inside a document is neutralised
- **WHEN** a retrieved chunk contains `[3]` or `[1, 2]`
- **THEN** the prompt shows `(3)` or `(1, 2)` inside that chunk and the label of each context block is unchanged

#### Scenario: A marker in a filename is neutralised
- **WHEN** a source filename contains `[2]`
- **THEN** the prompt header shows `(2)` in the filename

#### Scenario: Stored data and snippets are untouched
- **WHEN** a turn replays a history with markers and retrieves a chunk with a marker
- **THEN** the stored messages, the stored chunk and the `snippet` of the sources keep their original text
