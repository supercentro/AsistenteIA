# Proposal

## Why

The aggregate teacher activity (`GET /subjects/{subject_id}/activity`, changes `activity-events-and-metrics` and `teacher-activity-dashboard`, both merged and **switched off by default**) withholds every figure from fewer than 5 distinct students. Explore (2026-11-23, security and privacy of F1) found that this threshold is checked on the cohort **at the moment of the request**, and that the cohort is data the teacher controls. A threshold limits what one read shows; it does not stop the **difference between two reads** from returning one person's contribution. TD-069 already records the unenrolment version of this (F1, Major). Explore added two more paths: a teacher who controls student accounts pads the group (**F8, not confirmed**) and a teacher who moves the window by whole weeks differences the window-wide figures. This change plans how to **demonstrate** these vectors with tests and how to choose proportionate mitigations. It is not a legal opinion and does not enable anything.

## What Changes

Planning only; nothing is implemented. Approved by the owner on 2026-11-23:

- Threat model: a teacher who can **manipulate enrolments and control student accounts**, not only an honest but curious one.
- **F8** is added next to TD-069 as a finding **not confirmed until it is reproduced**. Reproduced end to end on 2026-11-23 and recorded as TD-071 (Major, open).
- Priority: **demonstrate with tests** F1, F8 and the comparison between windows, before any mitigation.
- Mitigations are weighed as **preventive, detective or organisational**, keeping the right of erasure and the existing privacy limits.
- Keeping enrolments, raising N, limiting queries or logging accesses are **not assumed to resolve a risk on their own**.
- **P2 / A2** (a non-personal marker of the last unenrolment; figures only over whole weeks after it) is the priority for F1. It keeps D-M5, keeps no enrolment after a removal and keeps the right of erasure; it is specified in `design.md` and `spec.md` and **not implemented**. F1 stays open until its demonstration passes. A second validation round (2026-11-23) fixed two defects of the first draft (the order of the writes against the deletion of a subject, and the single snapshot of the read), described how the new column grant reaches existing environments (`db-migrate` then `db-verify`, not applied), checked `weeks = 0` against the contract, and evaluated V5 and A2b (the rule that only ended weeks are shown), which is a separate decision.

Pending owner approval, **not decided here** (see `design.md`, D-P1 to D-P8): any migration; any change of contract; keeping enrolments after unenrolment (this reverses the approved D-M5); identity verification of students; a persistent access record; any change of the meaning or precision of a figure.

Explicitly out of scope: implementing any mitigation, running tests that change persistent data, enabling either switch, changing the aggregation rules, any use with real students, any resolution of F6 or F7 beyond what the owner approves later, archiving.

## Capabilities

### New Capabilities
- `activity-privacy-hardening`: how the inference vectors are demonstrated, what a mitigation must prove, what it must preserve (erasure, switches, defaults), and how the residual risks are recorded.

### Modified Capabilities
<!-- None now. Changes to `teacher-activity-metrics` (the aggregation) would be proposed only after the owner approves a mitigation (design D-P). -->

## Impact

- **Authorisation and isolation:** unchanged by this planning. Every vector concerns the owner teacher, who already may read the aggregate; no new access is granted.
- **Personal data (GDPR):** the vectors recover one student's activity from aggregates, which is the harm to prevent. Options that keep data after unenrolment, add an access record or verify identity create new processing and need the owner and legal review first.
- **External services:** none; no Gemini call.
- **Contracts:** `docs/api-spec.yml` and `docs/data-model.md` are **not** changed now. Option A would change `data-model.md` (an `ended_at` and a migration); options B, C and F would change the meaning or the parameters of the response. Each needs the owner's approval first.
- **Code and standards:** none now. When authorised: backend tests with an in-memory repository (no persistent data) and, later and separately, the approved mitigation.
- **Other documents (when authorised):** a TD-069 update with F8 and the evidence, a TD-070 note for the query limit, the roadmap; no edit of `readme.md` or `prompts.md`.
- **Defaults:** `TEACHER_ACTIVITY_ENABLED=false` and `VITE_TEACHER_ACTIVITY_ENABLED=false` stay.
