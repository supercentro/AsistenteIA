"""`GET /subjects/{id}/activity` against a real PostgreSQL database (tasks 1.1 to 1.5).

Fictitious data only. The capability is switched off by default, so the tests that read it build
the application with the setting on.
"""

import uuid
from collections.abc import Iterator
from datetime import UTC, datetime

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import text

from app.core.database import create_db_engine, create_session_factory
from app.models.user import UserRole
from app.repositories.activity_repository import ActivityRepository
from tests.activity_support import QUESTION, Classroom, at
from tests.integration.helpers import MakeUser, TestUser, bearer, build_app, login_token
from tests.sql_support import count, insert_enrollment, run, scalar

API = "/api/v1"
WEEKS = {"start": "2026-03-02", "end": "2026-03-29"}  # Monday to Sunday, four weeks
WEEK1, WEEK2, WEEK3, WEEK4 = ("2026-03-02", "2026-03-09", "2026-03-16", "2026-03-23")


@pytest.fixture
def enabled(clean_db: str) -> Iterator[TestClient]:
    with TestClient(
        build_app(clean_db, teacher_activity_enabled=True), raise_server_exceptions=False
    ) as test_client:
        yield test_client


@pytest.fixture
def owner(make_user: MakeUser) -> TestUser:
    return make_user("owner-act@example.com", UserRole.TEACHER)


@pytest.fixture
def room(clean_db: str, owner: TestUser) -> Classroom:
    return Classroom(clean_db, students=6, teacher=uuid.UUID(owner.id))


def ask(client: TestClient, user: TestUser, subject: uuid.UUID, **query: str):  # type: ignore[no-untyped-def]
    headers = bearer(login_token(client, user.email, user.password))
    return client.get(f"{API}/subjects/{subject}/activity", params=query or WEEKS, headers=headers)


def fill(room: Classroom) -> None:
    """Six students ask twice in weeks 1 and 2; five of them cite document A once in week 3."""
    for student in room.students:
        for day in ("2026-03-03", "2026-03-04"):
            room.turn(student, at(day), "cited")
        room.turn(student, at("2026-03-10"), "retrieved")
    for student in room.students[:5]:
        room.turn(student, at("2026-03-17"), "none")


# --- the owner reads --------------------------------------------------------------------------


def test_the_owner_reads_the_figures_of_the_window(
    enabled: TestClient, room: Classroom, owner: TestUser
) -> None:
    fill(room)

    response = ask(enabled, owner, room.subject)

    assert response.status_code == 200, response.text
    body = response.json()
    assert body["window"] == {
        "start": WEEK1,
        "end": "2026-03-29",
        "granularity": "week",
        "weeks": 4,
    }
    assert body["minimum_group"] == 5 and body["enrolled_students"] == 6
    assert body["active_students"] == 6
    assert [(p["period_start"], p["count"]) for p in body["questions"]] == [
        (WEEK1, 12), (WEEK2, 6), (WEEK3, 5), (WEEK4, None),
    ]  # fmt: skip
    # 23 answers: 12 cited, 6 retrieved only, 5 without material
    assert body["no_material_rate"] == pytest.approx(5 / 23, abs=0.001)
    assert body["no_cited_source_rate"] == pytest.approx(11 / 23, abs=0.001)
    documents = {d["filename"]: d for d in body["documents"]}
    assert documents["a.pdf"]["cited_appearances"] == 12
    assert documents["a.pdf"]["document_id"] == str(room.document_a)
    assert documents["b.pdf"]["cited_appearances"] is None  # nobody cited it: fewer than N


def test_a_subject_with_four_active_students_shows_only_the_enrolled_count(
    enabled: TestClient, room: Classroom, owner: TestUser
) -> None:
    for student in room.students[:4]:
        room.turn(student, at("2026-03-03"))

    body = ask(enabled, owner, room.subject).json()

    assert body["enrolled_students"] == 6 and body["active_students"] is None
    assert all(p["count"] is None for p in body["questions"])
    assert body["no_material_rate"] is None and body["suppressed"] is True


def test_only_conversations_of_the_subject_and_enrolled_students_are_counted(
    enabled: TestClient, room: Classroom, owner: TestUser, clean_db: str
) -> None:
    for student in room.students:
        room.turn(student, at("2026-03-03"))
    other_room = Classroom(clean_db, students=5, prefix="other", teacher=room.teacher)
    for student in other_room.students:
        other_room.turn(student, at("2026-03-03"))
    run(
        clean_db,
        "DELETE FROM enrollments WHERE student_id = :s AND subject_id = :j",
        s=room.students[0],
        j=room.subject,
    )

    body = ask(enabled, owner, room.subject).json()

    assert (
        body["enrolled_students"] == 5 and body["active_students"] == 5
    )  # the unenrolled one is out
    assert body["questions"][0]["count"] == 5


