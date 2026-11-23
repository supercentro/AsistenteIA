# RAG evaluation (answers)

All documents, questions and users of this run are **fictitious**.

- Golden set version: v0.2-draft
- Code revision: aa8fe37-dirty-run2
- Date: 2026-11-23
- Embedder: local
- Model: gemini-3.1-flash-lite
- Configured defaults: top-k 5, threshold 0.3
- Cases: 41; model calls made: 11

## Retrieval and refusal

### Self-contained questions

| top-k | threshold | default | n | Hit@1 | Hit@3 | Hit@5 | MRR | refused |
|---|---|---|---|---|---|---|---|---|
| 3 | 0.2 |  | 20 | 65% | 95% | 95% | 0.783 | 0% |
| 3 | 0.3 |  | 20 | 65% | 95% | 95% | 0.783 | 0% |
| 3 | 0.4 |  | 20 | 65% | 95% | 95% | 0.783 | 0% |
| 3 | 0.5 |  | 20 | 50% | 65% | 65% | 0.558 | 20% |
| 5 | 0.2 |  | 20 | 65% | 95% | 95% | 0.783 | 0% |
| 5 | 0.3 | yes | 20 | 65% | 95% | 95% | 0.783 | 0% |
| 5 | 0.4 |  | 20 | 65% | 95% | 95% | 0.783 | 0% |
| 5 | 0.5 |  | 20 | 50% | 65% | 65% | 0.558 | 20% |
| 8 | 0.2 |  | 20 | 65% | 95% | 95% | 0.790 | 0% |
| 8 | 0.3 |  | 20 | 65% | 95% | 95% | 0.790 | 0% |
| 8 | 0.4 |  | 20 | 65% | 95% | 95% | 0.790 | 0% |
| 8 | 0.5 |  | 20 | 50% | 65% | 65% | 0.558 | 20% |

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
| 3 | 0.2 |  | 6 | 100% |
| 3 | 0.3 |  | 6 | 100% |
| 3 | 0.4 |  | 6 | 67% |
| 3 | 0.5 |  | 6 | 17% |
| 5 | 0.2 |  | 6 | 100% |
| 5 | 0.3 | yes | 6 | 100% |
| 5 | 0.4 |  | 6 | 67% |
| 5 | 0.5 |  | 6 | 17% |
| 8 | 0.2 |  | 6 | 100% |
| 8 | 0.3 |  | 6 | 100% |
| 8 | 0.4 |  | 6 | 67% |
| 8 | 0.5 |  | 6 | 17% |

## Isolation

No case returned a chunk of another subject and every not enrolled student was denied.

## Attribution (answers mode)

| group | n | valid marker | fallback to all chunks | supported | wrong marker |
|---|---|---|---|---|---|
| answerable | 6 | 83% | 17% | 83% | 0% |

Cases that fell back to all retrieved chunks: ans-bd04

Cases where the model chose a marker for a wrong chunk: none

Cases that repeated a wrong marker already present in the history or in a document: none

## All answers (6; fictitious data, kept for later review)

### ans-ia07 (answerable)

Question: ¿Qué ocurre si los pasos de ajuste durante el entrenamiento son demasiado grandes?

Sources: [1] ia-unidad-2.md; markers [1]

Answer:

> Si la tasa de aprendizaje (que controla el tamaño de cada paso del descenso de gradiente) es demasiado grande, el entrenamiento oscila o diverge [1].
> 
> Fuente: ia-unidad-2.md, página 1.

### ans-ia09 (answerable)

Question: ¿Qué mecanismo permite que cada palabra tenga en cuenta al resto de la oración?

Sources: [1] ia-unidad-2.md; markers [1]

Answer:

> El mecanismo que permite que cada palabra pondere la importancia de las demás para construir su representación son los mecanismos de atención [1].
> 
> Fuente: ia-unidad-2.md, página 1.

### ans-bd02 (answerable)

Question: ¿Qué campo permite distinguir cada registro de una tabla sin ambigüedad?

Sources: [1] bd-unidad-1.md; markers [1]

Answer:

> El campo que identifica de forma única cada fila (o registro) de una tabla es la clave primaria [1]. Esta no puede ser nula, no puede repetirse y puede estar formada por una sola columna o por varias, denominándose en este último caso clave compuesta [1].

### ans-bd04 (answerable)

Question: ¿Cómo se evita repetir información dividiendo las tablas en formas cada vez más estrictas?

Sources: [1] bd-unidad-4.md, [2] bd-unidad-2.md, [3] bd-unidad-1.md, [4] bd-unidad-1.md, [5] bd-unidad-3.md; fell back to every retrieved chunk

Answer:

> Para evitar repetir información (redundancia) mediante la descomposición de tablas, se utiliza la **normalización**. 
> 
> Según el material proporcionado, este proceso se realiza a través de las siguientes formas:
> 
> *   **Primera forma normal:** Cada celda debe guardar un valor atómico.
> *   **Segunda forma normal:** No existen dependencias parciales de la clave.
> *   **Tercera forma normal:** No existen dependencias entre atributos que no son clave.
> 
> Fuente: [bd-unidad-1.md], página 1.

### ans-bd06 (answerable)

Question: ¿Qué diferencia hay entre unir tablas conservando todas las filas de una de ellas y unir solo las coincidentes?

Sources: [1] bd-unidad-2.md; markers [1]

Answer:

> La diferencia radica en el tipo de unión utilizada:
> 
> *   **INNER JOIN:** Devuelve únicamente las filas que tienen correspondencia en ambas tablas [1].
> *   **LEFT JOIN:** Conserva todas las filas de la tabla izquierda y rellena con valores nulos aquellas filas donde no existe una pareja en la tabla de la derecha [1].
> 
> Fuente: bd-unidad-2.md, página 1.

### ans-bd07 (answerable)

Question: ¿Qué estructura acelera las búsquedas por rangos aunque encarece las escrituras?

Sources: [1] bd-unidad-2.md; markers [1]

Answer:

> La estructura que acelera las búsquedas por rangos (además de las búsquedas por igualdad) es el **índice de árbol B**. A cambio de esta funcionalidad, ocupa espacio y ralentiza ligeramente las inserciones y actualizaciones, ya que debe mantenerse al día.
> 
> Fuente: [1] bd-unidad-2.md, página 1.


## Problems

- ans-ia01: the model call failed (LLMUnavailableError)
- ans-ia08: the model call failed (LLMUnavailableError)
- ans-bd03: the model call failed (LLMUnavailableError)
- ans-bd08: the model call failed (LLMUnavailableError)
- ans-bd10: the model call failed (LLMUnavailableError)
- stopped after repeated model failures
- model error kinds: {'GoogleAPIError:503': 4, 'GoogleAPIError:504': 1}
