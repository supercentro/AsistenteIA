# RAG evaluation (answers)

All documents, questions and users of this run are **fictitious**.

- Golden set version: v0.1-draft
- Code revision: 8d028ce-dirty
- Date: 2026-11-20
- Embedder: local
- Model: gemini-3.1-flash-lite
- Configured defaults: top-k 5, threshold 0.3
- Cases: 75; model calls made: 44

## Retrieval and refusal

### Self-contained questions

| top-k | threshold | default | n | Hit@1 | Hit@3 | Hit@5 | MRR | refused |
|---|---|---|---|---|---|---|---|---|
| 3 | 0.2 |  | 45 | 69% | 93% | 93% | 0.793 | 0% |
| 3 | 0.3 |  | 45 | 69% | 93% | 93% | 0.793 | 0% |
| 3 | 0.4 |  | 45 | 67% | 87% | 87% | 0.756 | 4% |
| 3 | 0.5 |  | 45 | 51% | 60% | 60% | 0.548 | 27% |
| 5 | 0.2 |  | 45 | 69% | 93% | 93% | 0.793 | 0% |
| 5 | 0.3 | yes | 45 | 69% | 93% | 93% | 0.793 | 0% |
| 5 | 0.4 |  | 45 | 67% | 87% | 87% | 0.756 | 4% |
| 5 | 0.5 |  | 45 | 51% | 60% | 60% | 0.548 | 27% |
| 8 | 0.2 |  | 45 | 69% | 93% | 93% | 0.796 | 0% |
| 8 | 0.3 |  | 45 | 69% | 93% | 93% | 0.796 | 0% |
| 8 | 0.4 |  | 45 | 67% | 87% | 87% | 0.759 | 4% |
| 8 | 0.5 |  | 45 | 51% | 60% | 60% | 0.548 | 27% |

### Follow-ups (retrieval ignores the conversation)

| top-k | threshold | default | n | Hit@1 | Hit@3 | Hit@5 | MRR | refused |
|---|---|---|---|---|---|---|---|---|
| 3 | 0.2 |  | 8 | 38% | 62% | 62% | 0.500 | 0% |
| 3 | 0.3 |  | 8 | 38% | 62% | 62% | 0.500 | 0% |
| 3 | 0.4 |  | 8 | 25% | 38% | 38% | 0.312 | 38% |
| 3 | 0.5 |  | 8 | 12% | 12% | 12% | 0.125 | 75% |
| 5 | 0.2 |  | 8 | 38% | 62% | 88% | 0.556 | 0% |
| 5 | 0.3 | yes | 8 | 38% | 62% | 75% | 0.531 | 0% |
| 5 | 0.4 |  | 8 | 25% | 38% | 50% | 0.344 | 38% |
| 5 | 0.5 |  | 8 | 12% | 12% | 12% | 0.125 | 75% |
| 8 | 0.2 |  | 8 | 38% | 62% | 88% | 0.556 | 0% |
| 8 | 0.3 |  | 8 | 38% | 62% | 75% | 0.531 | 0% |
| 8 | 0.4 |  | 8 | 25% | 38% | 50% | 0.344 | 38% |
| 8 | 0.5 |  | 8 | 12% | 12% | 12% | 0.125 | 75% |

### Traps with expected sources

| top-k | threshold | default | n | Hit@1 | Hit@3 | Hit@5 | MRR | refused |
|---|---|---|---|---|---|---|---|---|
| 3 | 0.2 |  | 6 | 100% | 100% | 100% | 1.000 | 0% |
| 3 | 0.3 |  | 6 | 100% | 100% | 100% | 1.000 | 0% |
| 3 | 0.4 |  | 6 | 83% | 83% | 83% | 0.833 | 17% |
| 3 | 0.5 |  | 6 | 50% | 50% | 50% | 0.500 | 50% |
| 5 | 0.2 |  | 6 | 100% | 100% | 100% | 1.000 | 0% |
| 5 | 0.3 | yes | 6 | 100% | 100% | 100% | 1.000 | 0% |
| 5 | 0.4 |  | 6 | 83% | 83% | 83% | 0.833 | 17% |
| 5 | 0.5 |  | 6 | 50% | 50% | 50% | 0.500 | 50% |
| 8 | 0.2 |  | 6 | 100% | 100% | 100% | 1.000 | 0% |
| 8 | 0.3 |  | 6 | 100% | 100% | 100% | 1.000 | 0% |
| 8 | 0.4 |  | 6 | 83% | 83% | 83% | 0.833 | 17% |
| 8 | 0.5 |  | 6 | 50% | 50% | 50% | 0.500 | 50% |

