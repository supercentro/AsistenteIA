"""The marker of the last unenrolment (change `activity-privacy-hardening`, A2), on a real database.

Fictitious data only; the capability switch is on for the test application only. What is shown:

* the removal writes the marker, once, in the same unit as the deletion, before it (the order
  that cannot deadlock with the deletion of a subject), and a removal that deletes nothing writes
  nothing;
* the marker never moves for anything else, never decreases and names no student;
* every message of the removed student precedes it, whichever of a chat turn and the removal wins;
* the activity read is one snapshot, so a removal that commits in the middle of a read cannot pair
  the old marker with the new cohort (the control without the snapshot does).
"""

import time
import uuid
from collections.abc import Iterator
from concurrent.futures import Future, ThreadPoolExecutor
from datetime import date, datetime
from typing import Any

import pytest
from fastapi import Request
from fastapi.testclient import TestClient
from sqlalchemy import event, text
from sqlalchemy.engine import Engine
from sqlalchemy.exc import DBAPIError
from sqlalchemy.sql.dml import Delete

from app.api.deps import get_activity_db
from app.core.database import create_db_engine, create_session_factory
from app.models.user import UserRole
from app.repositories.activity_repository import ActivityRepository
from app.repositories.enrollment_repository import EnrollmentRepository
from app.repositories.subject_repository import SubjectRepository
from app.services.activity_service import ActivityService
from tests.activity_support import Classroom, at
from tests.integration.helpers import MakeUser, TestUser, bearer, build_app, login_token
from tests.integration.test_chat_enrollment_lock import (  # noqa: F401 - the autouse fixture
    OtherTransaction,
    _release_other_transactions,
    wait_for_a_waiter,
)
from tests.sql_support import count, insert_enrollment, run, scalar

API = "/api/v1"
WINDOW = {"start": "2026-03-02", "end": "2026-03-29"}


@pytest.fixture
def api(clean_db: str) -> Iterator[TestClient]:
    with TestClient(
        build_app(clean_db, teacher_activity_enabled=True), raise_server_exceptions=False
    ) as test_client:
        yield test_client


@pytest.fixture
def teacher(make_user: MakeUser) -> TestUser:
    return make_user("teacher-marker@example.com", UserRole.TEACHER)


@pytest.fixture
def room(clean_db: str, teacher: TestUser) -> Classroom:
    return Classroom(clean_db, students=6, teacher=uuid.UUID(teacher.id))


def marker(url: str, subject: uuid.UUID) -> datetime | None:
    value = scalar(url, "SELECT last_unenrolment_at FROM subjects WHERE id = :id", id=subject)
    assert value is None or isinstance(value, datetime)
    return value


def database_now(url: str) -> datetime:
    value = scalar(url, "SELECT clock_timestamp()")
    assert isinstance(value, datetime)
    return value


def remove(api: TestClient, teacher: TestUser, room: Classroom, student: uuid.UUID) -> Any:
    token = login_token(api, teacher.email, teacher.password)
    return api.delete(f"{API}/subjects/{room.subject}/enrollments/{student}", headers=bearer(token))


# --- what the removal writes ----------------------------------------------------------------------


def test_a_new_subject_has_no_marker(clean_db: str, room: Classroom) -> None:
    assert marker(clean_db, room.subject) is None


def test_a_removal_sets_the_marker_to_the_database_clock_for_an_inactive_student_too(
    api: TestClient, clean_db: str, teacher: TestUser, room: Classroom
) -> None:
    room.turn(room.students[0], at("2026-03-03"))  # one student is active, the removed one is not
    before = database_now(clean_db)

    assert remove(api, teacher, room, room.students[5]).status_code == 204

    after = database_now(clean_db)
    stored = marker(clean_db, room.subject)
    assert stored is not None and before <= stored <= after


