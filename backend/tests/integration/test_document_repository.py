"""`DocumentRepository` against PostgreSQL (change 6, task 7.1).

Admission (subject lock, global admission lock, quota, queue depth, pending bytes), listing, reading
and deleting, all scoped by the owning teacher and the subject. Limits are checked under real
concurrency from several sessions.
"""

import threading
import time
import uuid

import pytest
from app.repositories.document_repository import (
    ADMISSION_LOCK_KEY,
    AdmissionLimits,
    DocumentRepository,
)
from sqlalchemy import text

from app.core.errors import (
    DocumentQuotaExceededError,
    IngestionQueueFullError,
    NotFoundError,
)
from tests.ingestion_support import (
    PDF_BYTES,
    Scene,
    add_subject,
    chunk_count,
    document_state,
    insert_pending,
    job_state,
    make_scene,
    run_together,
    session_for,
)
from tests.sql_support import count, insert_chunk, insert_document, insert_user, run, scalar

LIMITS = AdmissionLimits(max_documents=50, queue_max=100, pending_bytes_max=200 * 1024 * 1024)


def upload(
    scene: Scene,
    payload: bytes = PDF_BYTES,
    limits: AdmissionLimits = LIMITS,
    filename: str = "notes.pdf",
    subject: uuid.UUID | None = None,
    teacher: uuid.UUID | None = None,
) -> uuid.UUID:
    """One upload in its own transaction; returns the document id."""
    with session_for(scene.url) as session:
        document = DocumentRepository(session).add_with_job(
            teacher_id=teacher or scene.teacher,
            subject_id=subject or scene.subject,
            filename=filename,
            content_type="application/pdf",
            payload=payload,
            limits=limits,
        )
        document_id = document.id
        session.commit()
    return document_id


@pytest.fixture
def scene(clean_db: str) -> Scene:
    return make_scene(clean_db)


