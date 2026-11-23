"""F8 end to end and the erasure invariant (change `activity-privacy-hardening`, tasks 1.5 and 2.3).

Runs only against the guarded test database (`TEST_DATABASE_URL`, name ending in `_test`) with the
fake LLM and the fake embedder: no Gemini call. Fictitious data only; the capability switch is on
**for this test application only**, never in a default.

What it shows: whether a teacher, using only the public API, can reach the state of the padding
vector (V2): register student accounts, enrol them by email, make them ask in the teacher's own
subject, and read the aggregate. **No mitigation exists, so the test records the confirmed state;
if a step is later blocked (for example by verified email) this test must be revisited, not
deleted.** Limits of the evidence: it does not show that real people have no identity control
outside the application (for example a real mail domain policy), and a single teacher account
inserted straight into the database stands for an existing teacher.
"""

import uuid
from datetime import date
from typing import Any

import pytest
from fastapi.testclient import TestClient

from app.models.user import UserRole
from app.rag.embedder import FakeEmbedder
from tests.integration.helpers import (
    DEFAULT_PASSWORD,
    MakeUser,
    TestUser,
    bearer,
    build_app,
    login_token,
)
from tests.sql_support import insert_chunk, insert_document, run, scalar

API = "/api/v1"
CONSENT_VERSION = "2026-10-v1"
QUESTION = "algebra equations"


@pytest.fixture
def api(clean_db: str):  # type: ignore[no-untyped-def]
    with TestClient(
        build_app(clean_db, teacher_activity_enabled=True), raise_server_exceptions=False
    ) as test_client:
        yield test_client


@pytest.fixture
def teacher(make_user: MakeUser) -> TestUser:
    return make_user("teacher-f8@example.com", UserRole.TEACHER)


def create_subject(api: TestClient, clean_db: str, teacher: TestUser) -> str:
    token = login_token(api, teacher.email, teacher.password)
    response = api.post(f"{API}/subjects", json={"name": "Fictitious F8"}, headers=bearer(token))
    assert response.status_code == 201, response.text
    subject_id = str(response.json()["id"])
    vector = FakeEmbedder().embed([QUESTION])[0]
    literal = "[" + ",".join(repr(v) for v in vector) + "]"
    document = insert_document(clean_db, uuid.UUID(subject_id), "notes.pdf", "ready")
    insert_chunk(
        clean_db,
        document,
        uuid.UUID(subject_id),
        chunk_index=0,
        embedding=literal,
        content=QUESTION,
        page_number=1,
    )
    return subject_id


def register(api: TestClient, email: str) -> str:
    """Step 1: public registration. Returns the token of the new account."""
    response = api.post(
        f"{API}/auth/register",
        json={"name": "Fictitious", "email": email, "password": DEFAULT_PASSWORD},
    )
    assert response.status_code == 201, response.text
    assert response.json()["role"] == "student"
    return login_token(api, email)


def enrol(api: TestClient, teacher_token: str, subject_id: str, email: str) -> None:
    """Step 2: the teacher enrols an account by its email."""
    response = api.post(
        f"{API}/subjects/{subject_id}/enrollments",
        json={"student_email": email},
        headers=bearer(teacher_token),
    )
    assert response.status_code == 201, response.text


def ask(api: TestClient, token: str, subject_id: str, times: int) -> None:
    """Step 3: the account accepts the consent and asks `times` questions in the subject."""
    consent = api.post(
        f"{API}/users/me/consent", json={"consent_version": CONSENT_VERSION}, headers=bearer(token)
    )
    assert consent.status_code == 200, consent.text
    for _ in range(times):
        response = api.post(
            f"{API}/chat",
            json={"subject_id": subject_id, "message": QUESTION},
            headers=bearer(token),
        )
        assert response.status_code == 200, response.text


def padded_class(
    api: TestClient, clean_db: str, teacher: TestUser, real_questions: int
) -> tuple[str, str, str]:
    """Four accounts the teacher controls (3 questions each) and one real student."""
    subject_id = create_subject(api, clean_db, teacher)
    teacher_token = login_token(api, teacher.email, teacher.password)
    for number in range(4):
        email = f"controlled-{number}@example.com"
        token = register(api, email)
        enrol(api, teacher_token, subject_id, email)
        ask(api, token, subject_id, 3)
    real_token = register(api, "real-student@example.com")
    enrol(api, teacher_token, subject_id, "real-student@example.com")
    ask(api, real_token, subject_id, real_questions)
    return subject_id, teacher_token, real_token


def current_week_cell(api: TestClient, token: str, subject_id: str) -> dict[str, Any]:
    response = api.get(f"{API}/subjects/{subject_id}/activity", headers=bearer(token))
    assert response.status_code == 200, response.text
    body: dict[str, Any] = response.json()
    return body


def test_f8_is_confirmed_end_to_end_a_teacher_recovers_one_real_students_questions(
    api: TestClient, clean_db: str, teacher: TestUser
) -> None:
    subject_id, teacher_token, _ = padded_class(api, clean_db, teacher, real_questions=2)

    body = current_week_cell(api, teacher_token, subject_id)

    shown = [row["count"] for row in body["questions"] if row["count"] is not None]
    assert body["active_students"] == 5
    assert shown == [14]
    assert shown[0] - 4 * 3 == 2  # the teacher subtracts what its own accounts asked