def test_the_marker_never_decreases_over_several_removals(
    api: TestClient, clean_db: str, teacher: TestUser, room: Classroom
) -> None:
    seen: list[datetime] = []
    for student in room.students[:3]:
        assert remove(api, teacher, room, student).status_code == 204
        value = marker(clean_db, room.subject)
        assert value is not None
        seen.append(value)

    assert seen == sorted(seen) and len(set(seen)) == 3


def test_a_removal_of_a_student_who_is_not_enrolled_is_a_404_and_writes_nothing(
    api: TestClient, clean_db: str, teacher: TestUser, room: Classroom
) -> None:
    assert remove(api, teacher, room, room.students[0]).status_code == 204
    first = marker(clean_db, room.subject)

    again = remove(api, teacher, room, room.students[0])

    assert again.status_code == 404
    assert marker(clean_db, room.subject) == first  # not moved by the failed attempt


def test_a_removal_that_deletes_nothing_in_a_new_subject_leaves_the_marker_null(
    api: TestClient, clean_db: str, teacher: TestUser, room: Classroom
) -> None:
    assert remove(api, teacher, room, uuid.uuid4()).status_code == 404
    assert marker(clean_db, room.subject) is None


def test_another_teachers_removal_does_not_touch_the_subject(
    api: TestClient, clean_db: str, make_user: MakeUser, room: Classroom
) -> None:
    stranger = make_user("stranger-marker@example.com", UserRole.TEACHER)

    response = remove(api, stranger, room, room.students[0])

    assert response.status_code == 404
    assert marker(clean_db, room.subject) is None
    assert count(clean_db, "enrollments") == 6


# --- what does not move it ------------------------------------------------------------------------


def test_nothing_but_a_removal_moves_the_marker(
    api: TestClient, clean_db: str, teacher: TestUser, room: Classroom
) -> None:
    assert remove(api, teacher, room, room.students[5]).status_code == 204
    fixed = marker(clean_db, room.subject)
    token = login_token(api, teacher.email, teacher.password)

    room.turn(room.students[0], at("2026-03-03"))
    enrol = api.post(
        f"{API}/subjects/{room.subject}/enrollments",
        json={"student_email": "student-act-5@example.com"},  # the removed student, enrolled again
        headers=bearer(token),
    )
    read = api.get(f"{API}/subjects/{room.subject}/activity", headers=bearer(token))
    run(clean_db, "DELETE FROM conversations WHERE student_id = :id", id=room.students[0])
    run(clean_db, "DELETE FROM users WHERE id = :id", id=room.students[1])  # an account deleted

    assert enrol.status_code == 201 and read.status_code == 200
    assert marker(clean_db, room.subject) == fixed


def test_the_marker_names_no_student(clean_db: str) -> None:
    columns = scalar(
        clean_db,
        "SELECT count(*) FROM information_schema.columns WHERE table_name = 'subjects' "
        "AND column_name LIKE '%student%'",
    )
    assert columns == 0


# --- the order of the writes ----------------------------------------------------------------------


def statements_of(function: Any) -> list[str]:
    seen: list[str] = []

    def record(conn: Any, cursor: Any, statement: str, *rest: Any) -> None:
        if (
            "pg_advisory_xact_lock" in statement
            or "UPDATE subjects" in statement
            or "DELETE FROM enrollments" in statement
        ):
            seen.append(statement.split("\n", 1)[0][:60])

    event.listen(Engine, "before_cursor_execute", record)
    try:
        function()
    finally:
        event.remove(Engine, "before_cursor_execute", record)
    return seen


def test_the_removal_takes_the_advisory_lock_then_the_subject_then_the_enrolment(
    api: TestClient, teacher: TestUser, room: Classroom
) -> None:
    seen = statements_of(lambda: remove(api, teacher, room, room.students[0]))

    assert [s.split(" ")[0] for s in seen] == ["SELECT", "UPDATE", "DELETE"]
    assert "pg_advisory_xact_lock" in seen[0] and "subjects" in seen[1] and "enrollments" in seen[2]