class TestAdmission:
    def test_the_document_and_its_job_are_stored_together(self, scene: Scene) -> None:
        document_id = upload(scene, b"%PDF-1.7 abc", filename="algebra.pdf")

        state = document_state(scene.url, document_id)
        assert state["status"] == "pending"
        assert state["error_code"] is None
        assert state["chunks_count"] == 0
        assert count(scene.url, "documents", "id = :d AND size_bytes = 12", d=document_id) == 1
        assert count(scene.url, "documents", "filename = 'algebra.pdf'") == 1
        assert count(scene.url, "ingestion_jobs", "document_id = :d", d=document_id) == 1
        assert (
            count(
                scene.url,
                "ingestion_jobs",
                "document_id = :d AND payload = CAST(:p AS bytea) AND attempts = 0 "
                "AND locked_by IS NULL",
                d=document_id,
                p=b"%PDF-1.7 abc",
            )
            == 1
        )

    def test_nothing_is_visible_before_the_caller_commits(self, scene: Scene) -> None:
        with session_for(scene.url) as session:
            DocumentRepository(session).add_with_job(
                teacher_id=scene.teacher,
                subject_id=scene.subject,
                filename="a.pdf",
                content_type="application/pdf",
                payload=PDF_BYTES,
                limits=LIMITS,
            )

            assert count(scene.url, "documents") == 0
            session.rollback()

        assert count(scene.url, "documents") == 0
        assert count(scene.url, "ingestion_jobs") == 0

    def test_another_teacher_and_an_unknown_subject_get_the_same_not_found(
        self, scene: Scene
    ) -> None:
        other = insert_user(scene.url, "other-teacher@example.com", "teacher")
        messages = []
        for teacher, subject in ((other, scene.subject), (scene.teacher, uuid.uuid4())):
            with pytest.raises(NotFoundError) as caught:
                upload(scene, teacher=teacher, subject=subject)
            messages.append((str(caught.value), caught.value.status_code))

        assert messages[0] == messages[1]
        assert count(scene.url, "documents") == 0
        assert count(scene.url, "ingestion_jobs") == 0

    def test_a_student_cannot_upload(self, scene: Scene) -> None:
        student = insert_user(scene.url, "student@example.com", "student")

        with pytest.raises(NotFoundError):
            upload(scene, teacher=student)

        assert count(scene.url, "documents") == 0

    def test_a_subject_at_the_cap_refuses_the_next_document(self, scene: Scene) -> None:
        for index in range(3):
            insert_document(scene.url, scene.subject, f"d{index}.pdf", "ready")
        small = AdmissionLimits(max_documents=3, queue_max=100, pending_bytes_max=10**9)

        with pytest.raises(DocumentQuotaExceededError) as caught:
            upload(scene, limits=small)

        assert caught.value.status_code == 409
        assert caught.value.code == "DOCUMENT_QUOTA_EXCEEDED"
        assert count(scene.url, "documents") == 3
        assert count(scene.url, "ingestion_jobs") == 0

    def test_documents_of_every_status_count_towards_the_cap(self, scene: Scene) -> None:
        for status in ("pending", "processing", "ready", "failed"):
            insert_document(scene.url, scene.subject, f"{status}.pdf", status)
        limits = AdmissionLimits(max_documents=4, queue_max=100, pending_bytes_max=10**9)

        with pytest.raises(DocumentQuotaExceededError):
            upload(scene, limits=limits)

    def test_one_below_the_cap_is_accepted(self, scene: Scene) -> None:
        for index in range(2):
            insert_document(scene.url, scene.subject, f"d{index}.pdf", "ready")
        limits = AdmissionLimits(max_documents=3, queue_max=100, pending_bytes_max=10**9)

        upload(scene, limits=limits)

        assert count(scene.url, "documents") == 3

    def test_the_cap_is_per_subject(self, scene: Scene) -> None:
        other_subject = add_subject(scene.url, scene.teacher, "Other")
        for index in range(2):
            insert_document(scene.url, other_subject, f"d{index}.pdf", "ready")
        limits = AdmissionLimits(max_documents=2, queue_max=100, pending_bytes_max=10**9)

        upload(scene, limits=limits)

        assert count(scene.url, "documents", "subject_id = :s", s=scene.subject) == 1

    def test_deleting_a_document_frees_space_in_a_full_subject(self, scene: Scene) -> None:
        first = insert_document(scene.url, scene.subject, "a.pdf", "ready")
        insert_document(scene.url, scene.subject, "b.pdf", "ready")
        limits = AdmissionLimits(max_documents=2, queue_max=100, pending_bytes_max=10**9)
        with pytest.raises(DocumentQuotaExceededError):
            upload(scene, limits=limits)

        with session_for(scene.url) as session:
            assert DocumentRepository(session).delete_for_teacher(
                scene.subject, first, scene.teacher
            )
            session.commit()
        upload(scene, limits=limits)

        assert count(scene.url, "documents", "subject_id = :s", s=scene.subject) == 2

    def test_unfinished_jobs_at_the_queue_limit_refuse_the_next_upload(self, scene: Scene) -> None:
        insert_pending(scene.url, scene.subject)
        insert_pending(scene.url, scene.subject, status="processing")
        limits = AdmissionLimits(max_documents=50, queue_max=2, pending_bytes_max=10**9)

        with pytest.raises(IngestionQueueFullError) as caught:
            upload(scene, limits=limits)

        assert caught.value.status_code == 503
        assert caught.value.code == "INGESTION_QUEUE_FULL"
        assert int(caught.value.headers["Retry-After"]) >= 1  # type: ignore[index]
        assert count(scene.url, "documents") == 2

    def test_finished_jobs_do_not_count_as_queued(self, scene: Scene) -> None:
        insert_pending(scene.url, scene.subject, payload=None, status="ready")
        insert_pending(scene.url, scene.subject, payload=None, status="failed")
        limits = AdmissionLimits(max_documents=50, queue_max=1, pending_bytes_max=10**9)

        upload(scene, limits=limits)

        assert count(scene.url, "documents") == 3

    def test_the_queue_counts_jobs_of_every_subject(self, scene: Scene) -> None:
        other = make_scene(scene.url, "b")
        insert_pending(scene.url, other.subject)
        limits = AdmissionLimits(max_documents=50, queue_max=1, pending_bytes_max=10**9)

        with pytest.raises(IngestionQueueFullError):
            upload(scene, limits=limits)

    def test_pending_bytes_over_the_limit_refuse_the_upload(self, scene: Scene) -> None:
        insert_pending(scene.url, scene.subject, payload=b"x" * 60)
        limits = AdmissionLimits(max_documents=50, queue_max=100, pending_bytes_max=100)

        with pytest.raises(IngestionQueueFullError):
            upload(scene, payload=b"y" * 41, limits=limits)

        assert count(scene.url, "documents") == 1

    def test_pending_bytes_exactly_at_the_limit_are_accepted(self, scene: Scene) -> None:
        insert_pending(scene.url, scene.subject, payload=b"x" * 60)
        limits = AdmissionLimits(max_documents=50, queue_max=100, pending_bytes_max=100)

        upload(scene, payload=b"y" * 40, limits=limits)

        assert count(scene.url, "documents") == 2

    def test_erased_bytes_do_not_count_as_pending(self, scene: Scene) -> None:
        insert_pending(scene.url, scene.subject, payload=None, status="ready")
        limits = AdmissionLimits(max_documents=50, queue_max=100, pending_bytes_max=40)

        upload(scene, payload=b"y" * 40, limits=limits)

    def test_a_single_file_larger_than_all_the_pending_bytes_is_refused(self, scene: Scene) -> None:
        limits = AdmissionLimits(max_documents=50, queue_max=100, pending_bytes_max=10)

        with pytest.raises(IngestionQueueFullError):
            upload(scene, payload=b"z" * 11, limits=limits)

    def test_the_quota_is_reported_before_the_queue(self, scene: Scene) -> None:
        insert_pending(scene.url, scene.subject)
        limits = AdmissionLimits(max_documents=1, queue_max=1, pending_bytes_max=10**9)

        with pytest.raises(DocumentQuotaExceededError):
            upload(scene, limits=limits)

    def test_a_refusal_stores_nothing_even_after_a_commit_attempt(self, scene: Scene) -> None:
        limits = AdmissionLimits(max_documents=50, queue_max=0 + 1, pending_bytes_max=10**9)
        insert_pending(scene.url, scene.subject)

        with session_for(scene.url) as session, pytest.raises(IngestionQueueFullError):
            DocumentRepository(session).add_with_job(
                teacher_id=scene.teacher,
                subject_id=scene.subject,
                filename="x.pdf",
                content_type="application/pdf",
                payload=PDF_BYTES,
                limits=limits,
            )
            session.commit()

        assert count(scene.url, "documents") == 1


