# document-ingestion Specification

## Purpose
Defines how an accepted document is turned into searchable chunks by a background worker that survives restarts, never processes a document twice at once, treats every file as hostile and leaves no temporary bytes behind.

## Requirements

### Requirement: A document moves through explicit states
A document SHALL be `pending` when accepted, `processing` while a worker holds it, and end as `ready` (with at least one chunk) or `failed` (with a stable `error_code`). Terminal states MUST NOT change, and a document without chunks MUST NOT be `ready`.

#### Scenario: Successful processing
- **WHEN** a worker finishes a document that produced chunks
- **THEN** the document is `ready`, its chunk count equals the stored chunks and its `error_code` is empty

#### Scenario: Failed processing
- **WHEN** processing cannot complete
- **THEN** the document is `failed`, has one `error_code` from the catalogue and a fixed safe message, and has no chunks

#### Scenario: Terminal state is final
- **WHEN** a late or duplicate worker tries to change a `ready` or `failed` document
- **THEN** nothing changes

### Requirement: Jobs are claimed by one worker at a time
Pending jobs SHALL be claimed with a time-limited lease so that two workers cannot process the same document at once, and a worker whose lease expired MUST NOT be able to write results.

#### Scenario: Two workers
- **WHEN** two workers look for work while one job is available
- **THEN** exactly one claims it

#### Scenario: Stale worker
- **WHEN** a worker keeps running after its lease expired and another worker claimed the job
- **THEN** the stale worker's attempt to store chunks or change the status is rejected and stores nothing

#### Scenario: Claimed again
- **WHEN** a lease expired, a second worker claimed the job and a third worker looks for work
- **THEN** the third worker does not claim it while the second holds a valid lease

#### Scenario: Stale worker cannot mark failure
- **WHEN** a worker that lost its lease tries to mark the document `failed`, change its status, store chunks, renew the lease or erase the bytes
- **THEN** nothing changes

#### Scenario: Long job
- **WHEN** a worker is making progress on a document whose processing lasts longer than one lease period
- **THEN** it renews its lease periodically, without holding a transaction open, and keeps the job until it finishes

#### Scenario: Late renewal
- **WHEN** a renewal arrives after the lease expired or after another worker claimed the job
- **THEN** it changes nothing, the lease is not revived and the worker stops without writing results

#### Scenario: Deadline
- **WHEN** an attempt runs past the job deadline
- **THEN** its lease is no longer renewed and the document fails with `PROCESSING_TIMEOUT`

### Requirement: Work survives restarts and crashes
A job whose worker stopped SHALL become claimable again when its lease expires. Each claim counts as an attempt; after `INGESTION_MAX_ATTEMPTS` (3) the document MUST end `failed` with code `PROCESSING_INTERRUPTED`, so a file that crashes the worker cannot loop forever.

#### Scenario: Worker killed mid-job
- **WHEN** the worker process is killed while processing
- **THEN** after the lease expires another worker processes the document from the start and the result is the same as an uninterrupted run, with no duplicated chunks

#### Scenario: Every process restarted
- **WHEN** the API and the worker restart while documents are `pending`
- **THEN** all of them are processed after the restart

#### Scenario: Poison file
- **WHEN** a file crashes the worker on each attempt
- **THEN** the document ends `failed` with `PROCESSING_INTERRUPTED` after the third attempt and its bytes are discarded

### Requirement: Unfinished jobs expire
A job that has waited longer than `INGESTION_JOB_MAX_AGE_HOURS` (24 by default) without finishing SHALL be failed by a periodic sweep with code `JOB_EXPIRED` and its bytes erased, so that work cannot accumulate when no worker runs.

#### Scenario: No worker for a long time
- **WHEN** a document stays `pending` beyond the maximum age
- **THEN** the sweep marks it `failed` with `JOB_EXPIRED` and erases the bytes

#### Scenario: Young jobs untouched
- **WHEN** a job is younger than the maximum age
- **THEN** the sweep leaves it alone

### Requirement: Deleting during processing cancels the job
If the document is deleted while a worker holds it, the worker SHALL detect it before its next phase or when it stores results, stop, and leave no chunk, row or byte behind, without reporting an error.