def test_a_failure_after_the_marker_undoes_it_with_the_savepoint(
    clean_db: str, room: Classroom, monkeypatch: pytest.MonkeyPatch
) -> None:
    engine = create_db_engine(clean_db)
    session = create_session_factory(engine)()
    try:
        original = session.execute

        def failing(statement: Any, *args: Any, **kwargs: Any) -> Any:
            if isinstance(statement, Delete):
                raise RuntimeError("the deletion fails")
            return original(statement, *args, **kwargs)

        monkeypatch.setattr(session, "execute", failing)
        repository = EnrollmentRepository(session)
        with pytest.raises(RuntimeError):
            repository.delete_for_teacher_subject(room.subject, room.teacher, room.students[0])
        monkeypatch.undo()
        session.commit()  # whatever the caller does with the transaction
    finally:
        session.close()
        engine.dispose()

    assert marker(clean_db, room.subject) is None
    assert count(clean_db, "enrollments") == 6


def test_a_removal_that_deletes_nothing_is_undone_even_if_the_caller_commits(
    clean_db: str, room: Classroom
) -> None:
    """The savepoint does not rely on the request handler rolling the 404 back."""
    engine = create_db_engine(clean_db)
    session = create_session_factory(engine)()
    try:
        deleted = EnrollmentRepository(session).delete_for_teacher_subject(
            room.subject,
            room.teacher,
            uuid.uuid4(),  # nobody enrolled with this id
        )
        session.commit()  # a caller that commits whatever happened
    finally:
        session.close()
        engine.dispose()

    assert deleted is False
    assert marker(clean_db, room.subject) is None and count(clean_db, "enrollments") == 6


def test_the_marker_is_later_than_a_turn_that_commits_after_the_removal_began(
    clean_db: str, room: Classroom
) -> None:
    """`clock_timestamp()` and not `now()`: the removal's transaction began before the turn did."""
    student = room.students[0]
    engine = create_db_engine(clean_db)
    session = create_session_factory(engine)()
    try:
        session.execute(text("SELECT 1"))  # the removal's transaction begins: its now() is fixed
        time.sleep(0.2)
        turn = OtherTransaction(clean_db)  # a chat turn that begins later and commits first
        turn.lock(str(student), str(room.subject))
        conversation = uuid.uuid4()
        turn.execute(
            "INSERT INTO conversations (id, student_id, subject_id) VALUES (:c, :s, :j)",
            c=conversation,
            s=student,
            j=room.subject,
        )
        turn.execute(
            "INSERT INTO messages (id, conversation_id, role, content) "
            "VALUES (:m, :c, 'user', 'Pregunta ficticia')",
            m=uuid.uuid4(),
            c=conversation,
        )
        turn.commit()
        deleted = EnrollmentRepository(session).delete_for_teacher_subject(
            room.subject, room.teacher, student
        )
        session.commit()
    finally:
        session.close()
        engine.dispose()

    stored = marker(clean_db, room.subject)
    newest = scalar(clean_db, "SELECT max(created_at) FROM messages")
    assert deleted is True
    assert stored is not None and isinstance(newest, datetime) and newest < stored


def test_a_rolled_back_transaction_leaves_neither_the_deletion_nor_the_marker(
    clean_db: str, room: Classroom
) -> None:
    engine = create_db_engine(clean_db)
    session = create_session_factory(engine)()
    try:
        deleted = EnrollmentRepository(session).delete_for_teacher_subject(
            room.subject, room.teacher, room.students[0]
        )
        session.rollback()
    finally:
        session.close()
        engine.dispose()

    assert deleted is True
    assert marker(clean_db, room.subject) is None and count(clean_db, "enrollments") == 6


# --- concurrency ----------------------------------------------------------------------------------


def in_thread(function: Any) -> tuple[ThreadPoolExecutor, Future[Any]]:
    pool = ThreadPoolExecutor(max_workers=1)
    return pool, pool.submit(function)


