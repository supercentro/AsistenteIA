# AI Usage Notes - subjects-and-enrollments

Working notes for the later `prompts.md` proposal (needs the user's approval). Literal fragments are marked; the rest are summaries. Tool: Claude Code (Sonnet 5.5), OpenSpec workflow (`/opsx:propose`, `/opsx:update`, `/opsx:apply`).

## User decisions and prompts (literal fragments)
- Planning approval (D1-D12), among them: "D1: devolver 404 para asignaturas de otros docentes; 403 para roles incorrectos." and "D8: mantener listados sin paginacion durante el MVP y registrar TD-016 como deuda tecnica."
- Conditions on the plan: "Mantener nombres de asignaturas sensibles a mayusculas, segun el modelo aprobado." and "Aceptar como riesgo residual del MVP que la inscripcion por email permite distinguir estudiantes registrados."
- Lessons-learned adjustments B1-B10 approved before implementation.
- Implementation authorization: "Apruebo iniciar la implementacion de `subjects-and-enrollments` mediante el workflow oficial de OpenSpec y los estandares del proyecto." with the instruction to record TDD evidence, run an independent adversarial review and stop before asking for the merge.

## AI findings and corrections (summaries)
- Group 1: the Write tool turned `\uXXXX` escapes in a test file into literal invisible characters (U+2028, bidi controls); detected by scanning the file for non-ASCII characters and rewritten with explicit code points.
- Group 2: `alembic check` on the development database first ran inside the compose backend container, whose image does not include the new migration (it reported `0002 (head)`); a `downgrade -1` run there reverted and re-applied `0002` on the development database (0 users, no data lost). The migration was then applied from the host against `127.0.0.1:5442`: `upgrade head`, `downgrade -1`, `upgrade head`, `alembic check` (no drift) and the same check on a freshly migrated test database. Lesson for the guide: run migrations for a new revision from the host (or rebuild the container) before using the container.
- Group 2: the existing test that asserted only the `users` table exists after `seed` was updated to assert that `subjects` and `enrollments` stay empty (same intent, now that the tables exist); the `0002` downgrade test now targets revision `0001` explicitly.