def test_the_window_is_half_open_in_utc(
    enabled: TestClient, room: Classroom, owner: TestUser
) -> None:
    for student in room.students:
        room.turn(student, at("2026-03-01", 23))  # Sunday before the window
        room.turn(student, at("2026-03-02", 0))  # first instant of the window
        room.turn(student, at("2026-03-29", 23))  # last day of the window
        room.turn(student, at("2026-03-30", 0))  # first instant after the window

    body = ask(enabled, owner, room.subject).json()

    assert body["questions"][0]["count"] == 6 and body["questions"][3]["count"] == 6


# --- authorisation (task 1.4) -----------------------------------------------------------------


def test_another_teacher_gets_the_same_answer_as_for_an_unknown_subject(
    enabled: TestClient, room: Classroom, make_user: MakeUser
) -> None:
    fill(room)
    stranger = make_user("stranger-act@example.com", UserRole.TEACHER)

    foreign = ask(enabled, stranger, room.subject)
    unknown = ask(enabled, stranger, uuid.uuid4())

    assert foreign.status_code == unknown.status_code == 404
    assert foreign.json() == unknown.json()


def test_a_student_is_refused_even_when_enrolled(
    enabled: TestClient, room: Classroom, make_user: MakeUser, clean_db: str
) -> None:
    student = make_user("student-act-login@example.com", UserRole.STUDENT)
    insert_enrollment(clean_db, room.subject, uuid.UUID(student.id))

    assert ask(enabled, student, room.subject).status_code == 403


def test_an_anonymous_caller_is_refused(enabled: TestClient, room: Classroom) -> None:
    response = enabled.get(f"{API}/subjects/{room.subject}/activity", params=WEEKS)

    assert response.status_code == 401


def test_the_capability_is_switched_off_by_default(
    client: TestClient, room: Classroom, owner: TestUser
) -> None:
    fill(room)

    response = ask(client, owner, room.subject)

    assert response.status_code == 404
    assert response.json()["code"] == "NOT_FOUND"


def test_switched_off_the_other_roles_still_get_their_own_refusal(
    client: TestClient, room: Classroom, make_user: MakeUser
) -> None:
    student = make_user("student-off@example.com", UserRole.STUDENT)

    assert ask(client, student, room.subject).status_code == 403
    assert client.get(f"{API}/subjects/{room.subject}/activity").status_code == 401


def test_the_aggregate_queries_take_the_teacher_and_join_the_subject_owner(
    room: Classroom, clean_db: str, make_user: MakeUser
) -> None:
    fill(room)
    stranger = uuid.UUID(make_user("stranger-repo@example.com", UserRole.TEACHER).id)
    engine = create_db_engine(clean_db)
    session = create_session_factory(engine)()
    try:
        repository = ActivityRepository(session)
        since, until = at("2026-03-02", 0), at("2026-03-30", 0)
        subject = uuid.UUID(str(room.subject))

        def read(teacher: uuid.UUID) -> tuple[int, int, int, int]:
            return (
                repository.enrolled_count(teacher_id=teacher, subject_id=subject),
                len(
                    repository.questions(
                        teacher_id=teacher, subject_id=subject, start=since, end=until
                    )
                ),
                len(
                    repository.answers(
                        teacher_id=teacher, subject_id=subject, start=since, end=until
                    )
                ),
                len(repository.current_documents(teacher_id=teacher, subject_id=subject)),
            )

        assert all(figure > 0 for figure in read(room.teacher))
        assert read(stranger) == (0, 0, 0, 0)
    finally:
        session.close()
        engine.dispose()


# --- window and parameters (task 1.3) ---------------------------------------------------------


@pytest.mark.parametrize(
    "query",
    [
        {"start": "2025-12-29", "end": "2026-03-29"},  # 13 weeks
        {"start": "2026-03-20", "end": "2026-03-02"},  # end before start
        {"start": "not-a-date", "end": "2026-03-29"},
        {"start": "2026-03-02", "end": "2026-03-29", "granularity": "day"},
        {"start": "2026-03-02", "end": "2026-03-29", "granularity": "hour"},
        {"start": "0001-01-01", "end": "9999-12-31"},
        {"end": "2026-03-29T10:00:00+02:00"},
    ],
    ids=["too-long", "reversed", "bad-date", "day", "hour", "calendar", "datetime"],
)
def test_an_invalid_window_or_granularity_is_a_422_never_a_500(
    enabled: TestClient, room: Classroom, owner: TestUser, query: dict[str, str]
) -> None:
    response = ask(enabled, owner, room.subject, **query)

    assert response.status_code == 422, response.text
    assert response.json()["code"] == "VALIDATION_ERROR"