def wait_for_a_row_waiter(url: str, timeout: float = 15.0) -> None:
    """Some transaction waits for the row lock of another one."""
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        waiting = scalar(
            url, "SELECT count(*) FROM pg_locks WHERE locktype = 'transactionid' AND NOT granted"
        )
        if isinstance(waiting, int) and waiting >= 1:
            return
        time.sleep(0.02)
    raise AssertionError("no transaction is waiting for a row lock")


def test_a_turn_in_flight_always_precedes_the_marker(
    api: TestClient, clean_db: str, teacher: TestUser, room: Classroom
) -> None:
    student = room.students[0]
    in_flight = OtherTransaction(clean_db)
    in_flight.lock(str(student), str(room.subject))  # a chat turn that holds the lock...
    conversation = uuid.uuid4()
    in_flight.execute(
        "INSERT INTO conversations (id, student_id, subject_id) VALUES (:c, :s, :j)",
        c=conversation,
        s=student,
        j=room.subject,
    )
    in_flight.execute(
        "INSERT INTO messages (id, conversation_id, role, content) "
        "VALUES (:m, :c, 'user', 'Pregunta ficticia')",
        m=uuid.uuid4(),
        c=conversation,
    )

    pool, removal = in_thread(lambda: remove(api, teacher, room, student))
    try:
        wait_for_a_waiter(clean_db)
        assert not removal.done() and marker(clean_db, room.subject) is None
        in_flight.commit()
        assert removal.result(timeout=15).status_code == 204
    finally:
        in_flight.close()
        pool.shutdown(wait=True)

    stored = marker(clean_db, room.subject)
    newest = scalar(clean_db, "SELECT max(created_at) FROM messages")
    assert stored is not None and isinstance(newest, datetime) and newest < stored


def test_a_removal_that_wins_leaves_no_message_dated_after_the_marker(
    api: TestClient, clean_db: str, teacher: TestUser, room: Classroom
) -> None:
    student = room.students[0]
    room.turn(student, at("2026-03-03"))

    assert remove(api, teacher, room, student).status_code == 204

    stored = marker(clean_db, room.subject)
    assert stored is not None
    late = scalar(clean_db, "SELECT count(*) FROM messages WHERE created_at >= :m", m=stored)
    assert late == 0  # the removed student cannot ask again (the turn is refused: M2)


def test_two_removals_wait_for_each_other_and_the_later_marker_wins(
    api: TestClient, clean_db: str, teacher: TestUser, room: Classroom
) -> None:
    holder = OtherTransaction(clean_db)  # a removal in flight: it holds the row of the subject
    holder.execute(
        "UPDATE subjects SET last_unenrolment_at = greatest(last_unenrolment_at, "
        "clock_timestamp()) WHERE id = :id",
        id=room.subject,
    )
    pool, second = in_thread(lambda: remove(api, teacher, room, room.students[1]))
    try:
        wait_for_a_row_waiter(clean_db)
        assert not second.done()
        holder.commit()
        assert second.result(timeout=15).status_code == 204
    finally:
        holder.close()
        pool.shutdown(wait=True)

    stored = marker(clean_db, room.subject)
    assert stored is not None and count(clean_db, "enrollments") == 5


def test_a_removal_and_a_document_upload_do_not_deadlock(
    api: TestClient, clean_db: str, teacher: TestUser, room: Classroom
) -> None:
    upload = OtherTransaction(clean_db)  # the upload locks the row of the subject first
    upload.execute("SELECT id FROM subjects WHERE id = :id FOR UPDATE", id=room.subject)
    pool, removal = in_thread(lambda: remove(api, teacher, room, room.students[2]))
    try:
        wait_for_a_row_waiter(clean_db)
        assert not removal.done()
        upload.commit()
        assert removal.result(timeout=15).status_code == 204
    finally:
        upload.close()
        pool.shutdown(wait=True)


