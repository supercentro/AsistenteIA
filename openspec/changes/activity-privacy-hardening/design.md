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
