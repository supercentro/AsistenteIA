# Design

Follows `docs/backend-standards.md` (section 9, aggregate teacher metrics) and `docs/base-standards.md` sections 8 and 9.4. Written after the Explore of 2026-11-23 and the owner's decisions of the same day. **Nothing is implemented and no option below is approved**: the owner approves a mitigation (section "Decisions pending") before any code. Reuses TD-069 and TD-070, the design D-M1 to D-M8 of `activity-events-and-metrics` and the existing tests with an in-memory repository (`backend/tests/unit/test_activity_service.py`).

## Decisions of the owner (2026-11-23)

| # | Decision |
|---|---|
| D-H1 | Threat model: a teacher who can manipulate enrolments and control student accounts |
| D-H2 | F8 (padding with controlled accounts) is a new finding related to TD-069, **not confirmed until reproduced**. **Confirmed end to end on 2026-11-23**: Major, open, recorded as TD-071 |
| D-H3 | The vectors F1, F8 and window differencing are demonstrated by tests first |
| D-H4 | Mitigations are proportionate, keep the right of erasure and the privacy limits, and are classified as preventive, detective or organisational |
| D-H5 | Keeping enrolments, raising N, limiting queries or logging accesses are **not assumed** to resolve a risk alone |
| D-H6 | Out of this planning: implementation, tests that change persistent data, migrations, contract changes, keeping enrolments after unenrolment, identity verification, a persistent access record |
| D-H7 | Both switches stay false; F6 and F7 stay open |

## Root cause

The group size is checked on the **cohort of the request**: `enrolled_count`, `questions` and `answers` all depend on who is enrolled now (D-M5: unenrolled students are excluded). Every figure is therefore a function of a set the teacher controls. A threshold limits one read; it does not limit the **difference of two reads** whose cohorts differ by one person.

Two kinds of exclusion exist and must not be mixed:

| Exclusion | Who triggers it | Can it be removed? |
|---|---|---|
| Unenrolment by the teacher | the teacher | yes, by design; it is the lever of V1 |
| Erasure by the student (conversations or account) | the student | **no**: it is a right. The teacher may notice the effect; it stays a residual risk |

## The vectors (reproduced first, see the spec)

| Id | Vector | Needs | Why N = 5 does not stop it |
|---|---|---|---|
| V1 (F1) | read, remove a student from the enrolments, read | the enrolment controls | each read has 5 or more students; the difference is one person |
| V2 (F8, unconfirmed) | the teacher registers accounts, enrols them by email, makes them ask, then reads | public registration (the role of the client is ignored, so accounts are students) and enrolment by email | the group is 4 controlled accounts and 1 real student; the teacher subtracts what it produced. A figure that appears also says that the real student was active |
| V3 | read two windows that differ by whole weeks | the `start` and `end` parameters, or only waiting for the default window to slide | window-wide totals (`active_students`, both rates, document figures) change by the activity of the weeks that enter and leave |
| V4 (F6) | one heavy contributor in a shown cell | nothing | not a recovery, a disclosure of dominance |

V2 was a hypothesis from reading the registration schema and the enrolment service. **It is now confirmed end to end** on a disposable database through the public API (`reports/2026-11-23-demonstration-results.md`, TD-071). What that test does not show is any control outside the application.

## Mitigations compared

Class: P = preventive, D = detective, O = organisational. "Store" means new persistent data. "Needs approval" lists what D-H6 reserves.

| # | Option | Class | Store | V1 | V2 | V3 | V4 | Cost and effects | Needs approval |
|---|---|---|---|---|---|---|---|---|---|
| A | **Stable cohort**: unenrolment sets `ended_at` and the aggregate counts everyone enrolled during the window | P | **yes** | closes | no | no | no | a migration and `data-model.md`; keeps the link student-subject after unenrolment (reverses D-M5 and the visibility rule E4); a student's own erasure still lowers the result | migration, retention, D-M5, standards |
| B | **Coarse figures**: counts in steps of 5, rates in steps of 10 %, active students in a band | P, partial | no | hides one unit most of the time; leaks at a step edge | partly | partly | partly | changes the meaning and precision of every figure and the interface copy | precision, contract meaning |
| C | **Bound the contribution** of each student (a cap per week, or count students with activity instead of questions) | P, partial | no | limits the difference to the cap | no | no | **closes** | changes what «Preguntas» means | precision, contract meaning |
| D | **A higher N or a minimum of enrolled students** | P of availability only | no | no | no | no | no | fewer classes can be read; the mechanism is unchanged | N is provisional (R-D3), legal review |
| E | **Noise** fixed per cohort | P | no (a privacy budget over several reads would need it) | hides it | hides it | hides it | yes | approximate figures, high complexity, averaging over cohorts without a budget | precision, architecture |
| F | **Fix the window**: remove or restrict `start` and `end`, or align them to terms | P, partial | no | no | no | closes the explicit parameters, not the sliding default | no | an API parameter is removed (today unused, switched off) | contract |
| G | **A limit of reads** per teacher and subject in process memory | D/deterrent | no (not shared between workers, resets at restart) | slows it | slows it | slows it | no | related to TD-070 | code, owner |
| H | **An access record** of reads and of enrolment changes | **D only** | **yes** | none | none | none | none | retention and review by a person; lets the pattern read, remove, read be seen after the fact | persistent record, retention |
| I | **Policy, notice to students and verified institutional email** | O | no or minimal | deters | the only answer to V2 | deters | no | depends on the institution and the legal review | identity verification, legal |

Reading the table: **only A addresses the cause of V1**; B and E hide it and need approval to change precision; C closes V4; F closes the explicit part of V3; nothing technical in the backend closes V2 without an identity control; D, G and H do not close a vector. None of them is accepted alone (D-H5).

## Proposed combination (first recommendation, before the evidence; refined in "Part B refined" below)

1. **A** for V1, if the owner accepts the retention after unenrolment and reverses D-M5, with the erasure behaviour of the spec preserved. If the owner does not accept A, V1 stays open with B (and C) as the partial answer.
2. **C** for V4, and **F** for the explicit window parameters (V3), both without storage.
3. **H** as the detective control for what A does not cover (V2 included), with a retention period and a reviewer defined by the owner.
4. **I** before any use with real students: the policy and the notice, the legal review, the consent version and a decision on verified email for V2.
5. **G** only if the owner wants a deterrent; it is not counted as a control.
6. **E** is not recommended for the pilot.

## Residual risks after the combination

| Risk | Why it stays |
|---|---|
| V2 without an identity control | the teacher can be the owner of the accounts; a threshold cannot tell |
| A student's own departure or erasure | a right; the teacher can notice the change |
| Window edges (V3) | the default window slides by one week every Monday |
| The step edge of B, if B is chosen | one bit can leak when a figure crosses a step |
| F7 | unmeasured cost; in-memory aggregation (TD-070) |
| Anything in TD-069 not listed here | unchanged until its test passes |

F1, F6 and F7 stay **open** until their tests pass or the owner accepts them in writing.

## Alternatives rejected for this planning

- **A higher N alone**: leaves the mechanism; it only removes small classes.
- **An access record alone**: detects, does not prevent; it also adds stored personal data.
- **Keeping enrolments without changing the aggregate**: stores data and changes nothing in the figures.
- **A teacher who cannot unenrol**: removes a basic function of the product and does not address V2 or V3.

## Part B refined (2026-11-23, after the evidence)

The tests confirmed V1, V3 and F8 and characterised V4. Nothing below is approved or implemented; the owner decides each package. Classes: P preventive, D detective, O organisational.

### A new option for V1 that keeps D-M5 and retains nothing about a student: A2, "forward-only after a roster change"

Option A (keep the enrolment as ended) cures V1 by counting people who left, which reverses D-M5 and retains personal links. A2 reaches the same goal differently.

- **Observation:** a student who is removed can have asked only **before** the removal (they cannot ask after it). So every week that starts after the last removal has a stable cohort; only the weeks before it are exposed to the read, remove, read pattern.
- **Rule:** the subject stores one non-personal marker, the moment of its last unenrolment by the teacher (a nullable timestamp on `subjects`). The service computes the weekly cells and every window-wide figure **only over whole weeks that start after the marker**; earlier weeks are withheld. The response already carries `window.start`, `window.end` and `window.weeks`, so the effective window is reported by fields that exist; the meaning "the window may be narrower than requested" is a contract note.
- **Why it closes V1:** after removing a student the teacher never sees again the weeks that held that student's activity, with or without the student. Re-enrolling does not bring them back, because those weeks stay withheld. The two reads compare different weeks.
- **Effect on erasure and D-M5:** D-M5 is unchanged (the unenrolled are still excluded). The marker names no person and is not a copy of the enrolment, so a student's own erasure leaves nothing behind. A student's own deletion still lowers later results (a right, and a residual risk).
- **Costs:** a migration (one column, with its `downgrade`), a rule in the service, and **lost history after any unenrolment** (the data stays; it is not shown). A removal by mistake hides the term so far; the dashboard fills again week by week. A removal caused by the deletion of the student's own account does not set the marker (a right, residual).
- **Needs approval:** the migration, the contract note about the effective window, the loss of history, and the sentence of `backend-standards.md` section 9.
- **Specified in detail** in "P2 / A2 specification in detail" below.

### V3 without storage: remove the window-wide figures, or compute them on fixed blocks (F2)

The leak of V3 comes only from the window-wide figures (`active_students`, both rates, document figures); the weekly cells are already stable. Two ways, both without storage:

- **F2a** drop the window-wide figures from the response and show only weekly figures (a contract change; the dashboard shows them today).
- **F2b** compute them over calendar-aligned blocks that never overlap (a fixed 4 or 12 week block) and withhold the incomplete one (a meaning change: they refresh once per block).

F (restricting `start` and `end`) alone does not close V3 because the default window slides every Monday.

### F8: identity and institutional membership, compared without assuming that a verified email solves it

The threat is a teacher who **controls** accounts that look like students. To stop it, the teacher must not be able to make an account that counts as a student of the institution.

| Mechanism | Class | What it proves | Why it can still fail | Cost and effect on the right of erasure | Needs approval |
|---|---|---|---|---|---|
| I1 Email verification (a link) | P, weak | the person controls the address | the teacher can create or control addresses (free mail, aliases, plus-addressing); it stops only careless fakes | no new retained data; needs a mail service | infrastructure, secrets |
| I2 Allow list of institutional domains plus verification | P, partial | the address belongs to the institution | a teacher with mailbox or alias rights in the same domain can create student-looking addresses; it excludes students without an institutional address | one setting; no retained data | identity policy, setting |
| I3 Roster supplied by the institution (an administrator or the registrar enrols; the teacher cannot) | P, strong | membership comes from an authority outside the teacher, which also removes the teacher's enrolment lever (V1) | needs an administrator role or an integration (Moodle or LTI is out of the MVP); the administrator is a new trusted party | stores the roster; erasure and the source of truth need design | architecture, roles, scope of the MVP |
| I4 The student confirms the enrolment | P, no for F8 | that the person behind the account accepts | a controlled account confirms itself, so it does not stop F8; it does inform real students | a consent record to erase with the account | consent flow, contract |
| I5 Maturity rule: count only accounts older than a period and enrolled before a date | P, partial | raises the cost and delay of padding | accounts can be created in advance; a new term has only new accounts, so figures disappear when they are most useful | uses existing columns; no new data | meaning of the figures |
| I6 Composition guard: withhold when too many of the contributing accounts were created or enrolled recently, or share a pattern | P/D, heuristic | detects a burst of new accounts | false positives at the start of a term; patterns are learnable; a threshold to tune | reads existing columns on demand; no new data | meaning of the figures, owner |
| I7 Policy, acceptable-use terms for teachers, and audit by a reviewer | O/D | a commitment and a way to sanction | does not prevent; relies on someone reading the record (H) | the record adds personal data of teachers and links to students | policy, retention, legal |
| I8 Change who reads: institution-level or reviewer-level figures instead of the subject's teacher | P, strong | the lever is not in the hands of the subject's teacher | a different product and role model | new roles | scope, architecture |

**Reading:** no mechanism of the application alone proves that an account is a real student. I1 and I2 raise the cost; I3 and I8 move the trust to someone who is not the teacher; I5 and I6 are heuristics with an availability cost; I7 is organisational. The honest option is a package: raise the cost technically (I2 plus I6), add a detective control (H) and a written policy (I7), and **accept F8 as a residual risk under a written decision** until I3 or I8 is possible. Verifying an email alone is not accepted as a mitigation.

### Effect of each option on the right of erasure and on the existing decisions

