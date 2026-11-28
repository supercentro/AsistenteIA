"""`GET /subjects/{id}/activity/topics` against a real PostgreSQL database.

Change `frequent-questions-and-topics`, tasks 3.2 and 3.3. Fictitious data only. The ranking takes
no window parameter, so the answers are dated relative to the last week that has ended.
"""

import uuid
from collections.abc import Iterator
from datetime import UTC, date, datetime, timedelta

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import text

from app.models.user import UserRole
from app.repositories.activity_repository import ActivityRepository
from app.services.activity_service import ended_weeks_today
from tests.activity_support import QUESTION, RETRIEVED_ANSWER, Classroom
from tests.integration.helpers import MakeUser, TestUser, bearer, build_app, login_token
from tests.sql_support import count, insert_document, run, scalar, unit_vector

API = "/api/v1"
ON = {"teacher_activity_enabled": True, "teacher_topics_enabled": True}


def ended_monday(weeks_ago: int = 0) -> date:
    """Monday of the last ended week, or of an earlier one."""
    today = ended_weeks_today(datetime.now(UTC))
    return today - timedelta(days=today.weekday()) - timedelta(weeks=1 + weeks_ago)


def in_week(weeks_ago: int = 0) -> datetime:
    day = ended_monday(weeks_ago) + timedelta(days=1)
    return datetime(day.year, day.month, day.day, 10, tzinfo=UTC)


class Course(Classroom):
    """A classroom whose documents have several pages and topics."""

    def pdf(self, name: str, pages: int = 6) -> tuple[uuid.UUID, dict[int, uuid.UUID]]:
        document = insert_document(self.url, self.subject, name, "ready")
        chunks = {page: uuid.uuid4() for page in range(1, pages + 1)}
        for page, chunk in chunks.items():
            run(
                self.url,
                "INSERT INTO document_chunks (id, document_id, subject_id, chunk_index, "
                "page_number, content, embedding) VALUES (:id, :d, :s, :i, :p, 'chunk text', "
                "CAST(:e AS vector))",
                id=chunk,
                d=document,
                s=self.subject,
                i=page - 1,
                p=page,
                e=unit_vector(page),
            )
        return document, chunks

    def answer(
        self, student: uuid.UUID, when: datetime, *chunks: uuid.UUID, cited: bool = True
    ) -> None:
        conversation = self.conversation(student)
        self._message(conversation, "user", QUESTION, when)
        marks = " ".join(f"[{n}]" for n in range(1, len(chunks) + 1))
        content = f"Respuesta ficticia {marks}" if cited else RETRIEVED_ANSWER
        message = self._message(conversation, "assistant", content, when)
        for rank, chunk in enumerate(chunks, start=1):
            run(
                self.url,
                "INSERT INTO message_sources (message_id, chunk_id, document_filename, "
                "page_number, rank, score) VALUES (:m, :c, 'x.pdf', 1, :r, 0.9)",
                m=message,
                c=chunk,
                r=rank,
            )


@pytest.fixture
def enabled(clean_db: str) -> Iterator[TestClient]:
    with TestClient(build_app(clean_db, **ON), raise_server_exceptions=False) as client:
        yield client


@pytest.fixture
def owner(make_user: MakeUser) -> TestUser:
    return make_user("owner-rank@example.com", UserRole.TEACHER)


@pytest.fixture
def course(clean_db: str, owner: TestUser) -> Course:
    return Course(clean_db, students=6, prefix="rank", teacher=uuid.UUID(owner.id))


def auth(client: TestClient, user: TestUser) -> dict[str, str]:
    return bearer(login_token(client, user.email, user.password))


def read(client: TestClient, user: TestUser, subject: uuid.UUID, **query: str):  # type: ignore[no-untyped-def]
    return client.get(
        f"{API}/subjects/{subject}/activity/topics", params=query, headers=auth(client, user)
    )


def define(
    client: TestClient,
    owner: TestUser,
    course: Course,
    document: uuid.UUID,
    revision: int,
    *ranges: tuple[str, int, int],
) -> None:
    response = client.put(
        f"{API}/subjects/{course.subject}/documents/{document}/topics",
        json={
            "revision": revision,
            "topics": [{"title": t, "start_page": a, "end_page": b} for t, a, b in ranges],
        },
        headers=auth(client, owner),
    )
    assert response.status_code == 200, response.text


