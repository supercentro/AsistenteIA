# Spec Delta

## Purpose
Defines the component that turns text into 384-dimension vectors with the local multilingual model, so that ingestion now and the chat later share one contract and never run with a silently different embedder.

## ADDED Requirements

### Requirement: Embeddings come from the local model with the stored dimension
The embedder SHALL use the local `paraphrase-multilingual-MiniLM-L12-v2` model on CPU, produce vectors of exactly 384 components for any input, and send no text to an external service at runtime.

#### Scenario: Normal text
- **WHEN** a batch of texts in Spanish and English is embedded
- **THEN** one vector of 384 components is returned per text, in the same order

#### Scenario: No network at runtime
- **WHEN** the worker runs with the network unavailable
- **THEN** embedding still works because the model files are already local

#### Scenario: Same text, same vector
- **WHEN** the same text is embedded twice
- **THEN** the two vectors are equal within the numeric tolerance of the model

### Requirement: The model is pinned and reproducible
The model SHALL be obtained from a fixed revision and verified by file hashes, so that fetching it again yields identical files, and the worker SHALL run with the model hub offline.

#### Scenario: Same revision, same files
- **WHEN** the model is fetched twice from the pinned revision
- **THEN** the file hashes are identical

#### Scenario: Offline
- **WHEN** the worker starts with the network disabled and the hub set offline
- **THEN** it loads the model and embeds text

### Requirement: The model is loaded once and checked at start
The worker SHALL load the model once at start, verify that it produces 384 components and that a probe vector passes the existing vector validation, and refuse to start otherwise.

#### Scenario: Model files missing or corrupt
- **WHEN** the model cannot be loaded
- **THEN** the worker exits with an error before claiming any job

#### Scenario: Wrong dimension
- **WHEN** the configured model produces a different dimension
- **THEN** the worker exits with an error before claiming any job

### Requirement: A fake embedder is never a fallback
A fake embedder SHALL be selectable only by explicit configuration that is accepted only in the test environment or an explicitly controlled one, and the application MUST NOT switch to it when the real model fails.

#### Scenario: Fake in production
- **WHEN** the fake embedder is configured with the production environment
- **THEN** the configuration is rejected at start

#### Scenario: Real model fails
- **WHEN** the real model fails to load in any environment
- **THEN** the process fails; it does not continue with the fake one

### Requirement: Every vector is validated before it is stored
Each vector SHALL pass the existing validation (finite numbers, 384 components, norm range on the single-precision values) and the validated values SHALL be the ones stored. A vector that fails MUST fail the document with `EMBEDDING_FAILED`.

#### Scenario: Valid vectors
- **WHEN** the model returns ordinary vectors
- **THEN** they are accepted and stored without database constraint errors

#### Scenario: Invalid vector
- **WHEN** an embedding contains a non-finite value or has a norm outside the range
- **THEN** the document fails with `EMBEDDING_FAILED` and no chunk is stored

### Requirement: Token counts use the model's own tokenizer
The embedder SHALL expose a token count, including special tokens, computed with the tokenizer of the same model, so that chunking can guarantee the model input limit of 128 tokens.

#### Scenario: Limit
- **WHEN** a chunk is measured
- **THEN** the count includes the special tokens and is the same one the model applies