| Option | Retains data after unenrolment | New personal data | Touches D-M5 | Effect on a student's own erasure |
|---|---|---|---|---|
| A | **yes** (the enrolment, as ended) | yes | **reverses it** | the retained row must be removed with the account (cascade) |
| **A2** | no | no (a timestamp of the subject) | no | none |
| B, C | no | no | no | none; C changes what a figure counts |
| F, F2a, F2b | no | no | no | none |
| G | no | no | no | none |
| H | no | yes (reads and enrolment changes; teacher data, links to students) | no | the links must cascade; retention and review are decisions |
| I1, I2 | no | no, or a verification flag | no | a flag erased with the account |
| I3 | the roster | yes | indirectly | roster and source of truth need a rule |
| I5, I6 | no | no | no | none |

### Decision packages (what the owner can approve separately)

| Package | Contents | Closes | Leaves open | Approvals |
|---|---|---|---|---|
| **P1 stateless** | C (bound the contribution), F2a or F2b (window-wide figures) and F (parameters) | V4, V3 | V1, F8 | meaning of figures, contract |
| **P2 roster guard** | A2 (marker and forward-only figures) | V1 | F8, V3 until P1, the student's own departure | migration, contract note, loss of history |
| **P3 identity** | I2 plus I6, with I3 or I8 as the strong later option | raises the cost of F8; **I3 or I8 closes it** | F8 stays a residual risk until I3 or I8 | identity policy, setting, legal, scope |
| **P4 detective and organisational** | H, I7 | nothing by itself | all of them stay open; it supports P1 to P3 | retention, reviewer, policy, legal |
| P5 optional | G | slows repetition | all | owner |

### Technical proposal to decide (a recommendation, not a decision)

1. **Decide P1 and P2 first**: both are small and hold no personal data; together they close V4, V3 and V1 and keep D-M5 and the right of erasure. The price is a changed meaning of some figures (P1) and the loss of history after a removal (P2).
2. **For F8 approve a written decision**, not a feature: accept it as a residual risk until I3 or I8 is possible, add I2 plus I6 to raise the cost if the institution has a mail domain, and keep the switches off for real students. A verified email alone is not enough.
3. **P4 after P1 to P3**: the detective record with a retention period and a named reviewer. It supports the policy; it is not a control of the figures.
4. **Not recommended**: A (it reverses D-M5 and retains links when A2 reaches the same result), E (noise), a higher N (it only removes small classes).
5. **Residual after P1, P2, P3 and P4:** F8 (until I3 or I8), a student's own departure or erasure, and the window edges.

## P2 / A2 specification in detail (2026-11-23)

Prioritised by the owner for F1. **Planning only: no code, migration, permission or contract is changed by this section.** D-M5 is kept: a student who is removed contributes to no later figure. F1 is **not** closed and stays open until the demonstration of this section passes (spec, "F1 stays open until demonstrated").

### The rule in one paragraph

The subject keeps one non-personal marker, `last_unenrolment_at`: the database clock at the last unenrolment the teacher made. Every figure of the response is computed **only over whole weeks that start strictly after the marker**. A student can have asked only before being removed, so no figure ever includes both the weeks that held that student's activity and a read that excludes them.

### The marker (persistence)

| Item | Definition |
|---|---|
| Column | `subjects.last_unenrolment_at TIMESTAMPTZ NULL`; null means no unenrolment has happened. No reference to a student |
| Written by | the single route that removes an enrolment (`DELETE /subjects/{id}/enrollments/{student_id}`), inside **the same transaction** and **before** the enrolment row is deleted (order: advisory lock, subject row, enrolment row, as the deletion of a subject follows); a removal that deletes nothing raises 404 and rolls the marker back |
| Value | `GREATEST(coalesce(current, '-infinity'), clock_timestamp())` of the database: **monotonic**, one clock for the marker and for `messages.created_at` |
| Unconditional | set whether or not the student had asked anything, so that hiding or not hiding the history never tells whether the student was active |
| Not written by | a read, an enrolment, a re-enrolment, a 404 (nothing deleted), the deletion of an account or of conversations by the student (their right), the deletion of the subject |
| Existing subjects | **the state of each environment was checked (2026-11-23)**: the switch is not set in any environment file, the Compose file or CI, but the development database holds 74 messages in 4 subjects, so earlier reading cannot be ruled out. The migration therefore sets the marker to the migration time **only for subjects that already hold conversations** (past removals left no trace, so the history before it stays withheld) and leaves it null for the others; no protection is omitted where history exists |
| Migration | one revision after the current head `0007`, with a working `downgrade` that drops the column; `alembic check` clean |

### The effective window (formal)

