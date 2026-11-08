# AI Usage Notes - documents-schema-pgvector

Working notes for a later `prompts.md` proposal (that file needs the user's approval and is not touched here). Tool: Claude Code (Sonnet 5.5), OpenSpec workflow, SpecBoot skills.

**Status of this file: partial.** Task 0.4 asked for this report from the start of the change, with the literal user prompts. It was not created at that time, and it is not reconstructed here from memory: the sections below cover only groups 5 to 10, whose authorization prompts were available verbatim in the session. The planning prompts (D1-D11, spikes of groups 1-4) are recorded in the session transcript and in `design.md` (approval record); completing this file for them is a separate decision for the user. Task 0.4 stays unchecked.

## User decisions and instructions (fragments in the original Spanish; accents removed to keep the file ASCII, as in earlier changes)
- Group 5: "Si HNSW reduce recall o entrega resultados incompletos, detenerse y presentar evidencia y alternativas. No modificar el planner ni los parametros de pgvector sin aprobacion."
- Group 6: "Registrar como deuda tecnica que HNSW no se utiliza en el plan actual." and "Dejar su evaluacion de rendimiento y estrategia de indexacion para el cambio 12."
- Group 8: "No ejecutar downgrade destructivo sobre la base de desarrollo." and "Generar un respaldo logico previo y verificar que sea valido y restaurable en una base temporal aislada."
- Group 9: "No modificar otros servicios PostgreSQL ni aplicaciones que utilicen el puerto 8000."
- Group 10: "Autorizo documentar en la guia de desarrollo existente como utilizar un archivo Compose override temporal cuando los puertos 8000 o 5173 estan ocupados." and "No considerar /tmp del contenedor como almacenamiento duradero."

## AI findings and corrections (summaries)
- Group 5: the mutation check showed that the tie-break test did not detect the removal of the `id` secondary sort key; the test was strengthened. The EXPLAIN evidence showed that the hnsw index is not used because of that secondary key (recorded as TD-022).
- Group 6: a test of this change used a relative `downgrade -1`; it would break with a later migration, and was changed to an explicit revision.
- Group 8: the task text asked for a downgrade on the development database, which conflicted with the user's restriction; the cycle was run on a restored copy instead and reported as a deviation. A read-only query was first sent by mistake to another project's PostgreSQL container and then corrected.
- Group 9: ports 8000 and 5173 belonged to another project; Playwright's `reuseExistingServer` would have tested that project's frontend. The suite was run against an own server on another port.
- Group 10: the `update-docs` skill was invoked itself (`Skill` tool, project skill `update-docs`), as task 10.5 requires; it directs the agent to `docs/documentation-standards.md`, which was applied (data model, backend standards, development guide, technical debt, same change). It also exposed that group 0 and task 0.4 were never completed (see the status note above).
- Group 11: the independent review ran as a separate read-only subagent (`Explore` type, `model=opus`, clean context). Review 1: FAIL (one major: the design promised an error translation the code does not do). It also found that the statement-log leak test passed with parameters exposed, that a huge integer and a lying-length sequence escaped the controlled error, and a committed throwaway password. All of these were corrected (tests first for the code). Review 2 of the corrections by the same reviewer: PASS WITH GAPS, plus two small new findings that were also fixed. Reviewer and implementer disagreed on nothing; the open items need the user's decision (see `2026-11-08-independent-review.md`). Task 0.1 to 0.4 survey: `2026-11-08-group-0-survey.md`.