#### Scenario: Deleted before storing
- **WHEN** the document is deleted while embeddings are being computed
- **THEN** the worker discards the work and no chunk of that document exists

#### Scenario: Subject deleted
- **WHEN** the subject is deleted while its documents are being processed
- **THEN** the same happens for each document

#### Scenario: Cancelled worker fails
- **WHEN** processing of a deleted document fails afterwards
- **THEN** the worker does not try to record a failure and writes nothing

### Requirement: No database resource is held while a file is processed
While a file is parsed or embedded the worker SHALL hold no open transaction, no row or advisory lock and no pooled connection, using short transactions only to claim, renew and store results, so that the work never blocks the database or other requests.

#### Scenario: Slow processing
- **WHEN** a document is being embedded slowly
- **THEN** the database shows no open transaction and no lock owned by the worker, and uploads, listing and deletion are not delayed

#### Scenario: Abandoned transaction
- **WHEN** a worker bug leaves a transaction open
- **THEN** the database closes it after the idle-in-transaction timeout

### Requirement: PDFs are parsed in an isolated, limited process
PDF parsing SHALL run in a separate short-lived process with a wall-clock timeout, a CPU limit and a memory limit, receiving the bytes by pipe and returning only bounded text, so that a hostile file cannot stall or exhaust the worker. Parser output other than extracted text MUST be discarded.

#### Scenario: Parser exceeds a limit
- **WHEN** the parsing process exceeds its wall-clock, CPU or memory limit, or its output cap
- **THEN** it is killed and the document fails with `PROCESSING_TIMEOUT` (time or CPU) or `RESOURCE_LIMIT_EXCEEDED` (memory or output) and the worker keeps running

#### Scenario: Small file, huge page
- **WHEN** a small PDF holds a page that needs far more CPU than the limit
- **THEN** the CPU limit stops the parsing process and the document fails with `PROCESSING_TIMEOUT`

#### Scenario: Not parsed in the HTTP process
- **WHEN** any PDF is processed
- **THEN** it is parsed only in the isolated child of the worker, never in the API process

#### Scenario: Too many pages
- **WHEN** a PDF has more than `MAX_PDF_PAGES` (300) pages
- **THEN** it fails with `TOO_MANY_PAGES` before its text is extracted

#### Scenario: Encrypted PDF
- **WHEN** a PDF is encrypted
- **THEN** it fails with `ENCRYPTED_PDF` even if it opens without a password

#### Scenario: Corrupt PDF
- **WHEN** a PDF is truncated or malformed
- **THEN** it fails with `CORRUPT_FILE`

#### Scenario: PDF without text
- **WHEN** a PDF has no extractable text, such as a scan
- **THEN** it fails with `NO_EXTRACTABLE_TEXT`

#### Scenario: Extracted text too large
- **WHEN** the extracted text exceeds the character cap
- **THEN** it fails with `TEXT_TOO_LARGE`

### Requirement: Text and Markdown are read as strict UTF-8 data
`.txt` and `.md` content SHALL be decoded as strict UTF-8 and stored as text. Markdown MUST NOT be interpreted, rendered or converted to HTML, and embedded HTML or links MUST remain inert text.

#### Scenario: Markdown with HTML
- **WHEN** a Markdown file contains `<script>` or raw HTML
- **THEN** the text is stored unchanged as data

#### Scenario: Invalid bytes found late
- **WHEN** the content is not valid UTF-8 when the worker decodes it
- **THEN** the document fails with `CORRUPT_FILE`

### Requirement: Content is normalised before it reaches the database
Before chunking, the text SHALL have NUL and other control characters (except line breaks and tabs), bidirectional controls and line separators removed or replaced, Unicode space characters turned into plain spaces, and chunks without any visible character dropped. No stored chunk may be blank, including text made only of no-break or next-line characters.

#### Scenario: NUL in a PDF
- **WHEN** the extracted text contains NUL characters
- **THEN** they are removed and the document is stored without a database error

#### Scenario: Blank-looking page
- **WHEN** a page contains only no-break spaces and next-line characters
- **THEN** it produces no chunk

#### Scenario: No visible text at all
- **WHEN** the whole document is blank after normalisation
- **THEN** it fails with `NO_EXTRACTABLE_TEXT`