def figures(body: dict) -> list[tuple[str, int]]:  # type: ignore[type-arg]
    return [(t["title"], t["answers"]) for t in body["topics"]]


# --- the owner reads --------------------------------------------------------------------------


def test_earlier_citations_count_for_the_first_definition(
    enabled: TestClient, course: Course, owner: TestUser
) -> None:
    document, chunks = course.pdf("unit.pdf")
    for student in course.students[:5]:
        course.answer(student, in_week(2), chunks[1], chunks[2])  # one topic, two pages
        course.answer(student, in_week(1), chunks[2], chunks[5])  # both topics
        course.answer(student, in_week(1), chunks[5], cited=False)

    define(enabled, owner, course, document, 0, ("Modelo", 1, 3), ("Formas", 4, 6))
    response = read(enabled, owner, course.subject)

    assert response.status_code == 200, response.text
    body = response.json()
    assert figures(body) == [("Modelo", 10), ("Formas", 5)]
    assert body["minimum_group"] == 5 and body["topics_defined"] == 2
    assert body["window"]["weeks"] == 12
    assert body["window"]["end"] == str(ended_monday() + timedelta(days=6))
    assert {d["filename"] for d in body["documents_without_topics"]} == {"a.pdf", "b.pdf"}


def test_no_field_identifies_a_student_or_holds_text(
    enabled: TestClient, course: Course, owner: TestUser
) -> None:
    document, chunks = course.pdf("unit.pdf")
    for student in course.students:
        course.answer(student, in_week(), chunks[1])
    define(enabled, owner, course, document, 0, ("Modelo", 1, 3))

    text = read(enabled, owner, course.subject).text

    for secret in [str(s) for s in course.students] + [QUESTION, "Respuesta ficticia", "student-"]:
        assert secret not in text


def test_reading_stores_nothing(enabled: TestClient, course: Course, owner: TestUser) -> None:
    document, _ = course.pdf("unit.pdf")
    define(enabled, owner, course, document, 0, ("Modelo", 1, 3))
    before = scalar(course.url, "SELECT revision FROM document_topic_sets")
    messages = count(course.url, "messages")

    read(enabled, owner, course.subject)

    assert scalar(course.url, "SELECT revision FROM document_topic_sets") == before
    assert count(course.url, "messages") == messages


def test_request_parameters_do_not_change_the_window(
    enabled: TestClient, course: Course, owner: TestUser
) -> None:
    plain = read(enabled, owner, course.subject).json()

    moved = read(
        enabled, owner, course.subject, start="2020-01-06", end="2020-01-12", granularity="day"
    )

    assert moved.status_code == 200 and moved.json() == plain


def test_another_subject_never_counts(
    enabled: TestClient, course: Course, owner: TestUser, clean_db: str
) -> None:
    other = Course(clean_db, students=6, prefix="other", teacher=course.teacher)
    document, _ = course.pdf("unit.pdf")
    foreign, foreign_chunks = other.pdf("unit.pdf")
    for student in other.students:
        other.answer(student, in_week(), foreign_chunks[1])
    for student in course.students:
        course.answer(student, in_week(), course.chunk_a)
    define(enabled, owner, course, document, 0, ("Modelo", 1, 3))

    assert read(enabled, owner, course.subject).json()["topics"] == []


def test_deleted_conversations_and_documents_stop_counting(
    enabled: TestClient, course: Course, owner: TestUser
) -> None:
    document, chunks = course.pdf("unit.pdf")
    for student in course.students:
        course.answer(student, in_week(), chunks[1])
    define(enabled, owner, course, document, 0, ("Modelo", 1, 3))
    assert figures(read(enabled, owner, course.subject).json()) == [("Modelo", 6)]

    run(course.url, "DELETE FROM conversations WHERE student_id = :s", s=course.students[0])
    assert figures(read(enabled, owner, course.subject).json()) == [("Modelo", 5)]

    run(course.url, "DELETE FROM documents WHERE id = :d", d=document)
    body = read(enabled, owner, course.subject).json()
    assert body["topics"] == [] and body["topics_defined"] == 0


# --- who may ----------------------------------------------------------------------------------