def test_an_end_in_the_far_future_is_cut_at_the_last_ended_week_never_a_500(
    enabled: TestClient, room: Classroom, owner: TestUser
) -> None:
    """The open week and the future are never shown (A2b): the end is cut, not refused."""
    response = ask(enabled, owner, room.subject, end="9999-12-31")

    assert response.status_code == 200, response.text
    body = response.json()
    assert body["window"]["weeks"] == 12
    assert body["window"]["end"] < datetime.now(UTC).date().isoformat()


def test_a_malformed_subject_identifier_is_a_422(enabled: TestClient, owner: TestUser) -> None:
    headers = bearer(login_token(enabled, owner.email, owner.password))

    assert enabled.get(f"{API}/subjects/not-a-uuid/activity", headers=headers).status_code == 422


# --- shape, storage and erasure (tasks 1.3, 1.5) ----------------------------------------------


def test_the_raw_response_holds_no_text_email_or_student_identifier(
    enabled: TestClient, room: Classroom, owner: TestUser
) -> None:
    fill(room)

    raw = ask(enabled, owner, room.subject).text

    assert QUESTION not in raw and "Respuesta ficticia" not in raw
    assert "@" not in raw
    assert not any(str(student) in raw for student in room.students)


def test_the_call_stores_nothing(
    enabled: TestClient, room: Classroom, owner: TestUser, clean_db: str
) -> None:
    fill(room)

    def snapshot() -> dict[str, int]:
        tables = [
            str(row[0])
            for row in _rows(
                clean_db, "SELECT tablename FROM pg_tables WHERE schemaname = 'public'"
            )
        ]
        return {name: count(clean_db, name) for name in sorted(tables)}

    before = snapshot()
    assert ask(enabled, owner, room.subject).status_code == 200
    assert (
        ask(enabled, owner, room.subject, start="2026-03-02", end="2026-03-08").status_code == 200
    )

    assert snapshot() == before


def _rows(url: str, sql: str) -> list[tuple[object, ...]]:
    engine = create_db_engine(url)
    try:
        with engine.connect() as connection:
            return [tuple(row) for row in connection.execute(text(sql))]
    finally:
        engine.dispose()


def test_deleting_a_conversation_lowers_the_next_result(
    enabled: TestClient, room: Classroom, owner: TestUser, clean_db: str
) -> None:
    fill(room)
    before = ask(enabled, owner, room.subject).json()["questions"][0]["count"]

    run(clean_db, "DELETE FROM conversations WHERE id = :c", c=room.conversation(room.students[0]))
    after = ask(enabled, owner, room.subject).json()["questions"][0]["count"]

    assert before == 12 and after == 10


def test_deleting_every_conversation_of_a_student_lowers_the_active_count(
    enabled: TestClient, room: Classroom, owner: TestUser, clean_db: str
) -> None:
    for student in room.students[:5]:
        room.turn(student, at("2026-03-03"))
    assert ask(enabled, owner, room.subject).json()["active_students"] == 5

    run(clean_db, "DELETE FROM conversations WHERE student_id = :s", s=room.students[0])
    body = ask(enabled, owner, room.subject).json()

    assert body["active_students"] is None  # four are left: suppressed
    assert body["enrolled_students"] == 6


def test_unenrolling_a_student_lowers_the_next_result(
    enabled: TestClient, room: Classroom, owner: TestUser, clean_db: str
) -> None:
    for student in room.students:
        room.turn(student, at("2026-03-03"))
    assert ask(enabled, owner, room.subject).json()["questions"][0]["count"] == 6

    run(clean_db, "DELETE FROM enrollments WHERE student_id = :s", s=room.students[1])

    assert ask(enabled, owner, room.subject).json()["questions"][0]["count"] == 5
    assert (
        count(clean_db, "conversations", "student_id = :s", s=room.students[1]) == 1
    )  # nothing is erased by unenrolling


def test_a_deleted_document_is_no_longer_listed(
    enabled: TestClient, room: Classroom, owner: TestUser, clean_db: str
) -> None:
    for student in room.students:
        room.turn(student, at("2026-03-03"), "cited", "a")

    run(clean_db, "DELETE FROM documents WHERE id = :d", d=room.document_a)
    body = ask(enabled, owner, room.subject).json()

    assert [d["filename"] for d in body["documents"]] == ["b.pdf"]  # V7
    assert scalar(clean_db, "SELECT count(*) FROM documents WHERE id = :d", d=room.document_a) == 0
