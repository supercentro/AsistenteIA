# Round 5: M2 corrected with advisory locks, stopped backend diagnosed, CLI privilege consumers, final verification

**Change**: chat-rag-endpoint, branch `feature/chat-rag-endpoint` (uncommitted), 2026-11-17
**Owner decisions applied**: M2 corrected with transactional advisory locks (approval covers only that); diagnosis and controlled recovery of the stopped backend authorised; CLI privileges **not** changed; TD-003 open; technical closure with the 11 skipped tests kept visible.
**Not done, by instruction or by lack of a safe way**: no `docker compose up` on the current stack, no bootstrap, no migration, no recreation of any persistent container, no change to PostgreSQL or its volumes, no secret touched, no Docker Desktop restart, no real Gemini call (every test, the Linux suite and the isolated Compose run used the fake LLM), no skill, hook or standard edited, no push, PR, merge or archive.

## 1. M2: state **resolved**

| Item | Detail |
|---|---|
| Lock | `pg_advisory_xact_lock(space, key)`, two-integer form: `space` = constant `ENROLLMENT_LOCK_SPACE` (0x454E524C), `key` = signed 32-bit integer from SHA-256 of `student_id:subject_id` (`enrollment_lock_key`). The two-integer form is a separate key space from the one-bigint document admission lock |
| Where | `EnrollmentRepository.lock_student_subject`; called as the **first statement of `RAGService.persist`** (before consent, enrollment and conversation revalidation) and **before the delete in `EnrollmentRepository.delete_for_teacher_subject`**, the only path that removes an enrollment |
| Held until | commit or rollback of the transaction (`commit_or_rollback` in `_persist_phase`; `commit_or_rollback` in the unenrolment endpoint). A savepoint rollback does not release it (the outer transaction does) |
| Never held during | the read phase, the embedding, the LLM call (the read session is closed and `generate` touches no repository) |
| Ordering rule (no deadlock) | at most one advisory lock per transaction, taken before the statements that depend on it; the admission lock is never taken in the same transaction; the row locks taken afterwards are never held by a transaction that is waiting for this lock. Documented in design D3 |
| Privileges, contracts, model | none changed: advisory locks need no table privilege (a role with only `SELECT` is refused row locks, verified on a disposable PostgreSQL), no HTTP status or body changed, same transaction model |
| Subject deletion | takes no advisory lock: a turn for a deleted subject fails its foreign key (404) or is removed by the cascade |
| Consent | there is no revocation endpoint; consent stops being current only when the policy version is raised (a restart); any change committed before the lock is released is seen by the revalidation, which is tested |

OpenSpec artifacts edited through the `/opsx:update` procedure under your approval, and only for M2: `design.md` (paragraph "Serialising persistence with unenrolment"), `specs/rag-chat/spec.md` (requirement "Persistence and unenrolment are serialised per student and subject", 6 scenarios), `tasks.md` (6.6, 6.7, 7.11, 7.12, all ticked with evidence). `openspec validate chat-rag-endpoint --strict` passes.

**Deterministic tests** (`tests/integration/test_chat_enrollment_lock.py`, 12 tests, plus `tests/unit/test_enrollment_lock.py` and two in `tests/unit/test_rag_service.py`). A separate session stands for the other transaction and releases only after PostgreSQL itself reports the waiter in `pg_locks`:

| Case | Result |
|---|---|
| unenrolment while a persist holds the lock | the removal waits, then completes (204) |
| persist while an unenrolment is in flight | the persist waits, revalidates, **403, nothing stored** |
| rolled-back unenrolment | the persist proceeds (200), the turn is stored |
| consent stops being current while the persist waits | 403 `CONSENT_REQUIRED`, nothing stored |
| persist in flight (paused inside the write) and an unenrolment arrives | the turn commits first (200), then the unenrolment (204) |
| other student, other subject | not blocked |
| no advisory lock during embedding and generation | 0 locks observed at both points |
| commit refused | the lock is released, the next unenrolment is not stuck |
| unenrolment of a student who is not enrolled | 404, no lock left |
| teacher who does not own the subject | 404, nothing deleted, no lock left |
| persist waiting longer than the statement timeout | clean 503 `SERVICE_UNAVAILABLE`, no SQL or timeout text, nothing stored |
| 3 chat threads and 1 enrol/unenrol toggler | no 5xx (a deadlock would be one); every 200 stored its whole turn |

The failing run was recorded first (the modules did not import). The file ran **20 consecutive times without a failure**. Five **mutations** were each detected by named tests and reverted: no lock in persist, none in the unenrolment, lock after the revalidation, one global key, lock taken in the read phase. Two weaknesses of my own tests were found and fixed on the way (L47): a test that raced an operation against its own competitor (failed 2 of 8 runs for a correct reason) and holders left open on failure, which made two mutation runs hang instead of fail.