def test_only_the_owner_reads(
    enabled: TestClient, course: Course, owner: TestUser, make_user: MakeUser
) -> None:
    other = make_user("other-rank@example.com", UserRole.TEACHER)
    student = make_user("student-rank@example.com")
    path = f"{API}/subjects/{course.subject}/activity/topics"

    assert enabled.get(path).status_code == 401
    assert enabled.get(path, headers=auth(enabled, student)).status_code == 403
    foreign = read(enabled, other, course.subject)
    unknown = read(enabled, other, uuid.uuid4())
    assert foreign.status_code == unknown.status_code == 404 and foreign.json() == unknown.json()
    malformed = enabled.get(f"{API}/subjects/nope/activity/topics", headers=auth(enabled, owner))
    assert malformed.status_code == 404


@pytest.mark.parametrize(
    "settings",
    [{}, {"teacher_activity_enabled": True}, {"teacher_topics_enabled": True}],
)
def test_the_ranking_needs_both_switches(
    course: Course, owner: TestUser, make_user: MakeUser, settings: dict[str, object]
) -> None:
    student = make_user("student-rank-off@example.com")
    with TestClient(build_app(course.url, **settings), raise_server_exceptions=False) as client:
        assert read(client, owner, course.subject).status_code == 404
        assert read(client, student, course.subject).status_code == 403
        activity = client.get(
            f"{API}/subjects/{course.subject}/activity", headers=auth(client, owner)
        )
        expected = 200 if settings.get("teacher_activity_enabled") else 404
        assert activity.status_code == expected


# --- privacy ----------------------------------------------------------------------------------


def test_nothing_from_before_the_last_unenrolment_changes_the_ranking(
    enabled: TestClient, course: Course, owner: TestUser
) -> None:
    document, chunks = course.pdf("unit.pdf")
    define(enabled, owner, course, document, 0, ("Modelo", 1, 3))
    for student in course.students:
        course.answer(student, in_week(), chunks[1])
    run(
        course.url,
        "UPDATE subjects SET last_unenrolment_at = :at WHERE id = :s",
        at=in_week(1),
        s=course.subject,
    )
    baseline = read(enabled, owner, course.subject).json()
    assert figures(baseline) == [("Modelo", 6)]  # control: the later week is shown

    for student in course.students:
        course.answer(student, in_week(1), chunks[1])
        course.answer(student, in_week(3), chunks[2])

    assert read(enabled, owner, course.subject).json() == baseline


def test_changing_pages_cannot_isolate_the_answers_of_one_page(
    enabled: TestClient, course: Course, owner: TestUser
) -> None:
    """Pages 1-5 then 1-4 would reveal the answers that cite page 5 by subtraction."""
    document, chunks = course.pdf("unit.pdf")
    for student in course.students[:5]:
        course.answer(student, in_week(1), chunks[1])
    course.answer(course.students[5], in_week(1), chunks[5])  # one student, page 5
    define(enabled, owner, course, document, 0, ("Modelo", 1, 5))
    before = read(enabled, owner, course.subject).json()
    assert figures(before) == [("Modelo", 6)]  # control: all of them were visible together

    define(enabled, owner, course, document, 1, ("Modelo", 1, 4))
    after = read(enabled, owner, course.subject).json()

    assert after["topics"] == []
    assert [d["filename"] for d in after["restarted_documents"]] == ["unit.pdf"]


def test_clearing_and_defining_again_does_not_bring_earlier_answers_back(
    enabled: TestClient, course: Course, owner: TestUser
) -> None:
    document, chunks = course.pdf("unit.pdf")
    for student in course.students:
        course.answer(student, in_week(1), chunks[1])
    define(enabled, owner, course, document, 0, ("Modelo", 1, 5))
    define(enabled, owner, course, document, 1)
    define(enabled, owner, course, document, 2, ("Modelo", 1, 5))

    assert read(enabled, owner, course.subject).json()["topics"] == []


def test_a_rename_keeps_the_figure(enabled: TestClient, course: Course, owner: TestUser) -> None:
    document, chunks = course.pdf("unit.pdf")
    for student in course.students:
        course.answer(student, in_week(1), chunks[1])
    define(enabled, owner, course, document, 0, ("Modelo", 1, 5))
    define(enabled, owner, course, document, 1, ("Modelo relacional", 1, 5))

    assert figures(read(enabled, owner, course.subject).json()) == [("Modelo relacional", 6)]


# --- open risks, shown to exist (not accepted: see docs/technical-debt.md) --------------------