class TestListGetDelete:
    def test_the_owner_lists_newest_first_without_content(self, scene: Scene) -> None:
        first, _ = insert_pending(scene.url, scene.subject, filename="first.pdf")
        run(scene.url, "UPDATE documents SET created_at = now() - interval '1 hour'")
        second, _ = insert_pending(scene.url, scene.subject, filename="second.pdf")

        with session_for(scene.url) as session:
            listed = DocumentRepository(session).list_for_teacher(scene.subject, scene.teacher)

        assert listed is not None
        assert [document.id for document in listed] == [second, first]
        assert not hasattr(listed[0], "payload")

    def test_an_empty_subject_returns_an_empty_list(self, scene: Scene) -> None:
        with session_for(scene.url) as session:
            assert DocumentRepository(session).list_for_teacher(scene.subject, scene.teacher) == []

    def test_documents_of_other_subjects_are_not_listed(self, scene: Scene) -> None:
        other = add_subject(scene.url, scene.teacher, "Other")
        insert_pending(scene.url, other)
        mine, _ = insert_pending(scene.url, scene.subject)

        with session_for(scene.url) as session:
            listed = DocumentRepository(session).list_for_teacher(scene.subject, scene.teacher)

        assert listed is not None and [d.id for d in listed] == [mine]

    def test_another_teacher_an_unknown_subject_and_a_student_get_none(self, scene: Scene) -> None:
        insert_pending(scene.url, scene.subject)
        other = insert_user(scene.url, "other@example.com", "teacher")
        student = insert_user(scene.url, "student@example.com", "student")

        with session_for(scene.url) as session:
            repository = DocumentRepository(session)
            assert repository.list_for_teacher(scene.subject, other) is None
            assert repository.list_for_teacher(uuid.uuid4(), scene.teacher) is None
            assert repository.list_for_teacher(scene.subject, student) is None

    def test_get_returns_the_document_of_the_owner_only(self, scene: Scene) -> None:
        document, _ = insert_pending(scene.url, scene.subject, filename="mine.pdf")
        other = insert_user(scene.url, "other@example.com", "teacher")
        other_subject = add_subject(scene.url, scene.teacher, "Other")

        with session_for(scene.url) as session:
            repository = DocumentRepository(session)
            found = repository.get_for_teacher(scene.subject, document, scene.teacher)
            assert found is not None and found.filename == "mine.pdf"
            assert repository.get_for_teacher(scene.subject, document, other) is None
            assert repository.get_for_teacher(other_subject, document, scene.teacher) is None
            assert repository.get_for_teacher(scene.subject, uuid.uuid4(), scene.teacher) is None

    def test_delete_removes_the_document_its_chunks_and_its_job(self, scene: Scene) -> None:
        document, job = insert_pending(scene.url, scene.subject, status="ready", payload=None)
        insert_chunk(scene.url, document, scene.subject, 0)
        insert_chunk(scene.url, document, scene.subject, 1)

        with session_for(scene.url) as session:
            assert DocumentRepository(session).delete_for_teacher(
                scene.subject, document, scene.teacher
            )
            session.commit()

        assert document_state(scene.url, document) == {}
        assert job_state(scene.url, job) == {}
        assert chunk_count(scene.url, document) == 0

    def test_delete_of_another_subjects_document_touches_nothing(self, scene: Scene) -> None:
        other_subject = add_subject(scene.url, scene.teacher, "Other")
        document, job = insert_pending(scene.url, other_subject)

        with session_for(scene.url) as session:
            deleted = DocumentRepository(session).delete_for_teacher(
                scene.subject, document, scene.teacher
            )
            session.commit()

        assert deleted is False
        assert document_state(scene.url, document)["status"] == "pending"
        assert job_state(scene.url, job)["has_payload"] is True

    def test_delete_by_another_teacher_a_student_or_for_an_unknown_id_touches_nothing(
        self, scene: Scene
    ) -> None:
        document, _ = insert_pending(scene.url, scene.subject)
        other = insert_user(scene.url, "other@example.com", "teacher")
        student = insert_user(scene.url, "student@example.com", "student")

        with session_for(scene.url) as session:
            repository = DocumentRepository(session)
            assert repository.delete_for_teacher(scene.subject, document, other) is False
            assert repository.delete_for_teacher(scene.subject, document, student) is False
            assert (
                repository.delete_for_teacher(scene.subject, uuid.uuid4(), scene.teacher) is False
            )
            session.commit()

        assert document_state(scene.url, document)["status"] == "pending"

    def test_delete_does_not_wait_for_a_worker_that_holds_no_lock(self, scene: Scene) -> None:
        document, _ = insert_pending(scene.url, scene.subject, status="processing")
        started = time.monotonic()

        with session_for(scene.url) as session:
            DocumentRepository(session).delete_for_teacher(scene.subject, document, scene.teacher)
            session.commit()

        assert time.monotonic() - started < 5
        assert document_state(scene.url, document) == {}