def run_subject_deletion_against(old_order: bool, url: str, room: Classroom) -> str | None:
    """A removal and the deletion of the subject, both started; returns the deadlock text, if any.

    `old_order` deletes the enrolment first and marks the subject second (the first draft);
    otherwise the subject is marked first (the implemented order).
    """
    removal = OtherTransaction(url)
    deletion = OtherTransaction(url)
    mark = (
        "UPDATE subjects SET last_unenrolment_at = clock_timestamp() WHERE id = :id",
        {"id": room.subject},
    )
    drop = (
        "DELETE FROM enrollments WHERE subject_id = :j AND student_id = :s",
        {"j": room.subject, "s": room.students[0]},
    )
    first, second = (drop, mark) if old_order else (mark, drop)
    errors: list[str] = []

    def delete_subject() -> None:
        try:
            deletion.execute("DELETE FROM subjects WHERE id = :id", id=room.subject)
            deletion.commit()
        except DBAPIError as error:
            errors.append(str(error.orig))

    pool = ThreadPoolExecutor(max_workers=1)
    try:
        removal.execute(first[0], **first[1])
        started = pool.submit(delete_subject)
        wait_for_a_row_waiter(url)
        try:
            removal.execute(second[0], **second[1])
            removal.commit()
        except DBAPIError as error:
            errors.append(str(error.orig))
        started.result(timeout=20)
    finally:
        removal.close()
        deletion.close()
        pool.shutdown(wait=True)
    return errors[0] if errors else None


def test_the_first_draft_order_deadlocks_with_the_deletion_of_a_subject(
    clean_db: str, room: Classroom
) -> None:
    """Control: enrolment first, subject second, against `DELETE FROM subjects` (a cascade)."""
    found = run_subject_deletion_against(True, clean_db, room)

    assert found is not None and "deadlock" in found


def test_the_implemented_order_does_not_deadlock_with_the_deletion_of_a_subject(
    clean_db: str, room: Classroom
) -> None:
    assert run_subject_deletion_against(False, clean_db, room) is None
    assert count(clean_db, "subjects") == 0  # the deletion went through after the removal


# --- the read is one snapshot ---------------------------------------------------------------------


class RemovingRepository(ActivityRepository):
    """Commits a removal from another session just after the read loaded the subject."""

    def __init__(self, session: Any, removal: Any) -> None:
        super().__init__(session)
        self._removal = removal
        self._done = False

    def enrolled_count(self, **scope: Any) -> int:
        if not self._done:
            self._done = True
            self._removal()
        return super().enrolled_count(**scope)


def concurrent_read(clean_db: str, room: Classroom, *, snapshot: bool) -> Any:
    def removal() -> None:
        engine = create_db_engine(clean_db)
        session = create_session_factory(engine)()
        try:
            EnrollmentRepository(session).delete_for_teacher_subject(
                room.subject, room.teacher, room.students[5]
            )
            session.commit()
        finally:
            session.close()
            engine.dispose()

    engine = create_db_engine(clean_db)
    session = create_session_factory(engine)()
    try:
        if snapshot:  # what the dependency `get_activity_db` does before the first statement
            session.connection(
                execution_options={
                    "isolation_level": "REPEATABLE READ",
                    "postgresql_readonly": True,
                }
            )
        service = ActivityService(SubjectRepository(session), RemovingRepository(session, removal))
        return service.get(
            room.teacher,
            room.subject,
            start=date(2026, 3, 2),
            end=date(2026, 3, 29),
        )
    finally:
        session.rollback()
        session.close()
        engine.dispose()


def fill(room: Classroom) -> None:
    for student in room.students[:5]:
        room.turn(student, at("2026-03-03"))
        room.turn(student, at("2026-03-04"))
    for _ in range(3):
        room.turn(room.students[5], at("2026-03-05"))