**Independent focused review** (clean context, read-only): **PASS WITH GAPS**, no blocker, no major.

| # | Finding | Disposition |
|---|---|---|
| 1 | tasks 6.6, 6.7, 7.12 open | ticked after the role-bound run |
| 2 | the "read and generation take no lock" test did not exercise `prepare` | fixed (asserts after `prepare` and after `generate`) |
| 3 | missing negative tests | (a) not-enrolled student and (b) non-owner teacher added; (c) `conversation_repo.create` raising while the lock is held is covered by the unit test of the foreign-key path and by `test_a_failed_persist_releases_the_lock...`, no new test |
| 4 | lock counts were database-wide | filtered on `classid` = the lock space |
| 5 (question) | subject deletion cascade against a persist could form a cycle | analysed: it needs a subject deletion at the same moment as a persist of that subject; PostgreSQL then aborts one side (40P01), which the API maps to a clean 503 and no data is lost. It exists **without** the advisory lock (foreign-key row locks only) and the new lock adds no edge to it (the unenrolment takes the lock before its delete and waits holding nothing). Left as a known low-probability 503; **not accepted**: your decision |
| 6 (question) | waiting is bounded by `statement_timeout` (15 s) | tested: clean 503 |
| design wording | "first" applies to the dependent statement | design text corrected |

## 2. The stopped backend (`asistenteia-backend-1`)

**Diagnosis (read-only)**

| Observation | Evidence |
|---|---|
| stopped on 2026-11-17 14:38:57 UTC, exit 1, `OOMKilled=false`, `restart=no` | `docker inspect` |
| last log line: `WatchfilesRustInternalError: error in underlying watcher: Cannot allocate memory (os error 12)` | `docker logs` |
| no kill or OOM event retained by Docker for 14:30-14:45 UTC | `docker events` |
| the VM has 16 GB, 12.6 GB available afterwards; `inotify` limits 1048576 watches / 8192 instances | `/proc/meminfo`, `/proc/sys/fs/inotify` |
| since 2026-11-16 it reloaded **145 times** (my edits reach it through the `./backend/app` bind mount) and **127 of those reloads crashed** with `GOOGLE_API_KEY is required when LLM_BACKEND=gemini` | `docker logs` counts |
| it was created from an older Compose: its environment has no `GOOGLE_API_KEY`, `LLM_BACKEND`, `EMBEDDER_BACKEND` or model path, and its image (c1955d0b..., 398 MB) has no embedding dependencies | `docker inspect` (variable **names** only) |

**Attribution.** The cause of the stop is **not established**: no OOM kill or event is recorded, the VM has memory now, the inotify limits are not the problem. A memory-pressure episode in the shared VM while my disposable workloads ran coincides in time, but it was not demonstrated and I do not state it as the cause. What the evidence does show is separate and certain: this development API had been serving a crashed application since the first source edit of this change (every reload failed on the missing setting) while Docker reported `Up`.

**Recovery: not performed, because no safe isolated operation exists.** Starting the stopped container (`docker start`) would run today's source with the November environment and image and fail the same way (127 times already in its log): the container would be "Up" and broken. A working backend needs all of: (1) a rebuilt backend image (embedding extra and model), (2) new variables in `backend/.env` (`LLM_BACKEND=fake` and `ALLOW_FAKE_LLM=true`, or a `GOOGLE_API_KEY`, which is a secret), (3) migration 0007 on the development database (the chat endpoints need the three new tables), (4) recreation of the backend container. Items 2 to 4 are exactly what you prohibited. Procedure for you, when you authorise it: back up the development database per `docs/development_guide.md`; run the documented `db-migrate` step; add the variables; then `docker compose up -d --build --no-deps backend` (this recreates only the backend).

**`--reload`: evaluated, documented first, then removed from the development command.** Reasons: the watcher is the component that failed; the bind mount plus `--reload` coupled every repository edit to a running container, which restarted its API 145 times and kept it broken for two days without any signal. Cost: after editing `app/` run `docker compose restart backend` (the mount supplies the code; a restart does not apply a changed environment or image, as the guide already says). Changes: the decision and its evidence in `docs/development_guide.md` (services line, the notes of section 2, the worker mount note), the two `--reload` arguments removed from `docker-compose.yml` with a comment, a comment in `test_deployment_files.py`. The bind mount stays (its test is unchanged). **It takes effect only when the backend is next recreated; nothing running was changed.**

**Disposable resources.** Every container, network, volume and image created in this round was removed and checked: 0 `chatiso`, `chatr4`, `g10`, `m2` or `chat-verify` containers, volumes, networks; the scratch images are gone. One note: a diagnostic `docker run alpine` pulled `alpine:latest` (about 8 MB); it existed 11 days ago, so I cannot tell whether it was already present and I left it. The persistent `asistenteia-db-1` (started 2026-11-15, healthy), worker (healthy), frontend and `asistenteia-postgres` are as they were.

