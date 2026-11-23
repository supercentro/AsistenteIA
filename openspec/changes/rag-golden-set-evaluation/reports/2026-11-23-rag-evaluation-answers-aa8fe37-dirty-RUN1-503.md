# RAG evaluation (answers)

All documents, questions and users of this run are **fictitious**.

- Golden set version: v0.2-draft
- Code revision: aa8fe37-dirty
- Date: 2026-11-23
- Embedder: local
- Model: gemini-3.1-flash-lite
- Configured defaults: top-k 5, threshold 0.3
- Cases: 76; model calls made: 7

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

| group | n | valid marker | fallback to all chunks | supported | wrong marker |
|---|---|---|---|---|---|
| answerable | 4 | 75% | 25% | 75% | 0% |

Cases that fell back to all retrieved chunks: ans-ia06

Cases where the model chose a marker for a wrong chunk: none

Cases that repeated a wrong marker already present in the history or in a document: none

## All answers (4; fictitious data, kept for later review)

### ans-ia02 (answerable)

Question: ¿Qué técnica sirve para encontrar grupos naturales en datos que nadie ha clasificado?

Sources: [1] ia-unidad-1.md; markers [1]

Answer:

> La técnica que sirve para encontrar grupos naturales en datos sin etiquetar es el **agrupamiento** o **clustering**. Esta técnica forma parte del aprendizaje no supervisado, el cual busca estructura oculta en datos que no han sido clasificados previamente [1].
> 
> Fuente: ia-unidad-1.md, página 1.

### ans-ia03 (answerable)

Question: ¿Por qué un modelo puede funcionar perfecto con sus datos de práctica y fallar con datos nuevos?

Sources: [1] ia-unidad-1.md; markers [1]

Answer:

> Un modelo puede presentar este comportamiento debido al **sobreajuste** (o *overfitting*). Esto ocurre cuando el modelo memoriza el ruido del conjunto de entrenamiento en lugar de aprender patrones generales, lo que provoca que deje de generalizar correctamente hacia datos nuevos.
> 
> Este fenómeno se detecta cuando el error en los datos de entrenamiento es muy bajo, mientras que el error en los datos de prueba es alto. Para evitarlo, se recomienda utilizar técnicas de regularización o incrementar la cantidad de datos [1].
> 
> Fuente: *ia-unidad-1.md*, pág. 1.

### ans-ia04 (answerable)

Question: ¿Cómo se estima de forma fiable el rendimiento repartiendo los datos en varios bloques?

Sources: [1] ia-unidad-1.md; markers [1]

Answer:

> Para estimar el rendimiento de forma fiable dividiendo los datos en varios bloques, se utiliza la **validación cruzada**. Este método consiste en dividir los datos en $k$ partes; en cada ronda se entrena el modelo con $k-1$ de ellas y se evalúa con la restante. Al promediar los resultados obtenidos en todas las rondas, se consigue una estimación del rendimiento más estable que la que se obtendría mediante una única partición [1].
> 
> Fuente: *ia-unidad-1.md*, página 1.

### ans-ia06 (answerable)

Question: ¿Cómo se calculan las correcciones que hay que aplicar a cada capa de una red al entrenarla?

Sources: [1] ia-unidad-3.md, [2] ia-unidad-1.md, [3] ia-unidad-4.md, [4] ia-unidad-1.md, [5] ia-unidad-4.md; fell back to every retrieved chunk

Answer:

> El material proporcionado no contiene información sobre cómo se calculan las correcciones que deben aplicarse a cada capa de una red neuronal durante su entrenamiento.


## Notes

- 4 cases marked for the model retrieved nothing and were not sent: unans-03, unans-06, unans-09, unans-10

## Problems

- ans-ia01: the model call failed (LLMUnavailableError)
- ans-ia07: the model call failed (LLMUnavailableError)
- ans-ia08: the model call failed (LLMUnavailableError)
- stopped after repeated model failures
- model error kinds: {'GoogleAPIError:503': 3}
