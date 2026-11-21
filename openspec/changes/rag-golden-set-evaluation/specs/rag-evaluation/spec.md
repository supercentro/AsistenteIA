## ADDED Requirements

### Requirement: Versioned fictitious golden set
The repository SHALL contain a golden set made only of fictitious documents and cases. Each case SHALL state its kind (answerable, unanswerable, follow-up, injection trap, cross-subject), the question, the earlier messages when it is a follow-up, and the expected outcome: the acceptable sources (file, page and a passage that must appear in the cited chunk) or the expected "no material" answer. The set SHALL have a version identifier that every report repeats.

#### Scenario: Cases are complete
- **WHEN** the golden set is loaded
- **THEN** every case has a kind, a question and an expected outcome, and loading fails with a message naming the case when one is incomplete

#### Scenario: Only fictitious content
- **WHEN** the golden set files are inspected
- **THEN** they contain no real person, real student, real institution document or secret, and the set README states that the content is fictitious and who wrote it

### Requirement: Measurements use the production code path
The harness SHALL obtain the retrieved chunks, the prompt and the selected sources by calling the same functions the chat endpoint uses (the read phase of the chat service, the prompt builder and the citation selection), with real repository authorization, and SHALL NOT reimplement them. When the production code changes, the harness SHALL measure the changed behaviour without being edited.

#### Scenario: Follow-up cases use the stored conversation
- **WHEN** a follow-up case is measured
- **THEN** its earlier messages are stored as a conversation of the synthetic student and the read phase loads them as it does for a real request

#### Scenario: Citation selection is the production function
- **WHEN** the attribution of an answer is classified
- **THEN** the sources considered cited are the ones the production citation selection returns for that answer and the retrieved chunks

### Requirement: Retrieval and refusal metrics
The harness SHALL load the corpus into the isolated test database through the existing ingestion code and report, for the answerable cases, Hit@1, Hit@3, Hit@5 and MRR and the share refused at the configured relevance threshold, and for the unanswerable cases the share that pass the threshold and would reach the model.

#### Scenario: Same input, same numbers
- **WHEN** retrieval mode runs twice on the same golden set, configuration and embedder
- **THEN** both reports contain identical metrics

#### Scenario: Refusal quality is reported
- **WHEN** the set contains unanswerable and answerable cases
- **THEN** the report shows how many answerable cases fell below the threshold and how many unanswerable cases passed it

### Requirement: Sweep and separate follow-up reporting
The harness SHALL repeat the measurement for several values of `CHAT_TOP_K` and `CHAT_RELEVANCE_THRESHOLD` and SHALL report the follow-up cases apart from the self-contained ones, because retrieval does not use the conversation today.

#### Scenario: Sweep of the retrieval settings
- **WHEN** several values of top-k and threshold are given
- **THEN** the report has one row of metrics per combination and states which combination is the configured default

#### Scenario: Follow-ups are reported apart
- **WHEN** the set contains follow-up cases
- **THEN** their metrics appear in a separate row from the self-contained questions

### Requirement: Isolation is part of the measurement
The harness SHALL include cases with a student who has no access (enrolled nowhere, or enrolled only in another subject) and cases whose answer exists only in another subject, and SHALL report as failed every case that returns a chunk of a subject other than the one asked, or whose student without access is not refused. A student who is enrolled MAY legitimately receive chunks of the subject asked about, even for a question about another subject.

#### Scenario: Cross-subject case retrieves a chunk of another subject
- **WHEN** any case returns a chunk of a subject other than the one it asked about
- **THEN** the run is reported as failed and names the case

#### Scenario: Student without access
- **WHEN** a case is asked by a student who is enrolled nowhere or only in another subject
- **THEN** the read phase refuses the request and the case passes only if it was refused

### Requirement: Attribution metrics with the real model
The harness SHALL provide a manual answers mode that asks the cases marked for the model to the real model and reports, for the cases that have expected sources, the share of answers with a valid citation marker, the share that fall back to all retrieved chunks, the share that carry a marker pointing at a chunk without any accepted passage,. A fallback is counted as a fallback and not as a wrong citation, because the model chose no chunk.

#### Scenario: Fallback is visible
- **WHEN** an answer carries no valid marker
- **THEN** the case is counted as a fallback, not as a wrong citation, and listed by identifier in the report

#### Scenario: Wrong citation is visible
- **WHEN** the chunk of a marker chosen by the model does not contain any passage the case accepts
- **THEN** the case is counted as a wrong citation and listed by identifier

### Requirement: Stale and repeated markers, and traps that were not exercised
The harness SHALL list the cases that repeated a wrong marker already present in an earlier assistant message or in a retrieved chunk, and SHALL list the trap cases whose target chunk was never retrieved as not exercised instead of counting them as passed.