## 3. CLI privileges: finding recorded, nothing changed

`asistente_cli` holds SELECT and DELETE on `conversations` and SELECT on `messages` (matrix and `AHEAD_OF_INVENTORY`). Real consumers: **none**. grep over `app/cli.py`, `app/db_admin/`, `app/services/user_admin_service.py` finds no use; the only references are the matrix declaration, `tests/unit/test_db_privileges_matrix.py` (`cli_allowed`) and the exemption list, all for an erasure command that does not exist. Consequence: whoever holds `CLI_DATABASE_URL` (an administrative credential) can read every student's messages and delete conversations without any command needing it. Proposed specific correction, to be done later under the documented controls (not authorised now): remove those three grants from `db_privileges.py`, the three exemption lines, the `cli_allowed` entries, the CLI rows of `docs/data-model.md` and the matching scenarios of the conversation-history spec (`/opsx:update`), then run `db-verify`, the role-bound suites and the Linux gate; the erasure command should come with its own reviewed grants.

## 4. TD-003: open, unchanged

`docs/technical-debt.md` is untouched. No privacy-policy text, Gemini disclosure or consent screen exists in the repository. No automated test, the Linux suite or the isolated Compose run called Gemini or used real student data (fake LLM everywhere). TD-003 must be closed before real students use chat, not before this PR.

## 5. Final verification (after the last change)

| Check | Result |
|---|---|
| `openspec validate chat-rag-endpoint --strict` | valid; 78 of 78 tasks ticked |
| Host: `ruff check .`, `ruff format --check .`, `mypy --strict app tests` | clean (267 and 265 files) |
| Host unit | 1460 passed, 4 failed (Windows-only, environmental, pass on Linux), 110 skipped (Linux-only) |
| Host integration, not role-bound | 935 passed, 0 failed (before the three last small tests; the Linux run below includes them) |
| **Linux, disposable PostgreSQL only** (own orchestration of the CI job and the gate steps) | ruff, format, `mypy --strict app tests` clean; unit **1563** passed; integration not role-bound **973** passed; role-bound **452** passed; roles mode **531** passed; coverage of the changed modules: `enrollment_repository` 98%, `rag_service` 93%, `llm_service` 82% |
| Isolated Compose (`chatiso`) on the final tree | `up -d --build` exit 0; bootstrap and migrate exit 0; revision 0007; `db-verify` no findings; backend healthy and **started without `--reload`**; worker healthy; frontend ready; end-to-end script all PASS (real worker and embedder, fake LLM); torn down |

**The 11 skipped tests, kept visible.** On Linux, `tests/unit/test_deployment_files.py` (7) and `tests/unit/test_environment_files.py` (4) skip with `git or the repository metadata is not available`: the test image holds a copy of the files, not a git checkout. They run and **pass on the host** (78 passed, no skip, in those two files), and in CI, which checks the repository out. They are not hidden: they appear in the `-rs` output of every Linux run.

**Memory guard.** This round did not use the archived gate script. The earlier Linux gate run (round 3) used a scratch copy of it with the memory floor lowered from 6 GB to 4 GB; that deviation stays documented (round 4, section 4) and was not repeated. Free memory stayed between 3.6 and 4.8 GB during the isolated runs and was monitored; no run was started below 3.5 GB.

## 6. Residual findings (none accepted by me)

1. Subject deletion racing a persist can abort one side with a deadlock error (clean 503); pre-existing, not worsened (section 1, finding 5).
2. CLI over-grant (section 3): awaiting your authorisation to narrow it.
3. The development backend container is stopped and, even when started, cannot serve this code until its image, environment and database are updated (section 2).
4. TD-003 (section 4).
5. The minor items of the round-4 table are unchanged: D7 request logs not implemented, safety-block detection by text, `last_message_preview` always null, homoglyphs not folded, no sustained-load test (a 60-request burst was fine).
6. No run satisfies the original 6 GB memory guard of the archived gate script.
7. Windows host: 4 unit tests fail for environmental reasons; Linux and CI are the reference.

## 7. GO / NO-GO

**GO to open the pull request** (it was not opened): every major finding is fixed or explicitly out of this change, all 78 tasks are ticked with reproducible evidence, the independent reviews of every round ended without an open blocker or major, and the Linux suite, the gate steps and an isolated full-stack run pass on the final code. Conditions to carry into the PR description: TD-003 stays open and chat must not be used with real students until it is closed; the development backend needs the update described in section 2 before it can serve this code; the CLI over-grant and the subject-deletion 503 are known and awaiting your decisions; ask for a review of `docs/development_guide.md` and `docker-compose.yml` (the `--reload` change).