### Requirement: Chunks fit the embedding model and keep their page
The text SHALL be split into chunks of about 100 model tokens with an overlap of about 20, never crossing a page, each measured again with the real tokenizer including special tokens and never above 128 tokens, so that no text is silently truncated at embedding time. `page_number` is kept for PDFs and empty for text. Indexes are consecutive from zero.

#### Scenario: Long paragraph
- **WHEN** a paragraph is longer than one chunk
- **THEN** it is split with overlap and every chunk measures at most 128 tokens including special tokens

#### Scenario: Words that tokenize badly
- **WHEN** the text has very long words, URLs, digits, emoji or non-Latin scripts
- **THEN** no chunk exceeds 128 tokens

#### Scenario: Page numbers
- **WHEN** a PDF page 7 is split into three chunks
- **THEN** the three chunks have `page_number` 7 and consecutive `chunk_index`

#### Scenario: Too many chunks
- **WHEN** the document would produce more than `MAX_CHUNKS_PER_DOCUMENT` (2,000) chunks
- **THEN** it fails with `TOO_MANY_CHUNKS` before any embedding is computed

### Requirement: Results are stored atomically
Chunks, the chunk count and the `ready` status SHALL be written in one transaction by the worker that holds the lease. Until that commit, none of the document's chunks may exist, so search never sees a partial document.

#### Scenario: Failure while storing
- **WHEN** any error happens before the commit
- **THEN** no chunk of the document exists and the document is marked `failed`

#### Scenario: Searchable only when ready
- **WHEN** a document is `pending`, `processing` or `failed`
- **THEN** similarity search never returns its chunks; and once it is `ready` it can be found by the enrolled students and the owner

#### Scenario: Retried job
- **WHEN** a job is run again after an interruption
- **THEN** the document ends with exactly one set of chunks

### Requirement: Temporary bytes are removed in every outcome
The uploaded bytes SHALL be erased when the document becomes `ready` or `failed`, when it is deleted, and when the job is abandoned after its last attempt. No uploaded file is written to a durable location, and a periodic cleanup MUST remove bytes left behind by any other path.

#### Scenario: Success and failure
- **WHEN** a document ends `ready` or `failed`
- **THEN** no bytes of the file remain anywhere in the database or on disk

#### Scenario: Cancelled
- **WHEN** the document is deleted
- **THEN** the bytes disappear with it

#### Scenario: Leftover bytes
- **WHEN** a job has bytes but its document is already terminal
- **THEN** the cleanup erases the bytes

#### Scenario: Cleanup is light
- **WHEN** the cleanup runs
- **THEN** it uses ordinary short statements and never rewrites the table or takes an exclusive table lock; reclaiming the file space of erased bytes is left to autovacuum or to approved manual maintenance

### Requirement: Failures use a closed catalogue of codes
A failed document SHALL carry exactly one code from: `NO_EXTRACTABLE_TEXT`, `ENCRYPTED_PDF`, `CORRUPT_FILE`, `TOO_MANY_PAGES`, `TEXT_TOO_LARGE`, `TOO_MANY_CHUNKS`, `PROCESSING_TIMEOUT`, `RESOURCE_LIMIT_EXCEEDED`, `EMBEDDING_FAILED`, `PROCESSING_INTERRUPTED`, `JOB_EXPIRED`, `PROCESSING_FAILED`; and a fixed message per code that never includes parser, database or system text.

#### Scenario: Unknown exception
- **WHEN** an unexpected exception occurs while processing
- **THEN** the document fails with `PROCESSING_FAILED` and a fixed message, and the exception text is neither stored nor logged

#### Scenario: Stable codes
- **WHEN** the same kind of failure happens twice
- **THEN** the same code and message are reported

### Requirement: Processing logs only identifiers and counts
Worker and parser logs SHALL contain document and job identifiers, counts, durations and codes, and MUST NOT contain filenames, file or chunk content, embeddings, paths, parser stderr or exception messages.

#### Scenario: Hostile file
- **WHEN** a file with markers in its name, content and metadata is processed and fails
- **THEN** no marker appears in any log line or stored message