def test_open_risk_controlled_accounts_reveal_which_page_a_student_asked_about(
    enabled: TestClient, course: Course, owner: TestUser
) -> None:
    """F8 made finer (TD-071 family): four accounts of the teacher pad a one-page topic."""
    document, chunks = course.pdf("unit.pdf")
    define(enabled, owner, course, document, 0, ("Solo pagina 5", 5, 5))
    controlled = course.students[:4]
    real = course.students[4]
    for student in controlled:
        course.answer(student, in_week(), chunks[5])
    assert read(enabled, owner, course.subject).json()["topics"] == []

    course.answer(real, in_week(), chunks[5])

    assert figures(read(enabled, owner, course.subject).json()) == [("Solo pagina 5", 5)]


def test_open_risk_one_chosen_cut_bounds_the_answers_left_out(
    enabled: TestClient, course: Course, owner: TestUser
) -> None:
    """The single retroactive cut: the document figure minus the topic isolates one student."""
    document, chunks = course.pdf("unit.pdf")
    for student in course.students[:5]:
        course.answer(student, in_week(), chunks[1])
    course.answer(course.students[5], in_week(), chunks[6])
    define(enabled, owner, course, document, 0, ("Todo menos la ultima", 1, 5))

    ranked = read(enabled, owner, course.subject).json()
    activity = enabled.get(
        f"{API}/subjects/{course.subject}/activity", headers=auth(enabled, owner)
    ).json()
    document_figure = next(
        d["cited_appearances"] for d in activity["documents"] if d["filename"] == "unit.pdf"
    )

    assert document_figure - ranked["topics"][0]["answers"] == 1


def test_the_fifth_distinct_student_makes_a_topic_appear(
    enabled: TestClient, course: Course, owner: TestUser
) -> None:
    """Control of the minimum group with the same data: the fifth student makes a topic appear."""
    document, chunks = course.pdf("unit.pdf")
    define(enabled, owner, course, document, 0, ("Modelo", 1, 1))
    for student in course.students[:4]:
        for _ in range(5):
            course.answer(student, in_week(), chunks[1])
    course.answer(course.students[4], in_week(), chunks[2])  # active, other page
    assert read(enabled, owner, course.subject).json()["topics"] == []

    course.answer(course.students[4], in_week(), chunks[1])

    assert figures(read(enabled, owner, course.subject).json()) == [("Modelo", 21)]


def test_the_ranking_read_needs_one_pooled_connection_at_a_time(
    course: Course, owner: TestUser, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Lesson L52: with a pool of one the read must still complete and release it."""
    from sqlalchemy import create_engine as real

    def one_connection(url: object, **kwargs: object) -> object:
        return real(url, pool_size=1, max_overflow=0, pool_timeout=3, **kwargs)  # type: ignore[call-overload]

    monkeypatch.setattr("app.core.database.create_engine", one_connection)
    with TestClient(build_app(course.url, **ON), raise_server_exceptions=False) as small:
        headers = auth(small, owner)

        ranking = small.get(f"{API}/subjects/{course.subject}/activity/topics", headers=headers)
        again = small.get(f"{API}/subjects", headers=headers)  # the pool is free again

    assert ranking.status_code == 200, ranking.text
    assert again.status_code == 200, again.text


def test_the_ranking_is_read_in_a_read_only_repeatable_read_snapshot(
    enabled: TestClient, course: Course, owner: TestUser, monkeypatch: pytest.MonkeyPatch
) -> None:
    document, chunks = course.pdf("unit.pdf")
    define(enabled, owner, course, document, 0, ("Uno", 1, 3))
    for student in course.students[:5]:
        course.answer(student, in_week(), chunks[1])
    seen: list[tuple[str, str]] = []
    original = ActivityRepository.answers

    def look(self: ActivityRepository, **kwargs: object) -> object:
        session = self._session
        seen.append(
            (
                session.execute(text("SHOW transaction_isolation")).scalar_one(),
                session.execute(text("SHOW transaction_read_only")).scalar_one(),
            )
        )
        return original(self, **kwargs)  # type: ignore[arg-type]

    monkeypatch.setattr(ActivityRepository, "answers", look)

    response = read(enabled, owner, course.subject)

    assert response.status_code == 200, response.text
    assert seen == [("repeatable read", "on")]


def test_a_document_that_is_not_ready_is_not_listed(
    enabled: TestClient, course: Course, owner: TestUser
) -> None:
    course.pdf("ready.pdf")
    insert_document(course.url, course.subject, "waiting.pdf", "pending")

    body = read(enabled, owner, course.subject).json()

    names = [d["filename"] for d in body["documents_without_topics"]]
    assert "ready.pdf" in names
    assert "waiting.pdf" not in names