def test_f8_is_confirmed_end_to_end_the_absence_of_a_figure_reveals_no_activity(
    api: TestClient, clean_db: str, teacher: TestUser
) -> None:
    subject_id, teacher_token, real_token = padded_class(api, clean_db, teacher, real_questions=0)

    quiet = current_week_cell(api, teacher_token, subject_id)
    assert quiet["active_students"] is None
    assert all(row["count"] is None for row in quiet["questions"])

    ask_once = api.post(
        f"{API}/chat",
        json={"subject_id": subject_id, "message": QUESTION},
        headers=bearer(real_token),
    )
    assert ask_once.status_code == 200
    assert current_week_cell(api, teacher_token, subject_id)["active_students"] == 5


def test_a_students_deleted_conversations_leave_the_next_aggregate(
    api: TestClient, clean_db: str, teacher: TestUser
) -> None:
    """Erasure invariant (spec): deleting conversations lowers the next result."""
    subject_id, teacher_token, real_token = padded_class(api, clean_db, teacher, real_questions=2)
    assert current_week_cell(api, teacher_token, subject_id)["active_students"] == 5

    response = api.delete(f"{API}/users/me/conversations", headers=bearer(real_token))
    assert response.status_code == 204

    after = current_week_cell(api, teacher_token, subject_id)
    assert after["active_students"] is None  # four students remain: everything withheld


def test_a_deleted_account_leaves_the_next_aggregate_and_no_row_about_it(
    api: TestClient, clean_db: str, teacher: TestUser
) -> None:
    """Erasure invariant at database level: the application has no route that deletes an account,
    so the cascade of the foreign keys is exercised directly."""
    subject_id, teacher_token, _ = padded_class(api, clean_db, teacher, real_questions=2)
    real_id = scalar(
        clean_db, "SELECT id FROM users WHERE email = :email", email="real-student@example.com"
    )

    run(clean_db, "DELETE FROM users WHERE id = :id", id=real_id)

    after = current_week_cell(api, teacher_token, subject_id)
    assert after["enrolled_students"] == 4
    assert after["active_students"] is None
    for table, column in (("enrollments", "student_id"), ("conversations", "student_id")):
        count = scalar(clean_db, f"SELECT count(*) FROM {table} WHERE {column} = :id", id=real_id)  # noqa: S608
        assert count == 0, table


def test_the_week_of_the_figures_is_the_current_one(
    api: TestClient, clean_db: str, teacher: TestUser
) -> None:
    """Sanity of the scenario: the figures come from the window that ends today."""
    subject_id, teacher_token, _ = padded_class(api, clean_db, teacher, real_questions=1)

    body = current_week_cell(api, teacher_token, subject_id)

    assert body["window"]["end"] >= date.today().isoformat()
    assert scalar(clean_db, "SELECT count(*) FROM messages WHERE role = 'user'") == 4 * 3 + 1


# --- V1 and V3 against the real SQL and routes (task 2.2 evidence; no mitigation exists) ----------


def read_window(api: TestClient, token: str, subject: uuid.UUID, start: str, end: str) -> dict:  # type: ignore[type-arg]
    response = api.get(
        f"{API}/subjects/{subject}/activity",
        params={"start": start, "end": end},
        headers=bearer(token),
    )
    assert response.status_code == 200, response.text
    return response.json()  # type: ignore[no-any-return]


def first_week_cell(body: dict) -> int | None:  # type: ignore[type-arg]
    return body["questions"][0]["count"]  # type: ignore[no-any-return]


def test_v1_is_reproduced_with_the_real_routes_and_sql(
    api: TestClient, clean_db: str, teacher: TestUser
) -> None:
    from tests.activity_support import Classroom, at

    room = Classroom(clean_db, students=6, teacher=uuid.UUID(teacher.id))
    for student in room.students[:5]:
        room.turn(student, at("2026-03-03"))
        room.turn(student, at("2026-03-04"))
    for _ in range(3):
        room.turn(room.students[5], at("2026-03-05"))
    token = login_token(api, teacher.email, teacher.password)
    window = ("2026-03-02", "2026-03-29")

    before = read_window(api, token, room.subject, *window)
    removed = api.delete(
        f"{API}/subjects/{room.subject}/enrollments/{room.students[5]}", headers=bearer(token)
    )
    assert removed.status_code == 204
    after = read_window(api, token, room.subject, *window)

    assert (first_week_cell(before), before["active_students"]) == (13, 6)
    assert (first_week_cell(after), after["active_students"]) == (10, 5)
    assert first_week_cell(before) - first_week_cell(after) == 3  # type: ignore[operator]


def test_v3_is_reproduced_with_the_real_routes_and_sql(
    api: TestClient, clean_db: str, teacher: TestUser
) -> None:
    from datetime import timedelta

    from tests.activity_support import Classroom, at

    room = Classroom(clean_db, students=6, teacher=uuid.UUID(teacher.id))
    monday = date(2026, 3, 2)
    for index in range(13):
        day = (monday + timedelta(days=7 * index)).isoformat()
        for student in room.students[:5]:
            room.turn(student, at(day))
    room.turn(room.students[5], at("2026-03-02"), "none")  # the sixth student, week 1 only
    token = login_token(api, teacher.email, teacher.password)

    first = read_window(api, token, room.subject, "2026-03-02", "2026-05-24")
    second = read_window(api, token, room.subject, "2026-03-09", "2026-05-31")

    assert (first["active_students"], second["active_students"]) == (6, 5)
    assert first["no_material_rate"] == pytest.approx(1 / 61, abs=1e-3)
    assert second["no_material_rate"] == 0.0
