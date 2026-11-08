# chunk-retrieval Specification

## Purpose
Defines the single, actor-scoped way to find the chunks most similar to a query embedding, so that later chat and RAG features can retrieve course material without ever reading another subject's chunks or the chunks of a subject the acting user may not access.

## Requirements

### Requirement: Similarity search is scoped by subject and by acting user inside the query
`ChunkRepository.find_similar` SHALL receive the acting user, the subject, a query embedding and `top_k`, and the SQL statement itself MUST restrict the result to chunks of that subject for which the actor is an enrolled student or the owning teacher whose stored role matches, whatever role the caller declares; there MUST be no method, parameter or default that reads chunks without that restriction.

#### Scenario: Enrolled student
- **WHEN** a student enrolled in the subject searches it
- **THEN** the result contains only chunks of that subject, never a chunk of another subject

#### Scenario: Owning teacher
- **WHEN** the teacher who owns the subject searches it
- **THEN** the result contains only chunks of that subject

#### Scenario: Student not enrolled
- **WHEN** a student without an enrollment in the subject searches it
- **THEN** the result is empty, indistinguishable from a subject with no material, and no error is raised

#### Scenario: Another teacher
- **WHEN** a teacher who does not own the subject searches it
- **THEN** the result is empty

#### Scenario: Enrollment removed
- **WHEN** a student's enrollment is removed and the student searches again
- **THEN** the result is empty on the next call

#### Scenario: Unknown subject
- **WHEN** the subject id is a well-formed UUID and the subject does not exist
- **THEN** the result is empty and no error is raised

#### Scenario: Declared role that does not match the stored role
- **WHEN** an actor declares the role `student` or `teacher` but the stored role of that user is the other one (for example a teacher who is also enrolled, a student who appears as the owner of a subject, or a user whose role was changed), or the user does not exist
- **THEN** the result is empty and no error is raised

#### Scenario: Subject id that is not a UUID
- **WHEN** the subject id is not a `uuid.UUID` (a string, a number, `None`, bytes)
- **THEN** a controlled error with fixed text that does not contain the value is raised and no database statement is executed

#### Scenario: Chunks of other subjects are never returned
- **WHEN** several subjects hold chunks closer to the query than any chunk of the requested subject
- **THEN** only chunks of the requested subject are returned, and fewer than `top_k` rows are returned if the subject has fewer chunks

### Requirement: Results are ordered by cosine similarity with a score
`find_similar` SHALL return at most `top_k` chunks of documents in status `ready`, ordered by decreasing cosine similarity (distance operator `<=>`, similarity = 1 − distance) with ties broken deterministically, each result carrying the chunk id, document id, document filename, chunk index, page number, content and similarity.

#### Scenario: Ranking is correct for known vectors
- **WHEN** the subject holds chunks whose cosine similarity to the query is known from deterministic fixtures
- **THEN** the results appear in that order with similarities matching the expected values within a small tolerance

#### Scenario: Limit
- **WHEN** the subject holds more than `top_k` chunks
- **THEN** exactly `top_k` chunks are returned

#### Scenario: Only ready documents
- **WHEN** a subject holds chunks of documents in status `pending`, `processing` or `failed`
- **THEN** those chunks are never returned

#### Scenario: Complete results with many subjects
- **WHEN** many subjects hold chunks and the requested subject holds at least `top_k` chunks that are not the globally nearest
- **THEN** exactly `top_k` chunks of the requested subject are still returned and they equal the result of an exact (unindexed) search of that subject

### Requirement: Invalid query vectors and limits are rejected before the database
`find_similar` MUST reject, with a controlled domain error and without executing any statement, a query embedding that is not exactly 384 finite numbers, whose Euclidean norm (of the single-precision values that the database stores, accumulated in double precision as `vector_norm` does) is outside the reliable range `1e-6 <= norm <= 1e6` (zero included), or a `top_k` outside 1 to 50. The range is justified in `reports/2026-10-28-magnitude-experiment.md`.

#### Scenario: Wrong dimension
- **WHEN** the query embedding has 383, 385 or 0 components
- **THEN** a controlled error is raised and no database statement is executed

#### Scenario: Zero vector
- **WHEN** the query embedding has every component equal to zero
- **THEN** a controlled error is raised

#### Scenario: NaN and infinity
- **WHEN** the query embedding contains `NaN`, `+inf` or `-inf`
- **THEN** a controlled error is raised

#### Scenario: Magnitude outside the reliable range
- **WHEN** the query embedding is a valid direction scaled so that its norm is `1e-7`, `1e-30`, `1e7` or `1e38`, or contains one component large enough to push the norm above `1e6`, or has a norm of exactly `1e6`
- **THEN** a controlled error is raised and no statement is executed

#### Scenario: Magnitude within the safety margin of a limit
- **WHEN** the query embedding has a stored norm closer than a relative `1e-12` to `1e-6` or `1e6`
- **THEN** a controlled error is raised and no statement is executed

#### Scenario: Magnitude at the edges of the range
- **WHEN** the query embedding has the largest single-precision norm below `1e6` (`999999.9375`), or the smallest single-precision norm that is not below `1e-6`
- **THEN** the search runs and returns finite similarities that match an exact double-precision computation within `1e-6`

#### Scenario: Helper never accepts what the database check rejects
- **WHEN** a vector has a norm next to `1e-6` or `1e6` (for example `1e-6` as a double, which is stored just below it; components at single-precision midpoints; sums that differ in the last bits depending on the order of addition)
- **THEN** whenever the validation helper accepts it, the database check `vector_norm(embedding) BETWEEN 1e-6 AND 1e6` accepts the vector the helper returns (the single-precision values); the helper may be stricter only within the relative margin `1e-12` of a limit, where a norm exactly `1e6` is rejected

#### Scenario: Normalised vectors
- **WHEN** the query embedding is a unit vector, or a unit vector rounded to single precision
- **THEN** the search runs normally

#### Scenario: Invalid limit
- **WHEN** `top_k` is zero, negative or above 50
- **THEN** a controlled error is raised

#### Scenario: Values are not leaked
- **WHEN** any of the rejections above happens
- **THEN** the error message and the captured application log contain no component of the embedding

### Requirement: The search is safe under concurrency and errors stay generic
Concurrent searches by different actors on different subjects MUST each return only their own authorized chunks, and a database failure during the search MUST surface as the application's generic error without chunk text, embeddings or SQL parameters in logs.

#### Scenario: Parallel searches
- **WHEN** several actors search different subjects in parallel, including one actor without access
- **THEN** each result contains only chunks the corresponding actor may read, and the unauthorized actor receives an empty result

#### Scenario: Statement-level database error
- **WHEN** the search statement fails at the database
- **THEN** the application error is generic and the captured log contains neither the query embedding nor any chunk text

#### Scenario: Real database error text is never forwarded
- **WHEN** a real SQL exception whose message carries row data (a constraint violation with a `Failing row contains` detail, or a dimension error) is raised while the repository or the application handlers process a chunk statement
- **THEN** the controlled error exposes no `exc.orig` text, SQL parameter or embedding value, and log spies attached to the root logger record none of them