def test_a_read_that_overlaps_a_removal_returns_the_answer_of_the_instant_it_started(
    clean_db: str, room: Classroom
) -> None:
    fill(room)

    result = concurrent_read(clean_db, room, snapshot=True)

    assert result.window.weeks == 4 and result.enrolled_students == 6
    assert (result.questions[0].count, result.active_students) == (13, 6)  # the whole pre-removal
    assert marker(clean_db, room.subject) is not None  # and the removal did commit


def test_without_the_snapshot_the_same_read_mixes_the_old_marker_with_the_new_cohort(
    clean_db: str, room: Classroom
) -> None:
    """Control: the combination the snapshot rules out (weeks shown, the student gone)."""
    fill(room)

    result = concurrent_read(clean_db, room, snapshot=False)

    assert result.window.weeks == 4  # the old marker: no week hidden
    assert (result.questions[0].count, result.enrolled_students) == (10, 5)  # the new cohort


def test_the_activity_read_needs_one_pooled_connection_at_a_time(
    clean_db: str, teacher: TestUser, room: Classroom, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Review finding M-1: with a pool of one, the read must still complete.

    The shared session of the request only authenticates; if it kept its connection while the
    snapshot took another one, a burst of reads would take the whole pool and block every route.
    """
    from sqlalchemy import create_engine as real

    def one_connection(url: Any, **kwargs: Any) -> Any:
        return real(url, pool_size=1, max_overflow=0, pool_timeout=3, **kwargs)

    monkeypatch.setattr("app.core.database.create_engine", one_connection)
    with TestClient(
        build_app(clean_db, teacher_activity_enabled=True), raise_server_exceptions=False
    ) as small:
        token = login_token(small, teacher.email, teacher.password)

        read = small.get(f"{API}/subjects/{room.subject}/activity", headers=bearer(token))
        again = small.get(f"{API}/subjects", headers=bearer(token))  # the pool is free again

    assert read.status_code == 200, read.text
    assert again.status_code == 200, again.text


def test_the_activity_dependency_opens_a_read_only_repeatable_read_session(
    clean_db: str,
) -> None:
    engine = create_db_engine(clean_db)
    application = type("App", (), {})()
    application.state = type("State", (), {})()
    application.state.session_factory = create_session_factory(engine)
    request = Request({"type": "http", "app": application, "headers": []})
    shared = create_session_factory(engine)()  # the session of the request that authenticated
    shared.execute(text("SELECT 1"))
    teacher = object()  # already authenticated: only the order matters
    generator: Any = get_activity_db(request, teacher, shared)  # type: ignore[arg-type]
    session = next(generator)
    try:
        level = session.execute(text("SHOW transaction_isolation")).scalar_one()
        read_only = session.execute(text("SHOW transaction_read_only")).scalar_one()
        released = shared.in_transaction()  # the shared session gave its connection back
    finally:
        generator.close()
        engine.dispose()

    assert released is False

    assert (level, read_only) == ("repeatable read", "on")


# --- exposure -------------------------------------------------------------------------------------


def test_no_response_about_a_subject_carries_the_marker(
    api: TestClient, clean_db: str, teacher: TestUser, room: Classroom, make_user: MakeUser
) -> None:
    assert remove(api, teacher, room, room.students[5]).status_code == 204
    token = login_token(api, teacher.email, teacher.password)
    student = make_user("student-marker@example.com", UserRole.STUDENT)
    insert_enrollment(clean_db, room.subject, uuid.UUID(student.id))

    listed = api.get(f"{API}/subjects", headers=bearer(token))
    single = api.get(f"{API}/subjects/{room.subject}", headers=bearer(token))
    student_token = login_token(api, student.email, student.password)
    seen_by_student = api.get(f"{API}/subjects", headers=bearer(student_token))

    for response in (listed, single, seen_by_student):
        assert response.status_code == 200, response.text
        assert "last_unenrolment" not in response.text