Let the requested window be the whole weeks the service already computes (Monday to Sunday UTC, at most 12). Let `c(M)` be the **first Monday 00:00 UTC strictly after** the marker `M` (a marker exactly on a Monday still hides that Monday's week, which makes the proof independent of equal timestamps). The effective weeks are the requested weeks whose start is at least `c(M)`; with a null marker nothing changes.

- `window.start` is the first effective week, `window.end` and the default end are unchanged, `window.weeks` is the number of effective weeks. **`weeks` may be below 12 and may be 0**: with 0 weeks `questions` is empty, every window-wide figure is null, `enrolled_students` is still shown and `suppressed` is true.
- A marker older than the window has no effect. A marker inside the current week gives 0 weeks until the next Monday.
- Every query of the repository (questions, answers, documents) takes the effective bounds; the marker is read from the subject that the service already loads, so there is no extra query.

### Operations analysed

| Operation | Effect on the marker | Effect on the figures | Why it is safe or what remains |
|---|---|---|---|
| Read, repeated reads | none | the same answer every time | the answer depends only on data and marker, never on earlier reads |
| Remove student S | set to now (monotonic) | weeks before `c(M)` withheld | S's questions all precede the marker (see concurrency) |
| Remove an inactive student | set to now | the same as for an active one | no presence bit |
| Remove again, later | moves forward, never back | more weeks withheld | each removal hides what the previous read saw |
| Re-enrol S | none | S's new questions count from then on | their earlier weeks stay withheld, so nothing reappears |
| Enrol a new student | none | the new student's activity appears in later weeks only | not a removal; see "addition" in the residual risks |
| Roll back the removal | unchanged with the delete | unchanged | one transaction |
| Remove a student who is not enrolled (404) | unchanged (rolled back with the 404) | unchanged | the update ran first and the transaction rolled back |
| Student deletes conversations or account | unchanged | later results exclude that data | their right; the teacher may notice the change (residual) |
| Two removals at once | one monotonic value | as above | the subject row serialises the two updates |
| Chat turn at the same time as a removal | see below | see below | ordered by the existing lock |

### Security property of V1: independence from the cut-off past, not equality

Equality of the answers before and after cannot be required: A2 hides weeks. The first formulation (worlds that differ only in the removed student's messages) **was found insufficient** on the reference model: without any mitigation it holds in every case without re-enrolment (0 of 35 worlds differ), because a removed student is excluded anyway. The attack is not that a later read depends on the student; it is that a later read **covers the same weeks as an earlier one**, so subtracting isolates the student. The property to prove is:

> Take two worlds that differ only in messages created **before the marker in force**, written by **any** student, the removed one included. Apply the same removal and the same later operations. Every response after the removal is **identical in both worlds**: the figures, the window, `enrolled_students` and `suppressed`.

On the model: without a marker 60 of 60 worlds differ; with A2, with A2 and A2b, 0 of 60. The read taken before the removal legitimately includes the student, like any aggregate of 5 or more students; a response after the removal depends on nothing the earlier read covered, so it cannot be subtracted from it.

A2b counts a week as ended **one hour after its Sunday**, so that a chat transaction that began before midnight (its `created_at` is the start of the transaction) has committed before the week is shown. It adds a second property, temporal independence: a response at any instant depends only on messages created before the start of the current week, apart from the enrolled count (model: 60 of 60 worlds differ with A2 alone, 0 of 60 with A2b).

Proof obligations, each with a test: (P-a) every figure after the removal uses only weeks that start after the marker; (P-b) every message of S precedes the marker; (P-c) the marker never decreases; (P-d) the marker does not depend on S's activity; (P-e) the marker and the deletion commit or roll back together; (P-f) the only way to delete an enrolment is the route that sets the marker.

### Concurrency and transactions

- Messages take `created_at = now()`, the start of their transaction. A chat turn and an unenrolment already take the same advisory lock first, per student and subject (M2, `lock_student_subject`). If the turn takes it first, the removal waits, so the marker is later than the turn's commit and its `created_at`. If the removal takes it first, the turn finds the student not enrolled and is refused. So no question of S has `created_at` at or after the marker.
- The update of the marker takes the subject row **after** the advisory lock and **before** the enrolment row, which keeps the rule "one advisory lock, taken first" and the order of the deletion of a subject. The first draft wrote it after the delete, which could deadlock with that deletion; see the second validation round.
- The activity read runs in one snapshot (second validation round); the first draft did not say it.
- Assumption: the database clock does not go backwards; `GREATEST` keeps the marker monotonic even if it does.
- The route already commits through `commit_or_rollback` before the 204 is built.

### Effects on windows, availability and the dashboard

| Situation | What the teacher sees |
|---|---|
| No removal yet | as today |
| A removal in the current week | 0 weeks: no table, the window-wide cards read «Datos insuficientes», the enrolled count stays |
| A removal some weeks ago | only the weeks after it; `weeks` below 12; the cards use those weeks, with 5 or more active students needed |
| 12 to 13 weeks after the last removal | the full window again |

The loss is the visible history after each removal: with A2 and A2b **no figure for 7 to 14 days (mean about 11)**, then fewer than 12 weeks until 12 to 13 weeks have passed (reference model; A2 alone gives 0.2 to 7 days); the data stays stored. Each removal resets the effect, including one that corrects a mistaken enrolment, and the marker cannot be made conditional without leaking a bit. The dashboard sends no parameters, so `weeks` below 12 means the history was limited. Two states are needed, with copy for the owner to approve:

| State | Proposed Spanish copy |
|---|---|
| Limited (`weeks` below 12, above 0) | «Por un cambio en las inscripciones, solo se muestran las semanas posteriores a ese cambio.» |
| No weeks (`weeks` is 0) | «Por un cambio en las inscripciones, todavía no hay semanas completas para mostrar.» |

Coupling to note: reading "limited" as `weeks` below 12 depends on the default window having 12 weeks; a later change of the default (package P1) must revisit it. A new response field would remove the coupling but is a larger contract change; it is not proposed.

### Minimal changes (when implemented, each with approval)

| Where | Change |
|---|---|
| Persistence | revision `0008` (one column, backfill, `downgrade`); the `Subject` model |
| Write path | `EnrollmentRepository.delete_for_teacher_subject` sets the marker in the same transaction **before** deleting the enrolment; 404 rolls it back |
| Read path | the activity read runs in one `REPEATABLE READ` snapshot (read-only), set before its first statement |
| Service and repository | `ActivityService` computes the effective weeks from the subject it already loads; the repository queries take the effective bounds |
| Permissions | `backend/app/db_privileges.py`: `UPDATE (last_unenrolment_at)` on `subjects` for the application role, next to `description`; the inventory and the matrix tests; how an existing environment receives the grant (the admin step) is checked when implemented |
| Contract | `docs/api-spec.yml`: `weeks` minimum from 1 to 0 and the descriptions of `start`, `end`, `weeks` and of the endpoint (the window is the effective one); **no new field**; the generated types are checked, `weeks` stays `number` |
| Frontend | the two states and their strings; the judgement-word scan covers them |
| Documents | `docs/data-model.md` (the column and the privilege), one bullet of `docs/backend-standards.md` section 9, TD-069 after the demonstration, the roadmap line |

### Validation (existing tests reused, extra checks)

| Check | How |
|---|---|
| Strengthen the V1 property | replace the xfail of `test_v1_property_holds` by the two-world non-interference test with fixed seeds, over many random classes, removals and later operations (the project has no property-test library and none is added); it must fail without A2 and pass with it |
| Edge cases of the rule | a removal mid-week, exactly on a Monday 00:00, in the first week of the window, 12 or more weeks ago, two removals in a row, a re-enrolment, a new student, an inactive student (the same hiding as an active one), repeated reads |
| Real SQL and routes | the existing V1 end-to-end test of `test_activity_inference_f8.py` flips: the read after the removal shows no week with S; plus rollback (the removal and the marker both revert), a failing marker update (the removal reverts), a 404 (no marker) |
| Concurrency | the pattern of `test_chat_enrollment_lock.py`: a turn and a removal in both orders; every message of S has `created_at` below the marker; two removals at once |
| Erasure | the marker holds no student reference (schema test); deleting an account or conversations leaves it unchanged and lowers later results as today |
| Single write path | a static test that no code deletes from `enrollments` outside the repository method (the cascade of a deleted subject or account is not a route) |
| Migration | upgrade, downgrade, `alembic check`, the backfill on a database with existing subjects |
| Permissions | the role-bound suites (453 tests in CI): the application role may update that column and no other new one; the exposure test that no subject response carries the marker |
| Contract | `test_api_contract.py` and the property-key test of the activity response; `npm run check:api-types` |
| Existing tests to review | `test_activity_service.py` (the fake subject needs the attribute), `test_activity_endpoint.py`, `test_enrollments_*`, the privilege matrix, the dashboard tests and the mocked Playwright spec |
| F8 stays | the end-to-end F8 tests keep passing as confirmation of the vulnerability: A2 does not touch it |
| Mutation checks | remove the filter (V1 property fails), make the marker conditional on activity (the presence test fails), let it decrease (the sequence test fails), move the write after the commit (the rollback test fails), delete an enrolment by another path (the static test fails) |
| Final | the §9 gates, the manual `curl` run on the test stack, the Playwright MCP run of the two states, an independent adversarial review with a privacy focus |

### Residual risks of A2

| Risk | Why it remains |
|---|---|
| The read before the removal | an ordinary aggregate of 5 or more students; accepted baseline |
| A student's own erasure | their right; the teacher can notice the change |
| Windows that overlap (V3) | not touched; package P1 |
| F8 (TD-071) | not touched; needs an identity control |
| Heavy contributor (V4, F6) and F7 | not touched |
| **Addition and the current week (candidate V5)** | two reads in the same week differ by what was asked in between, and an added student's questions show up in the current week; time-resolved activity can be attributed when the teacher knows who is asking (a class in the room). It is trivial arithmetic but **not yet demonstrated**: it needs the owner's authorisation as a test. A rule that only complete weeks are shown (A2b) would close it; it changes the default window and is a separate decision |
| The clock | the marker assumes a database clock that does not go backwards |
| Loss of history | by design: 7 to 14 days without figures and 12 to 13 weeks until the full window, after every removal |

### Decisions pending (split from D-P9)

| # | Decision | Recommendation |
|---|---|---|
| D-P9a | The migration; backfill with the migration time only for subjects that hold conversations, null for the others (decided by the state of each environment) | **approved 2026-11-23 with that rule** |
| D-P9b | The `UPDATE (last_unenrolment_at)` grant to the application role, and how existing environments get it | approve; check the admin flow first |
| D-P9c | The contract: `weeks` minimum 0 and the descriptions of the effective window; no new field | approve |
| D-P9d | Accept the loss of visible history after each removal, unconditionally | approve; the cost is the price of D-M5 and erasure |
| D-P9e | The two Spanish texts of the dashboard | **approved by the owner on 2026-11-23** |
| D-P9f | The marker is set only by the teacher's unenrolment, not by an enrolment, an account deletion or the student's own deletions | approve |
| D-P11 | A2b: show complete weeks only (closes the candidate V5 and the addition case) | decide separately, after a demonstration test of V5 |
| D-P12 | F1 is closed only when the non-interference property passes unchanged, the mutation checks and the adversarial review are done | **approved by the owner on 2026-11-23** |

### Recommendation

**GO to authorise the implementation of P2/A2** with D-P9a to D-P9g and D-P12 (see the second validation round, which corrects two points of this section). It closes the unenrolment form of F1 without keeping any enrolment and without touching D-M5, at the price of visible history after every removal. It does **not** close F8, V3, F6 or F7, and it does not allow the capability to be enabled for real students.

## Second validation round (2026-11-23): grants, `weeks=0`, concurrency, V5 and A2b

Planning only. Nothing is implemented, no migration is run and no permission is changed. Four validations were requested before P2/A2 is implemented; two of them corrected the draft of A2 above (the order of the writes and the snapshot of the read).

### 1. How the new column permission reaches existing environments (not applied)

Privileges are **not** part of the Alembic revisions. The matrix of `backend/app/db_privileges.py` is the single source, and `python -m app.cli db-migrate` runs Alembic as the migrator and then `db-grants`, which in **one transaction** revokes everything from `PUBLIC` and from each runtime role on every table and grants exactly the matrix. Consequences for A2:

| Question | Answer |
|---|---|
| Who forces the decision | the snapshot `KNOWN_COLUMNS` and the inventory tests fail while the new column has no decision, so the change cannot merge without a matrix entry |
| What is granted | the application role `UPDATE (description, last_unenrolment_at)` on `subjects`; because the set is not every column it is rendered as a column-level grant; `SELECT` stays table-level, so every role that can read `subjects` can already read the new column (harmless: it names no person); the worker and the CLI role gain nothing |
| How an existing environment gets it | by running `python -m app.cli db-migrate` (Alembic upgrade, then the grants) with `backend/.env.migrate`, then `python -m app.cli db-verify` (read-only, exit 1 on any difference). `db-grants` alone applies only the grants. Alembic alone is refused by `alembic/env.py` |
| Order | the migration and the grants must finish **before** the new API code runs; in Compose the `migrate` one-shot already runs before `backend` and `worker` |
| If the order is wrong | the new route's `UPDATE` is refused by PostgreSQL, the removal fails with 500 and **rolls back as one unit**: no student is removed without the marker (fails closed) |
| Rollback | `db-migrate --downgrade 0007` is one of the documented dangerous operations (preconditions of the development guide); it drops the column together with its grants |
| Rehearsal | the CI job `privileges` builds a cluster as production does (bootstrap, migrate, `db-verify` without findings, `alembic check`), so the flow is exercised on every change; the development database of the machine is **not** touched until the owner authorises the run |
| Cost | the matrix, `docs/data-model.md` (the privileges table), the inventory and the 453 role-bound tests; no new role and no new secret |

### 2. `weeks = 0` and the existing contract

| Layer | Finding |
|---|---|
| Server | the Pydantic model declares `weeks: int` with no bound, so 0 is produced without an error; the 12-week maximum and the whole-week rules stay in the service |
| Specification | `docs/api-spec.yml` says `minimum: 1`. The contract test compares the paths, the schemas and their properties; it already passes although the Pydantic model declares no minimum, so a minimum is not compared. The specification must still be corrected to `minimum: 0` to tell the truth (decision D-P9c) |
| Generated types | `weeks: number`: no change of shape; `npm run check:api-types` is run after the edit |
| Other clients | none exist; both switches are off |
| Invariant for 0 weeks | `window.start` is the day after `window.end`, `questions` is empty, every window-wide figure is null, `enrolled_students` is shown, `suppressed` is true. Normalising `start` avoids a start far after the end |
| Dashboard | **it is not compatible as it is**: the line «Semanas del … al …» would read with an end before the start, and `WeeklyQuestions` would draw an empty table. With `weeks` 0 the page hides the window line and the table, shows the enrolled count, «Datos insuficientes» in the window-wide cards and the approved note. Approved copy (2026-11-23): limited «Por un cambio en las inscripciones, solo se muestran las semanas posteriores a ese cambio.»; no weeks «Por un cambio en las inscripciones, todavía no hay semanas completas para mostrar.» |

### 3. Concurrency of the removal, the marker and the operations that lock subjects

Lock sites found in the code: the per-student, per-subject advisory lock (`lock_student_subject`, taken by the chat turn and by the removal, always first); the document upload (`SELECT ... FROM subjects ... FOR UPDATE`, then the global admission advisory lock, a different key space); the deletion of a subject (the cascade deletes its enrolments).

**Defect 1 of the draft: a deadlock.** The draft wrote the marker after deleting the enrolment. The removal would hold the enrolment row and wait for the subject row, while the deletion of a subject holds the subject row and waits for the enrolment row in its cascade: opposite orders. **Fix:** the removal updates the marker **first** (advisory lock, subject row, then enrolment row), the same order as the deletion of a subject. A removal that deletes nothing raises 404 and the transaction rolls back, which also undoes the marker.

| Pair | Result with the corrected order |
|---|---|
| Removal and chat turn of the same student | ordered by the advisory lock (M2); the marker is later than the turn's `created_at`, or the turn is refused |
| Removal and chat turn of another student | the update of a non-key column takes `FOR NO KEY UPDATE`, which does not conflict with the `FOR KEY SHARE` that the turn's foreign keys take on the subject row |
| Two removals (same or different student) | the second waits for the subject row and then writes a later value; `GREATEST` keeps it monotonic |
| Removal and document upload | the upload's `FOR UPDATE` waits for the removal, or the removal waits for the upload; the upload waits for the admission lock, which no removal holds; no cycle |
| Removal and deletion of the subject | the same order (subject row first): the second waits for the first; no deadlock |
| Removal and a read of the activity | see the next defect |

**Defect 2 of the draft: a mixed read.** The activity read issues several statements, and under the default isolation level each statement sees the data committed at its own start. A read that loads the subject (old marker) and then queries the questions after a removal committed would combine the **old marker with the new cohort**: weeks before the marker shown without the removed student, which is exactly V1. A teacher could try to hit that window by sending reads while the removal is in flight, and by repeating the cycle (re-enrol, remove). **Fix:** the whole read runs in **one snapshot**: a single read-only transaction at `REPEATABLE READ` (set before the first statement), or one statement. A read that overlaps a removal then returns the full pre-removal answer (an ordinary aggregate) or the post-removal answer, never a mixture. A read-only repeatable-read transaction cannot fail with a serialisation error. This also makes the existing read internally consistent. It needs a test with a deterministic race (a separate session commits the removal between two statements of the read).

Remaining assumptions: the database clock does not go backwards (`GREATEST` keeps the marker monotonic anyway); no path other than the route deletes an enrolment (a static test).

### 4. V5 and A2b

**What V5 is.** The current week is shown while it is still open, so two reads in the same week differ by what was asked in between, and an enrolled student's first questions appear at once. A throwaway in-memory check (not part of the repository) gave: the cell of the week 10 -> 11 after one question (the difference is the question); and after a newcomer asked once, the cell 11 -> 12, `active_students` **5 -> 6** and `enrolled_students` unchanged. The second case is the **addition form of F1**: no removal, yet the teacher sees that the student who was just enrolled became active, and when. A2 does not touch it. It is arithmetic, not yet a test of the repository: the in-memory demonstration (task 1.7) and the owner's decision D-P11 are pending.

**What A2b is.** Show whole weeks only, and only weeks that have ended: the last effective week is the one that ended on the last Sunday. A read inside a week returns the same answer as any other read inside that week; nothing new is visible until the Monday 00:00 UTC that closes the week.

Formal rule combined with A2: let `L` be the Monday of the last week that has ended and `c(M)` the first Monday strictly after the marker. The effective weeks are the requested weeks `w` with `c(M) <= w <= L`. The default `end` is the last Sunday; an `end` inside the open week is clamped to it.

| Question | Answer |
|---|---|
| Does A2b change the marker, the column, the migration or the grants | **No.** It is one more bound in the service (and the default window), so **V5 does not require a design change before the migration is approved** |
| Does it change the contract | the same one change already planned: `weeks` may be 0 and `end` may be before today's week; no new field. If both are decided together the contract and the dashboard are edited once |
| Effect on the window | a new subject has 0 weeks during its first week; the table has 12 rows of ended weeks; the dashboard's note «Semanas del … al …» ends on the last Sunday |
| Effect on availability | the freshest information is up to 7 days old. After a removal on a Wednesday: A2 alone shows 0 weeks until the next Monday and then the open week; A2b shows 0 weeks until the Monday after that (the first visible week is the next one, and it must end), which is 7 to 14 days of blank figures (measured on the reference model, mean 10.6) |
| Effect on the inference risks | closes V5 (same-week increments) and the addition form of F1; leaves V1's removal form to A2, V3 to P1, F8 and F6 untouched; compatible with the P1 blocks, which are whole weeks |
| Effect on non-interference | none: the property of V1 holds with or without A2b; A2b adds its own property (below) |
| Disclosure that remains | at Monday 00:00 a whole week appears at once; a teacher who knows who was active in a small week learns from it, as with any aggregate of 5 or more students |

Property of A2b (temporal non-interference): the response at any instant depends only on messages created before the start of the current week. Test: two states that differ only in messages or enrolments of the current week give identical responses (except `enrolled_students`, which the teacher already knows); the same at 23:59:59 on Sunday and at 00:00:00 on Monday, where the answer changes by exactly one week. Mutation checks: let the open week through, or clamp to the wrong day.

Proposed notice for the dashboard if A2b is chosen (to approve): «Se muestran solo semanas completas.» The judgement-word scan covers it.

**Recommendation on V5.** Demonstrate it with the in-memory test (D-P11) and decide A2b separately. **Do not delay the migration** of P2: A2b is independent of the column. Specify A2b before the dashboard states are implemented, so that the contract and the copy are edited once.

### Decisions after this round

| # | Decision | State |
|---|---|---|
| D-P9a | Migration with a data-driven backfill (subjects that hold conversations) | **approved 2026-11-23** |
| D-P9b | The `UPDATE (last_unenrolment_at)` grant; applied with `db-migrate` then `db-verify`, never by hand | pending |
| D-P9c | `weeks` minimum 0, `start` the day after `end` when there are no weeks, the descriptions of the effective window; no new field | pending |
| D-P9d | Accept the loss of visible history after each removal, unconditionally | pending |
| D-P9e | The two Spanish texts of the dashboard | **approved 2026-11-23** |
| D-P9f | The marker is set only by the teacher's unenrolment | pending |
| D-P9g (new) | The marker is written **before** the enrolment is deleted (order subject then enrolment), and the activity read runs in one `REPEATABLE READ` snapshot | pending; it corrects two defects of the first draft |
| D-P11 | Demonstrate V5 with an in-memory test, then decide A2b | demonstration authorised to be **planned**; the test and A2b pending |
| D-P12 | F1 (unenrolment form) closes only when the non-interference tests pass unchanged, the mutation checks are recorded and the review has no open Blocker or Major | **approved 2026-11-23** |

### GO/NO-GO for authorising P2/A2

**GO** to authorise the implementation of P2/A2 with D-P9a to D-P9g, after the owner reads the two corrections of this round. It closes the unenrolment form of F1 only; the addition form (V5) needs A2b, F8 needs an identity control, V3 and F6 need P1, and F7 stays open. F1 stays open until its demonstration passes. Enabling the capability for real students stays **NO-GO**.

## P1 specification: fixed blocks for the summary and a dominance rule (2026-11-24)

> **Superseded on 2026-11-26** (see "Original scope restored"). Kept as the record of what was analysed.

Planning only: nothing is implemented. A2 and A2b are merged in `main` (PR #36, `55bc6da`) and are the base. P1 addresses **V3** (the comparison of windows) and **F6** (one student concentrating a figure). **V3, F6, V6a, V6b (found on 2026-11-24) and V7 (found on 2026-11-25, present in `main`) stay open until the demonstrations below pass**; F8 (TD-071) and F7 (TD-070) are not closed by P1.

**Decided by the owner (third round, 2026-11-24):** rule F (summaries only over the publishable weeks); fixed blocks of two weeks anchored to Monday 2026-01-05; dominance threshold 50 %, provisional and subject to tests; published figures keep their real values (no rounding, capping or noise that silently changes their meaning); no selection of historical blocks through `end`; the lower availability of the summaries is accepted provisionally; both switches stay off. On 2026-11-25 the owner also approved the Spanish copy (D-Q13), the two additive fields (D-Q14) and the acceptance criteria (D-Q15). The validation of that day found rule G insufficient: D-Q17 to D-Q19 are pending (below).

### Decisions of the owner (2026-11-24)

| # | Decision |
|---|---|
| D-Q1 | Fixed, complete, non-overlapping time blocks for the summary figures, plus a control of individual dominance |
| D-Q2 | Blocks of **two weeks**, provisionally, anchored to a fixed Monday common to every subject |
| D-Q3 | An additive field `summary_window` tells the summary figures apart from the weekly series |
| D-Q4 | A dominance threshold of **50 %**, provisional and not validated |
| D-Q5 | A published figure is the real figure; its meaning is never altered silently |
| D-Q6 | The privacy, authorisation and erasure rules stay as they are |
| D-Q7 | The documentary closure of F1 (the unenrolment and open-week forms, mitigated by A2 and A2b) and task 5.7 go into the next authorised pull request, with the evidence that exists |

### Second round of decisions of the owner (2026-11-24) and what this review corrected

The owner keeps fixed time blocks with a dominance control as the main alternative, `summary_window` as a proposal for an additive contract, and the two weeks and the 50 % threshold as provisional. **The owner does not approve yet that `end` selects historical blocks** (D-Q8). The review asked for was: can the summary figures, the weekly cells, the rates and the documents be **combined** to rebuild a withheld value; what do the transitions between a figure and `null` reveal; two against four weeks for small classes; do historical blocks add vectors; which proportional mitigations; and are the acceptance criteria of V3 and F6 able to detect these leaks.

**Result in one line:** the first version of this specification (cells and rates independent of each other) **would have left a composition leak open**, which also exists today in `main`. It is closed by a change of the rule, not of the contract's shape: the summary is computed only over the weeks of the block whose weekly cell is published. A statement of the first version was wrong and is withdrawn: *"the numerator of a rate needs a count of answers that the response does not give"*. A teacher does not need the numerator: the **denominator** is enough, and it is the sum of the cells plus the withheld ones.

### Why V3 happens and what closes it

The summary figures (`active_students`, both rates, `cited_appearances`) are computed over the whole window, and the window slides every Monday. Two reads one week apart differ by the week that leaves and the week that enters, so subtracting them isolates that week, **including a week whose own cell is withheld for having fewer than 5 students**. A teacher can also make overlapping windows without parameters, **by the timing of removals**: each removal moves the start of the effective window, so the same weeks could be shown in two versions. The only ways to avoid a difference are windows that never overlap, noise, or not showing the figure. P1 takes the first.

### Composition of the published figures (complementary disclosure)

The question is not whether one figure is safe but whether **the set of published figures determines a withheld one**. Method: an executable adversary that reads one response and solves for the withheld number with nothing but published figures (no controlled accounts: that is F8). The evidence is a self-contained model of the arithmetic of `ActivityService` (minimum group 5, rates rounded to three digits, one document per answer, 10 % of the answers without material, 15 % retrieved but not cited) run outside the repository. **Limit of the evidence:** in this session the interpreter of the project is blocked by an application-control policy of the host, so the real service could not be driven; the model ports the arithmetic read in `activity_service.py`, and task 3.1a repeats the demonstrations on the real service before any code is changed.

| Id | Combination | What it recovers | Evidence | Severity | Exists today |
|---|---|---|---|---|---|
| **V6a** | weekly cells + the two rates | the **total of the withheld weeks** (the denominator of the rates is the number of answers of the period; the published cells give all but the withheld weeks; two rates rounded to three digits fix the denominator within a few candidates) | worked example: 12 weeks, week 5 withheld (28 questions), published cells add up to 132, rates 0.138 and 0.331: the withheld cell can only be 13, 28, 49 or 107 (within 120). With the prior that a week is at most twice the biggest published one, the total is **unique in 29 % to 70 %** of the reads where it applies (3 digits) and has at most 3 candidates in 79 % to 98 %; rounding to two digits lowers it (unique 2 % to 13 %, at most 3 candidates 8 % to 63 %) but does not close it | **Major** for F6: it rebuilds what the dominance rule hides (a heavy student's week) and what the minimum group hides | yes (12-week window, rates over the window) |
| **V6b** | document figures + `no_cited_source_rate` | a **withheld document figure** (fewer than 5 citing students): the rate gives the number of cited answers; with one document, or answers that cite one document each, that is the figure | worked example: 4 students cite `a.pdf` (24 answers), 2 others get uncited answers (12); the figure of `a.pdf` is withheld, the rate 0.333 gives 24 cited answers of 36 | **Moderate**: it exposes the volume of a group of fewer than 5 students; no identity. With several documents the figure is only bounded (between the cited answers minus the published appearances, and the cited answers) | yes |
| V6c | `active_students` + the cells | **false as first written ("nothing exact"):** a published week has at least 5 students, so `active_students` minus 5 bounds how many asked only in one of the two weeks (V11, found by the second review) | reproduced | open (D-Q24) | n/a |
| V6d | the dominance suppression itself (rates null while `active_students` is shown) | one bit: some student has more than half of the answers | reasoned | **Minor**: no identity, no count; with F8 it adds nothing | new in P1 |

**What the rule as first written would have done:** keep V6a in every block, and make it worse with longer blocks (more reads where a cell is withheld while the rates are published: 28 % of the reads of a 2-week block for a class of 8 with low activity, 67 % for 4 weeks; 63 % and 92 % for a class of 12).

### Mitigations compared (proportional ones)

| Rule | What it does | V6a | Availability of the rates (n = 8 / 12, mean activity 0.5; blocks of 2 / 4 weeks) | Change of meaning |
|---|---|---|---|---|
| A. As first written | cells and summary independent | **open** | 71 % / 95 %; 90 % / 98 % | none |
| Rounding the rates to whole percents | coarser rates | **not closed** (see above) | same as A | the rates lose precision |
| B. Every week must be published | the rates and documents only when every cell of the block is published | closed | **13 % / 60 %; 4 % / 40 %** | none, but the block shows almost nothing |
| C. B and also `active_students` | idem | closed | idem | idem |
| **F. Published weeks only** | the summary is computed **only over the weeks of the block whose weekly cell is published** | **closed by construction**: the response depends on the published weeks only, so the denominator of the rates is the sum of the published cells | **53 % / 92 %; 72 % / 98 %** (summary published) | the summary says which weeks it covers; stated, never silent |

**Recommendation: rule F.** It is the only one that closes V6a without making small classes read «Datos insuficientes» almost always. It needs one more nullable field to say which weeks the summary covers (`summary_weeks`), so that a figure is never presented with a meaning it does not have. A block of two weeks is always contiguous; the field also works if the block becomes four weeks (D-Q10), where a single `summary_window` could not describe weeks 1 and 3.

**V6b is not closed by rule F.** It is a complement between two published families (a document and a rate), pre-existing, and its only complete mitigation withholds `no_cited_source_rate` whenever any current document with a citation has its figure withheld, which happens in most subjects (documents with fewer than 5 citing students are the common case); that cost was not simulated. Proportional answer: **characterise it** with a test that reproduces it (PASS means confirmed), register it as a new finding in `docs/technical-debt.md` in the implementing pull request, and let the owner decide (D-Q17). It does not block P1.

### Transitions between a figure and `null`

| Transition | What it reveals | Verdict |
|---|---|---|
| A cell null while the summary is published | nothing new: under rule F the summary simply leaves that week out; the reason (fewer than 5, a heavy student, no activity) is not told | safe |
| `active_students` shown, rates null | only a dominance over the answers of the covered weeks; under rule F a week passes only if no student has more than half of its questions, so the rates fail by dominance rarely (answers and questions differ only when some answer is missing) | one weak bit, accepted (V6d) |
| A document null among shown ones | fewer than 5 citing students or a heavy one | as today |
| A block seen published and later null | a removal (the teacher did it, and the marker hides the block whole) or an erasure of a student's data (their right) | existing residual: blocks are immutable once ended, so any change is attributable to an erasure; **tested** with the erasure invariant extended to blocks |
| A block seen null and later published | impossible without an erasure of a heavy student; no new fact can enter an ended block | test: adding facts after the end of a block never changes it |
| Visible figure to `null` when the marker moves | a removal, known to the teacher | safe |

### Two weeks against four weeks (rule F, small classes)

Share of reads in which the summary is published (at least one week of the block passes). The last column is the average share of the block's weeks that the summary covers over all reads; it is the same for both lengths, as the weeks are independent:

| n | mean activity | 2 weeks | 4 weeks | share of the block's weeks covered |
|---|---|---|---|---|
| 5 | 0.5 | 5 % | 10 % | 3 % |
| 6 | 0.8 | 76 % | 91 % | 57 % |
| 8 | 0.3 | 10 % | 17 % | 5 % |
| 8 | 0.5 | 53 % | 72 % | 33 % |
| 12 | 0.3 | 43 % | 64 % | 25 % |
| 12 | 0.5 | 92 % | 98 % | 75 % |
| 20 | 0.3 | 90 % | 99 % | 72 % |

Readings. (1) Under rule F the length of the block is **no longer a privacy parameter** (the composition attack of rule A grows with it, rule F does not depend on it): it only trades availability against freshness. (2) Four weeks gain 10 to 20 points of availability for classes of 8 to 12, at the price of a summary that is 0 to 28 days old (0 to 14 with two weeks) and that returns **28 to 56 days after a removal, mean 42** (14 to 28, mean 21, with two weeks). (3) Classes of 5 or 6 with low or medium activity stay withheld with either length: the floor of 5 decides, not the block. (4) The weekly cell, which is the recent signal, is the same in both. Recommendation: **keep two weeks provisionally** (as decided); revisit with the data of the pilot, and move to four if classes of 8 to 12 read «Datos insuficientes» in the summary more than the owner accepts. The constant is one line.

### Historical blocks through `end` (not approved; analysed)

Blocks do not overlap, so reading several of them gives no subtraction. The analysis found **no new inference vector** from historical blocks, and four costs: (1) more blocks mean more observations for the composition attacks, which rule F closes per block; (2) an ended block is immutable, so any change in an old block can only come from an erasure or a removal, a signal that exists today in the weekly series; (3) the summary would not match the series window unless the page labels it, as it must anyway; (4) a larger test surface and one range read per distinct `end` (F7 is open). Padding with controlled accounts cannot reach back into an old block (an account has no questions before it was enrolled), so old blocks are not easier to pad. **Decision of the owner honoured: P1 does not use `end` for the summary.** The summary is always the latest complete eligible block, whatever `start` and `end` say; `end` and `start` only drive the weekly series. Historical blocks remain a possible later change (D-Q8) with its own tests.

### The rule

- **Blocks.** `BLOCK_WEEKS = 2` (provisional constant), `BLOCK_ANCHOR = 2026-01-05` (a Monday, common to every subject, so that no subject has its own calendar). Block `k` covers `ANCHOR + 14k` to `ANCHOR + 14k + 13`; negative indexes use floor division.
- **Complete.** A block is complete when its last week has ended, one hour after its Sunday (the margin of A2b).
- **The summary block.** The latest complete block, **independent of `start` and `end`**. The one exception only withholds: a request that holds no whole week shows no figure at all (the state of A2), so no fact is read.
- **Eligible.** The block starts at or after `c(M)`, the first Monday strictly after the marker of A2. A block that starts earlier is **withheld whole, never trimmed**. If the latest complete block is not eligible, none is (older ones start earlier): `summary_window` is null.
- **The covered weeks.** A week of the block is *publishable* when it has at least 5 distinct students and no student above 50 % of its questions (the same predicate as its weekly cell, evaluated whatever the requested window). `summary_weeks` lists the publishable weeks; with none, the summary figures are null.
- **The summary figures** are computed only over the covered weeks, for the students enrolled now (D-M5): `active_students`, `no_material_rate`, `no_cited_source_rate` and the `cited_appearances` of every document. Only current documents are listed (superseded: they were listed as today.)
- **The weekly series** is the effective window of A2 and A2b, as today. Its cell is shown when its week is publishable; the old condition of 5 active students in the whole window is implied and is dropped.
- **Dominance.** A figure built from contributions of students is withheld (null) when **one student contributes more than 50 %** of it: the questions of a week for a cell, each side of each rate (superseded wording: it was one decision for both), the appearances of a document for its figure. Exactly 50 % is published. `active_students` is a distinct count and has no dominance rule. It comes **in addition to** the minimum group of 5. The threshold is a provisional constant (`DOMINANCE_SHARE`), like the minimum group (R-D3), to be reviewed with the legal review.
- **No silent change.** A published figure equals the true count **over the weeks that `summary_weeks` declares**; nothing is capped, rounded or noised.
- **A function of the published weeks only.** Two worlds that differ only in what happened in a withheld week give identical responses. This is the property that closes V6a, and the one the tests check.

### What each interaction does

| Case | Result | Why it is safe or what remains |
|---|---|---|
| Two reads of the same block | identical figures | the block is fixed and complete |
| Two reads of different blocks | disjoint periods | nothing to subtract: no overlap |
| A window sliding by a week (V3) | the summary does not move until the next block | the figures of the existing V3 test are equal |
| `start` or `end` changed | the summary does not change | it does not depend on them |
| A removal inside a displayed block | the block disappears from then on | A2: it starts before `c(M)`; it is never shown with and without the student |
| A removal, then a second one a week later | still no block in two versions | a block is shown whole or not at all |
| A re-enrolment | nothing returns | the marker never decreases |
| A newly enrolled student | appears only in later blocks | it has no questions before it was enrolled |
| A student erases their data between two reads of a block | the block moves by their contribution | their right; residual, as before |
| A week with fewer than 5 students, or a heavy student | its cell is null and the summary leaves it out | the isolating subtraction and the composition of V6a no longer exist |
| One heavy student in the covered weeks | a rate is null when one student holds more than half of one of its sides | the identity of the heavy student does not change the response (a test) |
| The summary against the weekly cells | no subtraction: the denominator of the rates is the sum of the published cells of the covered weeks | V6a closed |
| A document against the rate of uncited answers | the rate is null when a deleted document was cited, or the answers citing a withheld document are too few (rule G3, which replaced G2) | V6b open: its uncited-rate channel is closed, not the complements V8 to V10 (D-Q23) |
| The teacher deletes a document | its entry leaves the summary and the uncited rate becomes null if the covered weeks cited it; nothing new is published | closes V7 (D-Q18) |

### Small classes and teachers with few data (simulation, outside the repository)

Under rule F the figures follow the weekly cells, so the question is how often a week is publishable. A class of n students, a weekly activity probability around the mean, a few lively students (heavy tail). Share of weeks in which the weekly cell is **published** with only the minimum group, and with the dominance rule too:

| n | mean activity | weekly cell: 5 students -> with dominance |
|---|---|---|
| 8 | 0.3 | 5 % -> 4 % |
| 8 | 0.5 | 37 % -> 33 % |
| 12 | 0.3 | 28 % -> 25 % |
| 12 | 0.5 | 79 % -> 73 % |
| 20 | 0.3 | 76 % -> 71 % |
| 20 | 0.5 | 99 % -> 98 % |

**The dominance rule at 50 % adds little** (a few points); the floor of 5 students decides. Small and low-activity classes will often read «Datos insuficientes», in the weekly cells and in the summary: that is the privacy rule working. The table of two and four weeks above gives the effect on the summary.

### Effects on availability (reference model, hourly over a week)

| Situation | Two weeks | Four weeks |
|---|---|---|
| Steady state | the summary is 0 to 14 days old (an A2b margin of one hour included) | 0 to 28 days |
| After a removal | the weekly series returns in 7 to 14 days (A2); **the summary in 14 to 28 days, mean 21** | **28 to 56 days, mean 42** |
| A new subject | its first summary appears when the first aligned block is complete, up to two weeks | up to four |
| A class with fewer than 5 active students per week | the cells and the summary stay withheld | idem |

### V6b: the rate of uncited answers against a withheld document figure (rule G)

**What leaks.** `no_cited_source_rate` is the share of answers without a citation (`attribution != "cited"`, including the answers without material). Under rule F the denominator is known (the sum of the published cells), so the teacher gets `C`, the number of answers with a citation. Every cited answer cites at least one document, so if `S` is the sum of the published document figures, the documents with a withheld figure (current ones with a null figure, and deleted ones, which are not listed) together have at least `C - S` appearances, and exactly `C - S` when every answer cites one document. With one withheld document that is its figure. No identity is revealed: it is the volume of a group of fewer than 5 students, or of a heavy one. The bound is not empty in 15 to 99 % of the reads of classes of 8 to 20 with six or more documents in the model, because most documents are rarely cited.

**Treatments compared** (model outside the repository, same arithmetic as the service; share of the reads with published rates in which `no_cited_source_rate` stays published; activity 0.5):

| Class | Documents (deleted) | M1: withhold if any listed document has a withheld figure | M2: withhold if the published figures do not cover the cited answers | **G: withhold if the leak would single out one document** |
|---|---|---|---|---|
| 8 | 3 (0) | 16 % | 43 % | **71 %** |
| 8 | 6 (1) | 0 % | 8 % | **100 %** |
| 8 | 12 (2) | 0 % | 1 % | **100 %** |
| 12 | 3 (0) | 55 % | 81 % | **71 %** |
| 12 | 6 (1) | 0 % | 31 % | **99 %** |
| 12 | 12 (2) | 0 % | 5 % | **100 %** |
| 20 | 3 (0) | 94 % | 99 % | **94 %** |
| 20 | 6 (1) | 12 % | 85 % | **83 %** |
| 20 | 12 (2) | 0 % | 36 % | **100 %** |

- **Do nothing (characterise and register):** the rate always stays, the leak stays (the lower bound of the tail, exact for one withheld document).
- **M1** is sound but the rate disappears in almost every real subject. **M2** reveals through its own null that a withheld document was cited (the bit that the code already protects for deleted documents) and costs nearly the same.
- **G, recommended.** `no_cited_source_rate` is **null when exactly one document, current or deleted, has at least one appearance in the covered weeks and a withheld figure** (fewer than 5 distinct citing students, or one student above 50 % of its appearances). Documents without appearances are not counted. G keeps the rate in 71 to 100 % of the reads and removes the attribution of a volume to one document, which is what the minimum group of documents protects.
- **What G leaves.** When two or more withheld documents were cited, only their **sum** is bounded: a lower bound `C - S` (mean 6 to 14 answers in the model) and an upper bound that depends on how many documents an answer cites. It is the same kind of residual as the sum of the weekly cells, and it cannot be split into documents. The null of the rate reveals one bit (exactly one withheld document was cited), like V6d; a teacher who knows that a document is new learns nothing, because documents without appearances do not count.
- **Safe with rule F.** G depends only on the facts of the covered weeks, so two worlds that differ only in a withheld week still give identical responses. `no_material_rate` does not depend on documents and is not affected: the two rates may now differ in being null (`suppressed` is true when either is).
- **Cost:** the document counts are already built in the same pass; no new query, no field, no migration. The dashboard shows «Datos insuficientes» in the card, as for any withheld figure.

### Validation of rule G (2026-11-25): insufficient as written, completed as G2

Evidence: `reports/2026-11-25-rule-g-validation.md`. V6a, V6b and V7 were reproduced by running the unmodified source of `ActivityService` and `attribution_of`, with plain stand-ins for the schemas and repositories (the project interpreter is still blocked on this host). The adversary of rule G ran on a model of the arithmetic.

- **What holds.** With several citations per answer, new documents, documents withheld for dominance and one deleted document, no read under G let the adversary attribute a volume to one document (six scenarios of about 2 400 reads each). Several citations per answer only widen the bound.
- **What breaks it: V7, deleted documents merge by file name.** A deleted document leaves only the stored file name in the sources, and the service groups deleted sources by that name; nothing prevents two documents of a subject from having the same name. With `notes.pdf` (cited by 6 students, figure 6) and another `notes.pdf` (cited by 3, withheld): deleting the first shows 6, deleting the second shows 9, so the withheld figure is exactly 9 - 6 = 3. It needs no rate, it is deterministic, the teacher triggers it, and **it exists in `main` today** (the switch is off). The same merge turns "exactly one withheld document" into "none", so G then publishes the rate. A new version of a file uploaded and deleted later merges in the same way, without intent.
- **Rule G2 (recommended, replaces G).**
  1. The summary does **not list deleted documents**: their figures can no longer be attributed to one document.
  2. `no_cited_source_rate` is null when **a cited answer of the covered weeks cites a deleted document**, or **exactly one current document** with appearances has a withheld figure.
- **Property of G2: deleting a document only removes or withholds.** Every figure after the deletion is the same as before or null. In 3 000 random worlds with repeated names and successive deletions, a read after a deletion showed something new in 61.4 % of them today, 61.4 % under G and **0 %** under G2.
- **Cost of G2.** The figures of deleted documents disappear (they are shown today when they reach the minimum group), and a block that cites a deleted document has no uncited rate. The share of real blocks affected depends on how often teachers delete material; it was not modelled. No migration, no field: `documents[].document_id` stays nullable in the schema and is no longer null in practice.
- **Alternatives discarded.** Keeping the identity of the document in `message_sources` needs a migration and does not repair the stored rows. Rejecting duplicate names changes the upload contract and does not cover a name used again after a deletion.

**Residuals of G2** (accepted only if the owner approves D-Q17):

| Residual | Size |
|---|---|
| With exactly one withheld current document listed, the null or published rate tells whether it was cited at all (one bit, no volume) | in the model the rate status matched it in every such read |
| With two or more withheld documents cited, their **sum** is bounded | cannot be split |
| A student's erasure can move a document below the minimum and flip the rate from null to published; the teacher then subtracts the figure seen before and bounds the other withheld document | 577 of 6 000 modelled worlds when one random student erases (an upper estimate of a rare event); the bound was exact in 73. The teacher cannot trigger it. It is part of the erasure residual of D-M5 |
| The published totals and document figures allow an **estimate** of the withheld volume if most answers cite one document | an assumption, not a deduction; removing it would mean withholding the totals |

**The criteria could pass without detecting anything.** A random property did not catch the mutant that ignores deleted documents (0 events), and it never catches `at least one`, which leaks nothing and only costs availability. So each mutant needs a **named deterministic scenario**, each random property must **count the cases that trigger it** and fail below a minimum, and the same property must fail on `main` or on the mutant.

### The contract (additive in shape; the meaning of the summary figures changes)

`ActivityResponse` gains two nullable properties, and nothing else changes in the shape:

- `summary_window`: the schema already used by `window` (`start`, `end`, `granularity`, `weeks`); here `weeks` is 2. The fixed block. Null when there is no complete and eligible block.
- `summary_weeks`: a list of one or two dates, ascending, the Mondays of the weeks of the block that the summary covers. Always a subset of the Mondays of `summary_window`. Null when `summary_window` is null or no week of the block is publishable.

| `summary_window` | `summary_weeks` | Meaning | Summary figures |
|---|---|---|---|
| null | null | no complete block yet, or it starts before the first Monday after the marker (A2), or the window has 0 weeks | all null |
| set | null | the block is complete but no week has 5 balanced students | all null |
| set | one Monday | only that week passes the rule of the weekly cell | over that week |
| set | two Mondays | both weeks pass | over both |

- **What changes in meaning (stated, not hidden).** `active_students`, `no_material_rate`, `no_cited_source_rate` and `documents` stop covering the requested window and cover `summary_weeks` within `summary_window`. Their names and types do not change, so it is additive in shape and **not** in meaning. The only consumer is the teacher dashboard, switched off by default; there are no external consumers (to be confirmed by the owner with D-Q14).
- `documents` lists only current documents (D-Q18); the schema keeps `document_id` nullable.
- `window`, `questions`, `enrolled_students`, `suppressed` and the document names keep their shape. `questions` keeps its description and adds that a cell is also null when one student concentrates it. `suppressed` keeps its meaning (any figure withheld).
- The descriptions in `docs/api-spec.yml` are written in task 3.1d, not now. The shape test `test_activity_schema_shape.py` fails until the new keys are reviewed (by design), the generated types are regenerated and the contract test is updated.
- **Why two fields.** `summary_weeks` says which weeks a figure covers, so that no figure is shown with a meaning it does not have; with a single field defined as the covered weeks, a block of four weeks (D-Q10) would break the description, because weeks 1 and 3 are not contiguous. The single-field variant is kept only as a documented alternative.

Illustrative response (fictitious values; the first week has four students, so only the second is covered):

```json
{
  "window": {"start": "2026-11-02", "end": "2026-11-29", "granularity": "week", "weeks": 4},
  "summary_window": {"start": "2026-11-16", "end": "2026-11-29", "granularity": "week", "weeks": 2},
  "summary_weeks": ["2026-11-23"],
  "enrolled_students": 9,
  "active_students": 6,
  "no_material_rate": 0.083,
  "no_cited_source_rate": null,
  "suppressed": true
}
```

### The dashboard (final proposal of the Spanish copy; the owner approves the wording in D-Q13)

| Place | Text |
|---|---|
| Label of the summary block | «Resumen del bloque del {inicio} al {fin}» (dates in the format of the existing window line) |
| Both weeks covered | «Incluye las dos semanas del bloque.» |
| One week covered | «Incluye solo las semanas con datos suficientes: {semanas}.» |
| Note under it | «El resumen se actualiza cada dos semanas completas.» |
| Definition of the active students | «Estudiantes que hicieron al menos una pregunta en las semanas incluidas.» |
| No complete block yet, or no week with enough data | «Todavía no hay un bloque completo de dos semanas con datos suficientes para mostrar el resumen.» |
| A withheld figure | «Datos insuficientes» (unchanged; never zero, never a bar) |
| Privacy note (revised in the second review round) | «Cada cifra de actividad que se muestra proviene de al menos {n} estudiantes y ninguna persona aporta más de la mitad; cuando no se cumple, se indica «Datos insuficientes». Aun así, al combinar cifras o comparar consultas podría deducirse información sobre grupos pequeños o sobre una persona. Las cifras pueden cambiar entre consultas.» |

The weekly table keeps its caption and its window line («Semanas del … al …», A2 and A2b); the summary has its own label, so the two ranges are never confused. The cards, the shares and the documents are under the summary label. The judgement-word scan covers the new strings. With `summary_window` null, or no covered week, the summary section shows the enrolled count, «Datos insuficientes» in the cards and the «no complete block» note; the states of A2 (`weeks` below 12, 0) stay.

### Acceptance criteria (tests planned, written first)

> Written for rule G2 and **superseded**: see the sections on the two independent reviews below.

**On `main`, before the rule** (characterisation, PASS means the leak is confirmed, like the tests of part A): V6a (the withheld cell recovered from the rates, on the real service), V6b (the withheld document figure recovered from the rate), each with its `xfail(strict)` property test of the mitigation. **First gate of the implementation:** these characterisations run on the real service on a host where the project interpreter runs (it is blocked by the application-control policy of the host used for this specification, so the leaks are demonstrated here only on a port of the arithmetic). If they do not reproduce V6a and V6b, implementation stops and the finding is reported; the non-interference properties are not accepted as detecting the leaks until they fail on `main`.

- **V3, unchanged test as the acceptance:** the existing `test_v3_property_holds_moving_the_window_does_not_reveal_a_students_activity` (today `xfail(strict)`) passes without edits and its marker is removed in the same change. Both of its reads fall in the same latest block, so the test alone is weak: it is complemented by the properties below.
- **V3, new properties** (random worlds with fixed seeds, no new dependency): for any two reads, the two `summary_window` are equal or disjoint; equal windows give identical summary figures; a sequence of reads, removals and re-enrolments never shows the same block in two versions; the summary does not depend on `start` or on `end`.
- **V3, adversarial scenarios:** the sixth student active only in the first week of the **latest** block is not isolable from reads one week apart; a withheld week cannot be isolated by sliding or by the timing of removals.
- **Composition (V6a), the central new criterion, a non-interference property:** for random worlds, a second world that differs only in the facts of a **withheld** week (the volume or the students of a week with fewer than 5 students, the volume of a heavy student of a withheld week, the answers of that week) gives a **byte-identical response**; the denominator of the rates equals the sum of the published cells of `summary_weeks` (recomputed independently); an executable adversary (the candidate-total search used in this review) finds exactly one candidate, the true published total, and nothing about the withheld weeks. The test is not vacuous: it first fails on `main` (the TDD failing run) and a mutant that computes the summary over the whole block makes it fail.
- **V6b, rule G2:** exactly one withheld current document with appearances gives a null `no_cited_source_rate` while `no_material_rate` stays published; two give a published rate; a withheld document without appearances (a new one) is not counted; any cited deleted document gives a null rate; a document withheld for dominance is counted; the decision does not depend on a withheld week (non-interference); a published figure equals the true count.
- **V7:** the characterisation on `main` (two documents with one name, deleted one after the other, give the withheld figure exactly); after the change, no deleted document is listed, and the property that a deletion only removes or withholds passes and fails on `main`.
- **Non-vacuity:** one named scenario per mutant; each random property counts its triggering cases and fails below a minimum. In the non-interference property both worlds keep the same enrolled students and keep the week withheld.
- **Transitions:** adding facts after a block has ended never changes it; a removal makes it null; an erasure of a student's data equals the world in which the student never existed (the erasure invariant of the integration module, extended to blocks); a block never shows a figure for a week that is not in `summary_weeks`.
- **F6:** the characterisation of V4 (50, 1, 1, 1, 1) now gives a null cell; 4, 1, 1, 1, 1 (exactly 50 %) is published; 5, 1, 1, 1, 1 is withheld; balanced students are published; the rates and each document follow the same rule; which student is heavy does not change the response; a published figure equals the true count (recomputed independently).
- **Small classes:** four active students give a null summary and `summary_weeks`; five balanced give the figures; a block with a week of 4 students and a week of 6 covers only the second; `enrolled_students` is always given.
- **A2 and A2b:** a block that starts before `c(M)` is withheld whole; zero weeks gives a null `summary_window`; the block appears one hour after its Sunday; two subjects have the same blocks.
- **Contract and dashboard:** the schema and the generated types carry the two fields; the page shows the label and the covered weeks, never a withheld figure as zero, no bar for a null; the new states pass the accessibility and judgement-word scans; the Playwright mocked suite and a manual run in the demo environment.
- **Mutation checks:** the blocks overlap (a sliding block), the block is trimmed, `start` or `end` changes the block, the summary is computed over the whole block instead of the covered weeks, the dominance comparison is `>=` instead of `>`, dominance is ignored for the rates or for a document, the figure is capped, the anchor differs by subject, rule G2 with `at least one` instead of `exactly one`, cited deleted documents ignored, deleted documents listed again, documents without appearances counted, dominance-withheld documents not counted, `no_material_rate` made to depend on G2.
- **Independent adversarial review** with a privacy focus, **asked to attack by composition**, before F6, V3 and V6a can be recorded as mitigated.

### Residual risks of P1

> Written for rule G2 and **superseded**: see the sections on the two independent reviews below.

F8 (TD-071) and F7 (TD-070) are untouched; the residuals of G2 in the table above (one bit, the sum of two or more withheld documents, the flip after an erasure, the estimate from totals); a student's own erasure stays noticeable; the comparison between **different** blocks is possible and is a trend of aggregates, not an isolation; the dominance threshold is a provisional number; the summary is up to two weeks old and small or quiet classes will read «Datos insuficientes» often; the suppression of a rate signals that someone concentrates it (V6d, one bit). The leaks were reproduced on the real service source with stand-ins, not yet with the real schemas, database and test suite.

### Decisions (the owner)

| # | Decision | Status | Recommendation or what approval means |
|---|---|---|---|
| D-Q8 | Does `end` select the summary block? | **Closed: no** | a later change if the product needs it |
| D-Q9 to D-Q11 | Anchor 2026-01-05, blocks of two weeks, dominance 50 % | **Decided**, provisional | revisit with pilot data and the legal review |
| D-Q12 | Lower availability | **Accepted provisionally** | knowingly |
| D-Q13 | The Spanish copy | **Approved** (2026-11-25) | G2 needs no new string |
| D-Q14 | `summary_window` and `summary_weeks` | **Approved** (2026-11-25) | G2 adds nothing to the contract shape |
| D-Q15 | Closure criteria | **Approved** (2026-11-25) | the additions are D-Q19 |
| D-Q16 | The composition rule | **Decided: F** | |
| D-Q17 | V6b: rule G2 and its residuals | **Approved** (2026-11-25), subject to the security checks | G is not used |
| D-Q18 | Stop listing deleted documents (V7), with the loss of their figures | **Approved** (2026-11-25) | no migration |
| D-Q19 | Additions to the criteria: V7, one scenario per mutant, minimum triggering cases, the precision of non-interference | **Approved** (2026-11-25) | |

**D-Q15 with the additions of D-Q19.** Nothing is recorded as mitigated before the independent review, and everything is checked on a host where the project interpreter runs, with `mypy --strict`, `ruff` and the whole suite green:

- **V3:** the existing V3 test passes unchanged and without its `xfail`; the block properties; the adversarial scenarios; the mutants of overlap, trimming and selection by `start` or `end` fail.
- **V6a:** the characterisation fails first on `main` on the real service; the non-interference property and the executable adversary pass; the mutant that computes the summary over the whole block fails.
- **F6:** the dominance cases, rates, documents and identity independence pass; the mutants (`>=`, dominance ignored for the rates or a document, a capped figure) fail.
- **V6b:** the characterisation fails first on `main`; the G2 scenarios and non-interference pass; each G2 mutant fails its named scenario.
- **V7:** the characterisation fails first on `main`; no deleted document is listed; the deletion property passes.

### Recommendation

> Written for rule G2 and **superseded**: see the sections on the two independent reviews below.

**Rule G as written: NO-GO** (V7 defeats it). **P1 with G2: GO to implement once the owner approves D-Q17, D-Q18 and D-Q19.** The first gate of task 3.1a stays: the characterisations of V6a, V6b and V7 run with the real service and its test suite on a host where the interpreter runs; if they do not reproduce, stop and report. **NO-GO to enable the capability for real students** whatever the result: F8 (TD-071) and F7 (TD-070) stay open, and V7 is present in `main`, so the switch must stay off until it is fixed.

### Independent review of the implementation (2026-11-25): V6b is not mitigated

The review ran on the real routes and SQL (report in `reports/2026-11-25-implementation.md`). One Major and five Minor findings; it corrects four statements made above.

- **Major, M-1: G2 counts withheld documents, not the students behind what they hide.** One answer that cites two withheld documents gives both figures (1 and 1); one controlled account that cites a third document brings a withheld figure back exactly; the same material uploaded twice does it with no account. The statement that two or more withheld documents "cannot be split" is **false**. V6b stays open.
- **The erasure flip can be triggered by the teacher with a controlled account** (its account deletes its conversations and a week leaves the block): the statement "the teacher cannot trigger it" is false. It belongs with F8.
- **Superseded in the second round (each side of a rate is now checked, so it fires). Dominance on the two rates, as it was, never fired with real data:** a question and its answer are written in one transaction, so answers equal questions per student and week, and a student under half of each covered week is under half of the union. The check stays as defence in depth and is not evidence for F6.
- **Rate numerators have no group rule** (older than P1): one student's 11 answers without material read as 0.355 of 31.
- **Deleting a document probes whether a withheld one was cited** (destructive for the teacher; wider than the one-bit residual).

**Candidate G3 (evaluated, not implemented).** Let U be the cited answers that cite a withheld or unlisted document: publish the uncited rate only if U is empty, or U comes from at least 5 students with none above half and cites nothing unlisted; the whole set of cited answers must pass too. In a throwaway run with the real service it closed the reproductions, kept the deletion property, and failed only the scenario "two withheld cited documents keep the rate". It would leave padding with several controlled accounts (the level of F8). Share of reads with published rates that keep the uncited rate, one citation per answer:

| Class | 3 documents: G2 / G3 | 6 documents: G2 / G3 | 12 documents: G2 / G3 |
|---|---|---|---|
| 8 | 91 % / 47 % | 100 % / 71 % | 100 % / 75 % |
| 12 | 64 % / 45 % | 99 % / 78 % | 100 % / 89 % |
| 20 | 71 % / 69 % | 90 % / 77 % | 100 % / 98 % |
| 40 | 99 % / 99 % | 60 % / 58 % | 100 % / 98 % |

| # | Decision | Status | Recommendation |
|---|---|---|---|
| D-Q20 | V6b: replace G2 by G3, or accept V6b open and keep G2 | **Pending** | G3, with its tests and a new review |
| D-Q21 | Rate numerators: register only, or apply the same predicate to numerators and complements | **Pending** | evaluate together with D-Q20 |
| D-Q22 | The approved privacy note says that figures are shown only from at least 5 students and that none identifies a document; M-1 and the numerators show it says more than the system does | **Pending** | revisit the wording unless D-Q20 and D-Q21 close both |

### Corrections after the review (2026-11-25, second review round): G3, both sides of a rate, and what stays open

**Method.** An exhaustive adversary (now in `backend/tests/composition_oracle.py`) enumerates every world of answer types consistent with a published response and reports each withheld quantity of few students that takes one value in all of them: hidden document figures, answers citing hidden documents, both sides of each rate, their difference, the complements of one or several documents and the cited answers outside some documents. In 1 500 small random classes, with an adversary that knows an answer cites at most one document (and at most two):

| Rules | Worlds with an exact disclosure | What |
|---|---|---|
| G2 | 85 % (87 %) | hidden documents, cited count, retrieved-only count, document complements |
| G3 | 47 % (47 %) | retrieved-only count (the difference of the two rates), document complements |
| G3 and the rate sides | 11 % (15 %) | document complements only |
| ... and rule D | 0 (1 of 1 500) | inclusion and exclusion of two-document answers |

**Verdict on G3 (corrected by the second review, below):** it closes the channel of V6b through the uncited rate, not V6b, and is **not sufficient alone**: the difference of the two rates and the cell total minus a document figure disclosed small groups in 47 % of the worlds.

**Implemented (inside the approved scope).** G3 replaces G2, and each rate needs its sides publishable, as does the retrieved-but-uncited difference when both rates are shown. It is the same predicate and the same convention (an empty group is not publishable, which covers what the rates tell by themselves, not what the document figures add). Allowing 0 % (an empty group publishable) was measured: availability barely differs in classes of 20 or more, so the approved convention is kept.

**Cost** (simulation, 10 % of answers without material, 15 % retrieved only; share of reads with a covered week that keep `no_material_rate` / `no_cited_source_rate`):

| Class | 3 documents, before -> now | 6 documents, before -> now |
|---|---|---|
| 8 | 100 / 89 % -> 2 / 6 % | 100 / 100 % -> 2 / 15 % |
| 12 | 100 / 64 % -> 11 / 21 % | 100 / 99 % -> 10 / 40 % |
| 20 | 100 / 71 % -> 50 / 64 % | 100 / 92 % -> 46 / 68 % |
| 40 | 100 / 100 % -> 96 / 99 % | 100 / 61 % -> 96 / 59 % |

**Small and medium classes will rarely see the two rates.** That is the price of the guarantee on the numerators.

**V8, open: the cell total minus a document figure.** If 12 of 13 questions of the covered weeks are cited document A, the reader knows that one answer did not cite it. It needs no rate. **Rule D (proposed, not implemented, needs approval):** publish no document figure when the answers that cite no published document exist and are not publishable. In the simulation it costs little (document figures shown: 18 -> 13 % for 8 students and 3 documents, 47 -> 41 % for 12, unchanged in larger classes) and removes V8; it leaves inclusion and exclusion between documents that one answer cites together (1 of 1 500 worlds).

**Other residuals, unchanged:** the whole-or-null of a figure tells one bit; deleting documents probes which withheld one was cited; `enrolled_students` minus `active_students` can be one student; changes between reads by erasure, which a teacher can trigger with controlled accounts; padding with accounts (F8).

**Privacy note (D-Q22), now implemented with a claim limited to what is demonstrated:** «Cada cifra de actividad que se muestra proviene de al menos {n} estudiantes y ninguna persona aporta más de la mitad; cuando no se cumple, se indica «Datos insuficientes». Aun así, al combinar cifras o comparar consultas podría deducirse información sobre grupos pequeños o sobre una persona. Las cifras pueden cambiar entre consultas.»

| # | Decision | Status | Recommendation |
|---|---|---|---|
| D-Q20 | V6b: G3 | **Approved as candidate; implemented**; insufficient alone | V6b stays open (D-Q23) |
| D-Q21 | Rate numerators and complements | **Implemented** (approved as a priority) | confirm the loss of availability |
| D-Q22 | Privacy note | **Revised**, wording pending the owner | approve or edit |
| D-Q23 | Rule D for the document complement (V8) | **Pending** | approve; without it F6 stays open |

### Second independent review (2026-11-25): composition is still not closed

Verdict **FAIL**, no Blocker, three Major (report in `reports/2026-11-25-second-round.md`). It corrects statements of the section above.

- **M1. The total, `no_material_rate` and a document figure isolate small groups (V9).** 19 answers, 12 citing A, no-material rate 0.316: exactly one answer had material and did not cite A, so every withheld document figure is at most 1; with none left over they are shown to be zero. **Rule D does not close it.** The adversary lacked this target.
- **M1b. With answers citing two documents, a rate minus a figure gives the answers that cite only withheld documents (V10).** G3 passes because its group also holds answers that cite a published document.
- The table above and the sentence "rule D removes V8" are therefore **incomplete**: the zero of its last row was measured without these targets.
- **M2 and M3** (statements that promised more than the code does, and documents still describing G2): corrected.

**What is established.** Each published rate has both sides publishable; no hidden document figure was determined **with a nonzero value** by the uncited rate; V3, V6a and V7 hold. **V6b and F6 stay open.**

**D-Q23, restated (pending; nothing implemented).** Every open complement needs the document figures. Options, measured with the exhaustive adversary in memory (600 classes) and simulated classes:

| Option | Determined with a nonzero value | Determined zeros | Document figures shown (3 documents; classes of 8 / 12 / 20 / 40) | Guarantee |
|---|---|---|---|---|
| Today | 21 of 300 and 24 of 300 | 8 and 4 | 18 / 47 / 87 / 100 % | none for the complements |
| (a) D': publish document figures only if each group of answers citing no published document that the rates separate is publishable **or empty** | 0 | 8 and 4 | 13 / 39 / 82 / 100 % | one citation per answer; "none" stays visible; intersections of two-document answers are not covered and the adversary has no target for them |
| (b) D' strict (an empty group also withholds) | 0 | 0 | 12 / 29 / 20 / 0 % | one citation per answer; the figures vanish in large classes |
| (c) Publish no document figure (every `cited_appearances` null; the contract keeps its shape) | 0 | 0 | 0 % | any number of citations for rates and documents: nothing is determined from rates and cells alone. It does **not** close V11 (`active_students`), and it must also say what then happens to G3. Removes an approved feature (D-M6) |
| (d) Keep as is, V6b and F6 open | as today | as today | as today | none; no claim is made |

Recommendation: **(c)** if privacy before publication is the aim, as it is the only one whose guarantee does not depend on how many documents an answer cites; **(a)** if the document figures are essential, accepting its limits. Either needs its own tests and a new independent review. It does not close F8, F7, comparisons between reads or `enrolled_students` minus `active_students`.


### V11: the active students against the weekly cells (found 2026-11-25, open)

A published week has at least 5 students and no more students than questions. With both weeks covered, `active_students - 5` bounds how many students asked **only** in one given week: 6 active students mean at most one, 5 mean none. With two cells of 5 and 6 active, exactly one asked only in the first week and one only in the second. No identity follows. The same arithmetic existed before P1; no option of D-Q23 closes it.

**D-Q24 (pending; a new rule, not implemented).** Either (a) declare it and keep `active_students`; or (b) publish `active_students` only when the summary covers a single week, which loses the figure in the usual case; or (c) require a margin (publish only when it is at least 10), which was not measured. Recommendation: decide together with D-Q23; (a) is honest at no cost.

## A first, simplified cut (analysis of 2026-11-26; planning only, nothing implemented)

> **Rejected by the owner on 2026-11-26.** V12, found here, stays valid and open.

**Approved by the owner (2026-11-26).** D-Q23: option (c), no document citation figure is published, as the objective of the first cut. D-Q24: V11 stays a documented residual risk, **not yet accepted for production**. The mitigations of V3 and V7 are kept, subject to their final checks. F8, F7 and the other findings stay open. This replaces the "pending" state of D-Q23 and D-Q24 above. Everything else in this section is a proposal.

### V12: a counted group that is the whole class (found 2026-11-26; present in `main`)

The minimum group of 5 counts who contributed, not who did **not**. The adversary never had `enrolled_students` as an input, so no earlier round looked for this. Reproduced on the service of the branch with a disposable in-memory script (outside the repository, so a test is still due):

| World | Response | What the teacher learns |
|---|---|---|
| 5 enrolled, 5 questions in a week | cell 5, active 5, enrolled 5 | **every enrolled student asked exactly one question** |
| 12 enrolled, all ask | active 12, enrolled 12 | every enrolled student used the assistant |
| 5 enrolled, each with answers of every kind | rates 0.333 and 0.667 | every enrolled student got an answer without material and one without citation |
| 6 enrolled, 5 ask | cell 5, enrolled 6 | which one did not ask is not determined |

These are individual inferences from **one** response, without extra accounts. `main` has the same thresholds, so the same holds there (the capability is switched off). The enrolment dates are known to the teacher, so a student enrolled later does not enlarge the earlier group.

**`active_students` cannot be protected cheaply.** It equals the class whenever everybody asked. Withholding it when `enrolled - active < k` is a rule on the data: beside published weeks, its `null` would itself say that nearly everybody asked (with k = 1, exactly everybody).

**A class floor protects the weekly cells.** Publish a week only if at least F students of the subject were enrolled **before that week started** (current enrolment rows, `created_at`; no migration). The rule reads no activity. With F >= 6 and cells only, for every student there is a world consistent with the response in which they asked in that week and one in which they did not: a published cell only says "at least 5 distinct students", so 5 others can always account for it. What remains is an upper bound (nobody asked more than half of a cell, nor more than the cell minus 4; with a cell of 5, at most once). The argument covers one response and no outside knowledge.

### Rates: keep or retire

| | Keep (with (c)) | Retire |
|---|---|---|
| Use to the teacher | `no_material_rate` points at gaps in the material; the uncited rate is not a measure of quality | no signal about the material |
| Availability (classes of 8 / 12 / 20 / 40) | no material 2 / 11 / 50 / 96 %; uncited 6 / 21 / 64 / 99 % (measured with 10 % of answers without material; a share of 0 is never shown, so "all is well" reads like "not enough data") | none |
| Composition | with (c), rates and cells alone determined nothing (D-Q23 table, 1 or 2 citations, model without `enrolled` and `active`) | none |
| Whole class | V12 applies: needs the floor, and rates against enrolment were never an adversary target | gone |
| Across reads | an erasure or a document deletion can move a rate, which says something about the **kind** of that student's answers | only counts move |
| Data processed | reads the text and sources of every answer | no answer is read |
| Code and tests to maintain | rate sides, G3 or its replacement, blocks, rule F, composition oracle | cells and floor |

**Recommendation: retire both rates from the first cut.** With (c) the case is not a demonstrated leak from rates and cells; it is that small classes rarely see them, that they are the only figures that say something about what a student's answers contained, and that keeping them keeps most of P1's rules and an analysis still to be done.

### Weekly questions and `active_students` together

| Inference | Weekly cells only | Cells + `active_students` |
|---|---|---|
| Whole class (V12) | closed by the floor | **open**, whatever the floor |
| How many asked in only one week (V11) | not published | open: at most `active - 5` per week |
| Students who asked in neither covered week | not derivable | at most `enrolled - active`, down to none |
| Two windows or two blocks subtracted (V3) | not possible: weeks are fixed and disjoint | closed by the blocks |
| A student erases data between two reads | the cell moves by their exact count (open, by the right of erasure) | idem, and `active_students` moves by one |
| A teacher with controlled accounts (F8) | open | open |
| Two cells combined | disjoint, no relation between them | related through `active_students` |

**Limit of "no demonstrable individual inference".** It can be claimed only for one response, with cells and a floor, without outside knowledge. It cannot be claimed across reads around an erasure (an account deletion also changes the roster, so the teacher knows who) or against controlled accounts (F8), which can fill the floor and the group.

### The options

| Option | Publishes | V3 | V6a, V6b, V8-V10 | V11 | V12 | F8, F7, erasure between reads |
|---|---|---|---|---|---|---|
| P1 in the branch | cells, active, 2 rates, document figures | mitigated by blocks | V6a mitigated; V6b and V8-V10 **open** | open | open | open |
| S1 = (c) only | cells, active, 2 rates | blocks | not exposed (document figures gone) | open | open | open |
| S2 | cells, active | blocks | not exposed (no rates) | open | open | open |
| **S3 (recommended)** | cells, enrolled count | not exposed | not exposed | not exposed | closed for cells by the floor | open |

"Not exposed" means that the figure is not published, not that it was mitigated: re-publishing it reopens the vector, so the register keeps each one open or latent with that condition. V7 stays closed by listing only current documents.

**Conflict to decide.** S3 keeps what the V3 mitigation protects (no two reads can be subtracted) but removes the blocks, because no summary figure is left. The owner asked to keep the V3 mitigation: choosing S3 replaces it by non-publication and needs that approval.

**Availability of S3** (weeks of a reference model that would show a cell, from the table of "Two weeks against four weeks"): classes of 8 / 12 at activity 0.5, 33 / 75 %; 12 / 20 at 0.3, 25 / 72 %. With F = 10, a class below 10 shows only the enrolled count. The floor's effect was not simulated beyond that.

### Minimum adjustment for S3 (not applied)

- **Spec** (this change): replace the requirements of the block, the covered weeks, the rates, G3 and the document figures by "only weekly cells and the enrolled count", add the floor, keep dominance for cells, A2, A2b, one snapshot, erasure, switches. The earlier changes `activity-events-and-metrics` and `teacher-activity-dashboard` require rates, active students and documents: they must be reconciled before any of them is archived.
- **Contract**: the shape of `main` is kept. `active_students`, both rates and every `cited_appearances` are always `null`, and their descriptions say that this version does not publish them. `summary_window` and `summary_weeks` exist only in the branch: not adding them breaks nothing in `main`, but reverses D-Q14. `suppressed` must stop counting figures that are never published, or it is always true.
- **Service**: keep the weekly rule, dominance, A2, A2b; add the floor (enrolment dates from the repository); stop reading answers; remove blocks, rates and document use.
- **Dashboard**: enrolled card, window line, weekly table, the notes of limited and no weeks; remove the active card, the shares, the documents table and the block heading. New privacy note.
- **Tests**: keep the weekly, dominance, A2, A2b, snapshot, erasure and switch tests; new, failing first: the V12 worlds, the floor and its non-interference, "withheld figures are always null" with a mutant; the V3, V6a, V6b and V7 tests become vacuous and say so; the composition tests of rates and documents go with their code. Then mutation checks and a new independent review (section 9.8).
- **Documents** (need authorisation when implemented): `api-spec.yml`, `data-model.md`, `technical-debt.md` (V12; the others as latent), roadmap. The proposed patch of `backend-standards.md` is obsolete under S2 or S3 and must be redone.
- The code of P1 is not committed: before removing any of it, keep a copy (a commit, if authorised, or a patch in `reports/`).

Proposed note (replaces D-Q22 under S3, F = 10): «Solo se muestra cuántas preguntas se hicieron cada semana, cuando la asignatura tenía al menos {f} estudiantes inscritos y las preguntas provienen de al menos {n} sin que una persona aporte más de la mitad; si no, se indica «Datos insuficientes». Aun así, comparando consultas o con otra información podría deducirse algo sobre grupos pequeños o sobre una persona.» A figure for `{f}` in the response would change the contract; the text can state it as a constant of the page or avoid the number, to be decided.

### Decisions pending (the owner)

| # | Decision | Recommendation |
|---|---|---|
| D-Q25 | Rates in the first cut | retire both |
| D-Q26 | `active_students` in the first cut (with it, V11 stays and V12 stays open; without it, the blocks of V3 go) | withhold: S3 |
| D-Q27 | Class floor F, a new rule: 10, 6, or none and V12 declared | 10, provisional like N; 6 is what the argument needs |
| D-Q28 | Contract: not adding `summary_window` and `summary_weeks` (reverses D-Q14); meaning of `suppressed` | both as in the adjustment above |
| D-Q29 | Privacy note | the proposed text |

## Original scope restored (owner decisions of 2026-11-26)

**Decisions.** Pedagogical usefulness first; keep the weekly questions, the active students, both rates and the cited documents; no simplified cut; statistical anonymity is not a condition to finish development. V6b, V8 to V12 and inference by composition are candidates for a formal acceptance within a restricted institutional scope, without being marked as mitigated. Keep the access controls, the isolation and the protections that do not cost functionality; keep V3 and V7 where compatible. F8 and F7 stay open. Asked with the measurements below, the owner chose **to remove all four rules of P1** (rate sides, G3, published weeks only, dominance) and **the original 12 weeks** for the summary, which leaves V3 open.

**Evidence for those choices** (600 simulated subjects per row, 3 documents, the code of `main` and of the branch; share of subjects showing active students / each rate / each document figure):

| Class | `main` (12 weeks) | V3 + V7 (2-week block) | plus published weeks and dominance | P1 as it was |
|---|---|---|---|---|
| 8 | 100 / 100 / 98 % | 84 / 84 / 22 % | 54 / 54 / 10 % | 54 / 1 to 3 / 10 % |
| 12 | 100 / 100 / 100 % | 100 / 100 / 55 % | 93 / 93 / 44 % | 93 / 11 to 20 / 44 % |
| 20 | 100 / 100 / 100 % | 100 / 100 / 87 % | 100 / 100 / 85 % | 100 / 50 to 60 / 85 % |

**What the branch changes against `main`:** deleted documents are not listed (V7); the privacy note says that anonymity is not guaranteed; the contract and the data model say the same. The calculation, the response shape and A2/A2b are those of `main`. `summary_window` and `summary_weeks` are gone (they never reached `main`), and D-Q1 to D-Q22 and D-Q25 to D-Q29 no longer apply.

**Residual risks, kept apart.** (a) Candidates for acceptance: V6b, V8, V9, V10, V11, V12 (named by the owner) and V3, V6a, F6 (reopened by the choice of the original rules), and a rate of 0 or 1 and enrolled minus active (added on 2026-11-27). (b) Their own treatment: F8 (TD-071, an identity control) and F7 (TD-070, cost and rate of reads). (c) By design: a student's own erasure stays noticeable between reads. (d) Conditions before real students: the privacy text does not tell students that a teacher reads aggregates, the legal basis and the consent version are missing, and figures that allow inferences about one student must be treated as personal data.

### Findings of the review of the restored scope (2026-11-26) and what was done

- **Major, overclaim about V7.** The spec and a test said that the withheld figure of a deleted document could not be computed. V7 only removes the addition by file name; V8 and V9 still derive or bound it. Wording and test names corrected; V8 and V9 now have their own characterisations.
- **Major, earlier activity and consent (TD-072).** The chat requires consent for the policy in force when a message is written, but the read does not look at it, so enabling would process history written under earlier texts. **Owner decision (2026-11-27):** record it, change no consent rule, process no real activity, and keep the legal evaluation of real data as an independent condition of activation; consent is not assumed to be the only legal basis. It does not block the technical merge, since both switches stay false.
- **Owner decisions of 2026-11-27.** The new wording of the privacy note is **approved**. A rate of 0 or 1 and enrolled minus active join the candidates for a formal acceptance; none is accepted for production. V3, V6, V8 to V12 and F6 stay documented as open; TD-072, F8 and F7 stay open.
- **Minor.** The register, the contract and the privacy note also name the inferences about the whole class, a rate of 0 or 1 and enrolled minus active.

## Closure of the technical integration (owner decisions of 2026-11-27)

- Pull request #37 is in `main` (`7bd636a`) and the CI of `main` is green.
- P3, P4 and P5 (tasks 3.3 to 3.5) are **rescheduled** to the future change `activity-enablement-conditions`, not done and not dropped. F8 stays open as a confirmed Major finding, F7 stays open and the legal requirements stay pending. Nothing is accepted for production.
- The deltas of `activity-events-and-metrics` and `teacher-activity-dashboard` are updated to the integrated behaviour before they are ever synced.
- **Archive blocked (recorded 2026-11-27, owner instruction):** `docs/base-standards.md` §9.8 says a change is not closed with an open blocker or major finding, and F8 (Major) is open. Rescheduling the work on F8 does not lift the block. `activity-events-and-metrics`, `teacher-activity-dashboard` and this change stay **not archived and not synced** until F8 is no longer open. No exception to the standard is proposed.

## Tests (demonstration, no persistent data)

The first group uses `ActivityService` with the in-memory repository of `test_activity_service.py`, fictitious ids and fixed dates; it reads and writes nothing persistent. The end-to-end check of V2 (registration, enrolment by email, questions) ran on a throwaway database in its own container, with the owner's authorisation (D-P1 and D-P2 granted on 2026-11-23), and CI runs it on its own test database.

## Dependencies and standards that need authorisation when implemented

| What | Where | Why |
|---|---|---|
| TD-069 update (F8, the evidence, the classification) and a TD-070 note | `docs/technical-debt.md` | records what is demonstrated |
| Option A: a migration and `ended_at` | `docs/data-model.md`, Alembic | D-H6 |
| Option B, C or F: a change in the meaning of a figure or in a parameter | `docs/api-spec.yml`, the generated types, the dashboard copy | D-H6 |
| The sentences of the aggregate rule | `docs/backend-standards.md` section 9 | only if a rule changes |

## Decisions pending (the owner, before any implementation)

| # | Decision | Recommendation |
|---|---|---|
| D-P1 | Run the demonstration tests (in memory, no persistent data) | yes, first |
| D-P2 | Run the end-to-end test of V2 on a disposable database | yes, after D-P1 |
| D-P3 | Option A: a migration and the retention of the enrolment after unenrolment (reverses D-M5) | not recommended since D-P9 (A2) reaches the same result without retention; needs the legal review if chosen |
| D-P4 | Options B and C: precision and meaning of the figures | C yes; B only if A is refused |
| D-P5 | Option F: restrict `start` and `end` | yes |
| D-P6 | Option H: a persistent access record, its retention and its reviewer | yes, with the retention defined first |
| D-P7 | Verified institutional email or another control for V2 | needed before real students |
| D-P8 | A limit of reads (G) | optional |
| D-P9 | Package P2: a marker of the last unenrolment on the subject and forward-only figures (A2) instead of A | recommended over A; needs the migration, the contract note and the loss of history accepted |
| D-P10 | F8: a written acceptance as a residual risk, plus I2 and I6, with I3 or I8 as the strong later option | recommended; a verified email alone is not accepted |

## Risks and open points

- The demonstration tests can show that a vector is **not** reproducible in a form assumed here; the finding is then corrected, not forced.
- Option A and the right of erasure: the retained row about the student must disappear with the student's own deletion (spec, erasure).
- The default window slides weekly, so V3 does not need parameters; F reduces it and does not close it.
- No part of this change reduces the need for the legal review of N = 5 and of the policy text.

## Evidence to produce when implemented

- The failing run of the demonstration tests in `reports/` (TDD evidence).
- The end-to-end result for V2: confirmed or refuted.
- For each approved mitigation: the unchanged vector test passing, a mutation check that removes it, and the erasure test.
- An independent adversarial review with a privacy focus and the final residual-risk table.

## Findings of the independent review (2026-11-23) and what was done

The review (`reports/2026-11-23-a2-adversarial-review.md`) found no Blocker. **M-1 (Major)**: the activity route held two pooled connections per request (the shared session that authenticates plus the snapshot), so a burst of reads could take the whole pool and block every route (15 threads, none served, on the default pool); fixed by closing the shared session before the snapshot opens, with a test on a pool of one. **m-1**: a chat transaction that began before Monday 00:00 UTC could commit after it, so a week now counts as ended one hour after its Sunday (`ENDED_GRACE`). **m-2**: two mutants survived (`now()` for `clock_timestamp()`, no conversion to UTC); tests and mutation checks added. **m-3**: two tests used the local date; they use UTC. **m-4**: the static test is a best-effort tripwire and says so. **m-5**: the contract and spec text were reconciled. **m-6**: the PR stages only the files of this change. **q-2**, the word «reciente» of the approved copy was imprecise (the note can show for up to 13 weeks): the owner decided on 2026-11-23 to say «Por un cambio en las inscripciones» in both states, and it was changed.

## Implementation notes (2026-11-23, A2 + A2b)

Decided by the owner: A2 and A2b are implemented together; D-P9a to D-P9g, D-P11 (the notice «Se muestran solo semanas completas.») and D-P12 are approved; P1 and every other mitigation stay out. The read uses **its own session** at `REPEATABLE READ` read-only, because the authentication of the request has already run statements in the shared session of the request and the isolation level cannot change after the first statement. The removal uses a savepoint, so that a removal that deletes nothing undoes the marker whatever the outer handler does. Evidence is in `reports/`.