#### Scenario: Stale or repeated marker
- **WHEN** a wrong marker is also present in an earlier assistant message of the case or in a retrieved chunk
- **THEN** the case is listed as repeating a stale or repeated marker

#### Scenario: Trap not exercised
- **WHEN** a trap case never retrieved the chunk it was built around
- **THEN** the report lists it as not exercised instead of counting it as passed

### Requirement: Unanswerable cases that reach the model are reviewed by a person
The answers mode SHALL list, with the question and the full answer, every unanswerable case that passed the threshold, marked as pending human review, and SHALL NOT grade them automatically.

#### Scenario: Pending review list
- **WHEN** an unanswerable case reaches the model
- **THEN** the report lists its question and answer under a review heading and counts it as unreviewed

### Requirement: The real model is called only on explicit request, bounded and never from CI
The answers mode with the real model SHALL refuse to run unless it is explicitly requested, SHALL print the number of model calls before making them, SHALL cap them at a configurable maximum that cannot exceed the ceiling authorised by the owner (50 requests), SHALL make one attempt per call without hidden retries, SHALL space the calls, SHALL stop after two failed calls in a row, and SHALL never be part of the automated test suite or of CI.

#### Scenario: Ceiling
- **WHEN** a cap above the authorised ceiling is requested
- **THEN** the harness refuses to start

#### Scenario: Repeated failures
- **WHEN** two model calls fail in a row
- **THEN** the run stops, reports the failures by case and error kind (never the provider message) and writes what it has

#### Scenario: Not requested
- **WHEN** the real model is not explicitly requested
- **THEN** no call to the real model is made

#### Scenario: Calls are announced and capped
- **WHEN** the real model is requested for more cases than the cap
- **THEN** the run stops before the first call and says how many calls were needed and what the cap is

#### Scenario: Secrets are not printed
- **WHEN** any mode runs or fails, including an unexpected error of a library
- **THEN** the output and the report never contain the API key or database credentials

### Requirement: Runs never touch development data
The harness SHALL work only on the isolated test database, SHALL refuse to start when the configured database is not that database, and SHALL remove the synthetic users, subjects and conversations it created when it finishes.

#### Scenario: Wrong database
- **WHEN** the configured database is the development database
- **THEN** the harness stops before writing anything and says why

#### Scenario: Clean after the run
- **WHEN** a run finishes or fails
- **THEN** no synthetic user, subject, document or conversation of the run remains in the database

### Requirement: A persistent ledger bounds the real requests across runs
The harness SHALL require, for every run with the real model, a ledger file that records the total number of real requests the owner authorised and the number already spent, SHALL stop before the first call when the requests the run needs exceed what is left, SHALL add the calls it made to the ledger even when the run fails, and SHALL never raise the authorised total itself.

#### Scenario: No ledger
- **WHEN** the real model is requested without a ledger, or with a missing or invalid one
- **THEN** the harness refuses to start

#### Scenario: Nothing left
- **WHEN** the ledger has no requests left, or fewer than the run needs
- **THEN** the harness stops before the first call and says how many are needed and how many are left

#### Scenario: Calls are reserved before the first request
- **WHEN** a run with the real model is about to make its first call
- **THEN** the ledger already holds the calls the run needs, so that a killed process still leaves them spent, and the real number is settled when the run ends, also when it fails

#### Scenario: The ledger cannot be written
- **WHEN** the ledger cannot be written before or after a run
- **THEN** a run that has not started refuses to start, and a run that finished still writes its report and says that the ledger could not be settled

### Requirement: Accepted passages must be matchable
The harness SHALL check after chunking that every accepted passage lies inside a single stored chunk and SHALL report the cases whose passage does not, because they can never be matched and would silently lower the metrics.

#### Scenario: Passage straddles chunks
- **WHEN** an accepted passage is not contained in any single chunk of its file
- **THEN** the report lists the case among the problems

### Requirement: Reports are reproducible evidence
Each run SHALL write a report that names the golden set version, the code revision, the model and embedding model, the retrieval settings, the date, the mode and the metrics, and SHALL be readable without running the harness again.

#### Scenario: Report header
- **WHEN** a run finishes
- **THEN** the report states the golden set version, the code revision, the settings, the embedder, the model and the mode

### Requirement: CI proves the mechanics, not the quality
The automated suite SHALL run the harness on a small fixture with the deterministic fake embedder and the fake model and SHALL fail when the harness itself breaks. It SHALL NOT call Gemini, SHALL NOT need the real embedding model and SHALL NOT fail because a quality metric changes.

#### Scenario: Harness regression
- **WHEN** a change breaks the loading of the fixture or the metric computation
- **THEN** the automated suite fails

#### Scenario: No external calls in CI
- **WHEN** the automated suite runs
- **THEN** no request to the Gemini API is made and no embedding model is downloaded or loaded