### Unanswerable questions that pass the threshold

| top-k | threshold | default | n | passed |
|---|---|---|---|---|
| 3 | 0.2 |  | 10 | 70% |
| 3 | 0.3 |  | 10 | 60% |
| 3 | 0.4 |  | 10 | 40% |
| 3 | 0.5 |  | 10 | 10% |
| 5 | 0.2 |  | 10 | 70% |
| 5 | 0.3 | yes | 10 | 60% |
| 5 | 0.4 |  | 10 | 40% |
| 5 | 0.5 |  | 10 | 10% |
| 8 | 0.2 |  | 10 | 70% |
| 8 | 0.3 |  | 10 | 60% |
| 8 | 0.4 |  | 10 | 40% |
| 8 | 0.5 |  | 10 | 10% |

## Isolation

No case returned a chunk of another subject and every not enrolled student was denied.

## Attribution (answers mode)

| group | n | valid marker | fallback to all chunks | supported | some unsupported |
|---|---|---|---|---|---|
| answerable | 12 | 67% | 33% | 67% | 33% |
| follow_up | 4 | 75% | 25% | 75% | 75% |
| other | 3 | 0% | 100% | - | - |
| trap | 3 | 100% | 0% | 100% | 0% |

Cases that fell back to all retrieved chunks: ans-ia03, ans-ia06, ans-bd04, ans-hi05, unans-01, unans-04, unans-07, follow-01

Cases with a source that lacks every accepted passage: ans-ia03, ans-ia06, ans-bd04, ans-hi05, follow-01, follow-03, follow-07

## Unanswerable cases that reached the model: pending human review (3)

### unans-01

Question: Que son las redes generativas antagonicas y como se entrenan?

Answer:

> El material proporcionado no contiene información sobre qué son las redes generativas antagónicas ni cómo se entrenan.

### unans-04

Question: Que es una base de datos de grafos y para que se usa?

Answer:

> El material proporcionado no contiene información sobre qué es una base de datos de grafos ni para qué se utiliza.

### unans-07

Question: Que ocurrio en la batalla de Trafalgar?

Answer:

> El contexto proporcionado no contiene información sobre la batalla de Trafalgar, por lo que no es posible responder a tu pregunta.


## Problems

- ans-ia02: the model call failed (LLMUnavailableError)
- ans-ia04: the model call failed (LLMUnavailableError)
- ans-ia07: the model call failed (LLMUnavailableError)
- ans-ia09: the model call failed (LLMUnavailableError)
- ans-bd03: the model call failed (LLMUnavailableError)
- ans-bd06: the model call failed (LLMUnavailableError)
- ans-bd08: the model call failed (LLMUnavailableError)
- ans-bd12: the model call failed (LLMUnavailableError)
- ans-hi02: the model call failed (LLMUnavailableError)
- ans-hi04: the model call failed (LLMUnavailableError)
- ans-hi06: the model call failed (LLMUnavailableError)
- ans-hi09: the model call failed (LLMUnavailableError)
- unans-02: the model call failed (LLMUnavailableError)
- unans-05: the model call failed (LLMUnavailableError)
- unans-08: the model call failed (LLMUnavailableError)
- follow-02: the model call failed (LLMUnavailableError)
- follow-04: the model call failed (LLMUnavailableError)
- follow-06: the model call failed (LLMUnavailableError)
- follow-08: the model call failed (LLMUnavailableError)
- trap-doc-02: the model call failed (LLMUnavailableError)
- trap-hist-02: the model call failed (LLMUnavailableError)
- inj-doc-02: the model call failed (LLMUnavailableError)