class TestConcurrency:
    def test_many_uploads_to_a_subject_with_one_free_place_accept_exactly_one(
        self, scene: Scene
    ) -> None:
        for index in range(49):
            insert_document(scene.url, scene.subject, f"d{index}.pdf", "ready")

        outcomes = run_together(12, lambda i: upload(scene, filename=f"new{i}.pdf"))

        accepted = [o for o in outcomes if isinstance(o, uuid.UUID)]
        refused = [o for o in outcomes if isinstance(o, DocumentQuotaExceededError)]
        assert len(accepted) == 1
        assert len(refused) == 11
        assert count(scene.url, "documents", "subject_id = :s", s=scene.subject) == 50
        assert count(scene.url, "ingestion_jobs") == 1

    def test_uploads_from_different_subjects_fight_for_the_last_queue_slot(
        self, scene: Scene
    ) -> None:
        subjects = [add_subject(scene.url, scene.teacher, f"S{i}") for i in range(10)]
        insert_pending(scene.url, scene.subject)
        limits = AdmissionLimits(max_documents=50, queue_max=2, pending_bytes_max=10**9)

        outcomes = run_together(10, lambda i: upload(scene, limits=limits, subject=subjects[i]))

        assert len([o for o in outcomes if isinstance(o, uuid.UUID)]) == 1
        assert len([o for o in outcomes if isinstance(o, IngestionQueueFullError)]) == 9
        assert count(scene.url, "ingestion_jobs", "payload IS NOT NULL") == 2

    def test_uploads_from_different_subjects_fight_for_the_last_bytes(self, scene: Scene) -> None:
        subjects = [add_subject(scene.url, scene.teacher, f"S{i}") for i in range(10)]
        insert_pending(scene.url, scene.subject, payload=b"x" * 50)
        limits = AdmissionLimits(max_documents=50, queue_max=100, pending_bytes_max=150)

        outcomes = run_together(
            10, lambda i: upload(scene, payload=b"y" * 60, limits=limits, subject=subjects[i])
        )

        assert len([o for o in outcomes if isinstance(o, uuid.UUID)]) == 1
        assert count(scene.url, "ingestion_jobs", "payload IS NOT NULL") == 2
        total = scalar(scene.url, "SELECT sum(octet_length(payload)) FROM ingestion_jobs")
        assert total == 110  # 50 already queued plus one 60-byte file; never above 150

    def test_uploads_to_different_subjects_all_succeed_without_deadlock_over_many_rounds(
        self, scene: Scene
    ) -> None:
        subjects = [add_subject(scene.url, scene.teacher, f"S{i}") for i in range(6)]

        for round_number in range(4):
            outcomes = run_together(
                18,
                lambda i, r=round_number: upload(
                    scene, subject=subjects[i % 6], filename=f"{r}-{i}.pdf"
                ),
            )

            failures = [o for o in outcomes if isinstance(o, BaseException)]
            assert failures == [], [type(f).__name__ for f in failures]

        assert count(scene.url, "documents") == 72
        assert count(scene.url, "ingestion_jobs") == 72

    def test_uploads_and_deletions_together_never_deadlock(self, scene: Scene) -> None:
        subjects = [add_subject(scene.url, scene.teacher, f"S{i}") for i in range(4)]
        existing = [insert_pending(scene.url, subjects[i % 4])[0] for i in range(16)]

        def work(index: int) -> object:
            if index % 2 == 0:
                return upload(scene, subject=subjects[index % 4], filename=f"u{index}.pdf")
            with session_for(scene.url) as session:
                result = DocumentRepository(session).delete_for_teacher(
                    subjects[index % 4], existing[index], scene.teacher
                )
                session.commit()
                return result

        outcomes = run_together(16, work)

        failures = [o for o in outcomes if isinstance(o, BaseException)]
        assert failures == [], [type(f).__name__ for f in failures]

    def test_the_subject_row_lock_serialises_uploads_to_that_subject_only(
        self, scene: Scene
    ) -> None:
        other_subject = add_subject(scene.url, scene.teacher, "Other")
        holder = session_for(scene.url)
        session = holder.__enter__()
        try:
            session.execute(
                text("SELECT id FROM subjects WHERE id = :s FOR UPDATE"), {"s": scene.subject}
            )
            done = threading.Event()

            def blocked_upload() -> None:
                upload(scene, subject=scene.subject)
                done.set()

            thread = threading.Thread(target=blocked_upload)
            thread.start()
            upload(scene, subject=other_subject)  # a different subject is not delayed
            time.sleep(1.0)

            assert not done.is_set()  # the same subject waits for the lock
            session.rollback()
            thread.join(timeout=20)
            assert done.is_set()
        finally:
            holder.__exit__(None, None, None)

    def test_the_global_admission_lock_is_taken_after_the_subject_lock(self, scene: Scene) -> None:
        holder = session_for(scene.url)
        session = holder.__enter__()
        try:
            session.execute(text("SELECT pg_advisory_xact_lock(:k)"), {"k": ADMISSION_LOCK_KEY})
            done = threading.Event()

            def blocked_upload() -> None:
                upload(scene)
                done.set()

            thread = threading.Thread(target=blocked_upload)
            thread.start()
            time.sleep(1.0)

            assert not done.is_set()
            waiting = count(
                scene.url,
                "pg_locks",
                "locktype = 'advisory' AND NOT granted",
            )
            assert waiting == 1
            session.rollback()
            thread.join(timeout=20)
            assert done.is_set()
        finally:
            holder.__exit__(None, None, None)
