"""The limits of the upload under concurrency (change 6, task 9.2).

Simultaneous uploads, each over its own HTTP client in its own thread, compete for the last free
document slot of a subject, the last free queue slot and the last free pending bytes. The limits
are hard: they are counted and the row is inserted under the subject and admission locks.
"""

import uuid
from collections import Counter
from collections.abc import Sequence

import pytest
from fastapi.testclient import TestClient

from app.main import create_app
from app.models.user import UserRole
from tests.ingestion_support import insert_pending, run_together
from tests.integration.helpers import (
    FAST_PASSWORDS,
    build_settings,
    insert_subject,
    insert_user,
    login_token,
)
from tests.sql_support import count, scalar
from tests.upload_support import PDF, TEXT, documents_url

THREADS = 24


def statuses(results: Sequence[object]) -> Counter[int]:
    """Status codes of the results; an exception in a thread counts as 0 (and fails the tests)."""
    return Counter(getattr(r, "status_code", 0) for r in results)


def app_for(url: str, **overrides: object) -> TestClient:
    app = create_app(
        build_settings(url, upload_max_in_flight=100, **overrides), password_service=FAST_PASSWORDS
    )
    return TestClient(app, raise_server_exceptions=False)


def teacher_token(client: TestClient, url: str, email: str) -> tuple[str, str]:
    teacher = insert_user(url, email, UserRole.TEACHER)
    return teacher.id, login_token(client, email)


def test_simultaneous_uploads_leave_exactly_fifty_documents(clean_db: str) -> None:
    client = app_for(clean_db)
    teacher_id, token = teacher_token(client, clean_db, "t@example.com")
    subject = insert_subject(clean_db, teacher_id)
    for _ in range(49):
        insert_pending(clean_db, uuid.UUID(subject), payload=None, status="ready")
    headers = {"Authorization": f"Bearer {token}"}

    def attempt(index: int) -> object:
        return client.post(
            documents_url(subject), files={"file": (f"n{index}.txt", TEXT)}, headers=headers
        )

    results = run_together(THREADS, attempt)

    assert statuses(results) == Counter({202: 1, 409: THREADS - 1})
    assert count(clean_db, "documents") == 50
    assert count(clean_db, "ingestion_jobs") == 50


def test_the_cap_holds_over_many_rounds(clean_db: str) -> None:
    client = app_for(clean_db, max_documents_per_subject=6)
    teacher_id, token = teacher_token(client, clean_db, "t@example.com")
    subject = insert_subject(clean_db, teacher_id)
    headers = {"Authorization": f"Bearer {token}"}

    for _ in range(3):
        run_together(
            10,
            lambda i: client.post(
                documents_url(subject), files={"file": (f"n{i}.txt", TEXT)}, headers=headers
            ),
        )
        assert count(clean_db, "documents") <= 6

    assert count(clean_db, "documents") == 6


def test_the_last_free_queue_slot_goes_to_exactly_one_of_many_subjects(clean_db: str) -> None:
    client = app_for(clean_db, ingestion_queue_max=5)
    teacher_id, token = teacher_token(client, clean_db, "t@example.com")
    subjects = [insert_subject(clean_db, teacher_id, f"S{i}") for i in range(THREADS)]
    headers = {"Authorization": f"Bearer {token}"}
    for _ in range(4):
        insert_pending(clean_db, uuid.UUID(subjects[0]))  # four unfinished jobs, one slot left

    results = run_together(
        THREADS,
        lambda i: client.post(
            documents_url(subjects[i]), files={"file": ("n.txt", TEXT)}, headers=headers
        ),
    )

    assert statuses(results) == Counter({202: 1, 503: THREADS - 1})
    assert count(clean_db, "ingestion_jobs", "payload IS NOT NULL") == 5


def test_the_queue_never_exceeds_its_maximum_with_uploads_from_different_subjects(
    clean_db: str,
) -> None:
    client = app_for(clean_db, ingestion_queue_max=3)
    teacher_id, token = teacher_token(client, clean_db, "t@example.com")
    subjects = [insert_subject(clean_db, teacher_id, f"S{i}") for i in range(THREADS)]
    headers = {"Authorization": f"Bearer {token}"}

    results = run_together(
        THREADS,
        lambda i: client.post(
            documents_url(subjects[i]), files={"file": ("n.pdf", PDF)}, headers=headers
        ),
    )

    assert statuses(results) == Counter({202: 3, 503: THREADS - 3})
    assert count(clean_db, "ingestion_jobs", "payload IS NOT NULL") == 3
    assert count(clean_db, "documents") == 3


def test_the_pending_bytes_never_exceed_their_maximum(clean_db: str) -> None:
    client = app_for(clean_db, max_upload_mb=1, ingestion_pending_bytes_max_mb=2)
    teacher_id, token = teacher_token(client, clean_db, "t@example.com")
    subjects = [insert_subject(clean_db, teacher_id, f"S{i}") for i in range(12)]
    headers = {"Authorization": f"Bearer {token}"}
    content = b"a" * 700_000  # two fit in 2 MB, three do not

    results = run_together(
        12,
        lambda i: client.post(
            documents_url(subjects[i]), files={"file": ("n.txt", content)}, headers=headers
        ),
    )

    assert statuses(results) == Counter({202: 2, 503: 10})
    total = scalar(clean_db, "SELECT sum(octet_length(payload)) FROM ingestion_jobs")
    assert total == 1_400_000
    assert int(str(total)) <= 2 * 1024 * 1024


def test_a_delete_and_an_upload_racing_for_the_last_slot_never_exceed_the_cap(
    clean_db: str,
) -> None:
    client = app_for(clean_db, max_documents_per_subject=3)
    teacher_id, token = teacher_token(client, clean_db, "t@example.com")
    subject = insert_subject(clean_db, teacher_id)
    first, _ = insert_pending(clean_db, uuid.UUID(subject), payload=None, status="ready")
    insert_pending(clean_db, uuid.UUID(subject), payload=None, status="ready")
    insert_pending(clean_db, uuid.UUID(subject), payload=None, status="ready")
    headers = {"Authorization": f"Bearer {token}"}

    def attempt(index: int) -> object:
        if index == 0:
            return client.delete(f"{documents_url(subject)}/{first}", headers=headers)
        return client.post(
            documents_url(subject), files={"file": (f"n{index}.txt", TEXT)}, headers=headers
        )

    results = run_together(8, attempt)

    assert count(clean_db, "documents") <= 3
    accepted = sum(1 for r in results if getattr(r, "status_code", 0) == 202)
    assert accepted <= 1


@pytest.mark.parametrize("round_", range(3))
def test_the_connection_pool_is_not_exhausted_by_many_simultaneous_uploads(
    clean_db: str, round_: int
) -> None:
    client = app_for(clean_db)
    teacher_id, token = teacher_token(client, clean_db, f"t{round_}@example.com")
    subjects = [insert_subject(clean_db, teacher_id, f"S{i}") for i in range(40)]
    headers = {"Authorization": f"Bearer {token}"}

    results = run_together(
        40,
        lambda i: client.post(
            documents_url(subjects[i]), files={"file": ("n.txt", TEXT)}, headers=headers
        ),
    )

    assert statuses(results) == Counter({202: 40})
