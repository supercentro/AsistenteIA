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
