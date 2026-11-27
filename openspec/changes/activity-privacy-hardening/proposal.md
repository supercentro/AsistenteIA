# Proposal

## Why

The aggregate teacher activity (`GET /subjects/{subject_id}/activity`, changes `activity-events-and-metrics` and `teacher-activity-dashboard`, both merged and **switched off by default**) withholds every figure from fewer than 5 distinct students. Explore (2026-11-23, security and privacy of F1) found that this threshold is checked on the cohort **at the moment of the request**, and that the cohort is data the teacher controls. A threshold limits what one read shows; it does not stop the **difference between two reads** from returning one person's contribution. TD-069 already records the unenrolment version of this (F1, Major). Explore added two more paths: a teacher who controls student accounts pads the group (**F8, not confirmed**) and a teacher who moves the window by whole weeks differences the window-wide figures. This change plans how to **demonstrate** these vectors with tests and how to choose proportionate mitigations. It is not a legal opinion and does not enable anything.

## What Changes

**Current status (2026-11-27):** A2 + A2b are in `main`; the restored dashboard with the V7 correction is in a branch, not merged; P1 was removed from it before any merge. The list below is the planning record and its present tense is of its date. Approved by the owner on 2026-11-23:

- Threat model: a teacher who can **manipulate enrolments and control student accounts**, not only an honest but curious one.
- **F8** is added next to TD-069 as a finding **not confirmed until it is reproduced**. Reproduced end to end on 2026-11-23 and recorded as TD-071 (Major, open).
- Priority: **demonstrate with tests** F1, F8 and the comparison between windows, before any mitigation.
- Mitigations are weighed as **preventive, detective or organisational**, keeping the right of erasure and the existing privacy limits.
- Keeping enrolments, raising N, limiting queries or logging accesses are **not assumed to resolve a risk on their own**.
- **P2 / A2** (a non-personal marker of the last unenrolment; figures only over whole weeks after it) is the priority for F1. It keeps D-M5, keeps no enrolment after a removal and keeps the right of erasure; it is specified in `design.md` and `spec.md` and **not implemented**. F1 stays open until its demonstration passes. **P1** (2026-11-24) is specified: fixed, complete, non-overlapping blocks of two weeks for the summary figures (an additive field `summary_window`) and a provisional 50 % dominance rule, to close V3 and F6; it was reviewed on 2026-11-24 for the **composition of published figures**, which found V6a (a withheld cell recovered from the rates, also present today) and V6b (a withheld document figure recovered from the uncited rate); the summary is therefore computed only over the weeks of the block whose weekly cell is published (two additive fields, `summary_window` and `summary_weeks`). The validation of 2026-11-25 found V7 (deleted documents merged by file name reveal a withheld figure; present in `main`): deleted documents are no longer listed. Two independent reviews led to rule G3 (replacing G2) and to rates whose sides must each be publishable. P1 is **implemented in the branch and not merged**: V3, V6a and V7 are mitigated there; **V6b and F6 stay open** because the document figures can be subtracted from totals and rates (V8 to V10, decision D-Q23 pending), and F7 and F8 are not closed by P1.

**Owner decisions of 2026-11-26 (current).** The dashboard keeps every planned metric over the requested window; P1 and the simplified cut are **not** carried forward. Only the correction of V7 is added. V3, V6, V8 to V12 and F6 are open residual risks, candidates for a formal acceptance within a restricted institutional scope; F8 and F7 stay open with their own treatment. Nothing is enabled. The paragraphs above and below that mention P1 are history.

Pending owner approval, **not decided here** (see `design.md`, D-P1 to D-P8): any migration; any change of contract; keeping enrolments after unenrolment (this reverses the approved D-M5); identity verification of students; a persistent access record; any change of the meaning or precision of a figure.

Explicitly out of scope: implementing any mitigation, running tests that change persistent data, enabling either switch, changing the aggregation rules, any use with real students, any resolution of F6 or F7 beyond what the owner approves later, archiving.

## Capabilities

### New Capabilities
- `activity-privacy-hardening`: how the inference vectors are demonstrated, what a mitigation must prove, what it must preserve (erasure, switches, defaults), and how the residual risks are recorded.

### Modified Capabilities
No capability of `openspec/specs/` changes. `teacher-activity-metrics` still lives in the unarchived change `activity-events-and-metrics`; its spec does not say what happens to deleted documents, and its design said they stay listed. The V7 correction replaces that sentence (owner approval D-Q18, kept on 2026-11-26).

## Impact

- **Authorisation and isolation:** unchanged by this planning. Every vector concerns the owner teacher, who already may read the aggregate; no new access is granted.
- **Personal data (GDPR):** the vectors recover one student's activity from aggregates, which is the harm to prevent. Options that keep data after unenrolment, add an access record or verify identity create new processing and need the owner and legal review first.
- **External services:** none; no Gemini call.
- **Contracts:** A2 + A2b added `subjects.last_unenrolment_at` (migration `0008`) and changed `docs/api-spec.yml` and `docs/data-model.md` (in `main`). The branch changes the same two documents for V7 and for the stated limits; no migration and no change of the response shape.
- **Code and standards:** in the branch, the service lists current documents only, the privacy note of the page says that anonymity is not guaranteed, and tests characterise the open risks. No change of standards.
- **Other documents (when authorised):** a TD-069 update with F8 and the evidence, a TD-070 note for the query limit, the roadmap; no edit of `readme.md` or `prompts.md`.
- **Defaults:** `TEACHER_ACTIVITY_ENABLED=false` and `VITE_TEACHER_ACTIVITY_ENABLED=false` stay.
