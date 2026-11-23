"""The teacher activity route over real HTTP against Uvicorn with the production arguments.

Task 3.3 of `activity-events-and-metrics`: a teacher, another teacher, a student and an anonymous
caller, with fictitious data, once with the capability on and once with the default (off). Gemini
is never called: the route reads the database only.
"""

import sys
import uuid
from collections.abc import Iterator

import pytest

from app.models.user import UserRole
from tests.activity_support import QUESTION, Classroom, at
from tests.integration.helpers import insert_enrollment, insert_user
from tests.server_support import Server, login, request, running_server

pytestmark = pytest.mark.skipif(sys.platform != "linux", reason="runs in the Linux container")
WINDOW = "?start=2026-03-02&end=2026-03-29"


@pytest.fixture(scope="module")
def on(migrated_db: str) -> Iterator[Server]:
    with running_server(migrated_db, TEACHER_ACTIVITY_ENABLED="true") as server:
        yield server


@pytest.fixture(scope="module")
def default(migrated_db: str) -> Iterator[Server]:
    with running_server(migrated_db) as server:  # no setting: the production default
        yield server


@pytest.fixture
def room(clean_db: str) -> tuple[Classroom, str, str, str]:
    teacher = insert_user(clean_db, f"owner-{uuid.uuid4().hex[:8]}@example.com", UserRole.TEACHER)
    room = Classroom(clean_db, students=6, teacher=uuid.UUID(teacher.id))
    for student in room.students:
        room.turn(student, at("2026-03-03"), "cited")
    stranger = insert_user(clean_db, f"other-{uuid.uuid4().hex[:8]}@example.com", UserRole.TEACHER)
    pupil = insert_user(clean_db, f"pupil-{uuid.uuid4().hex[:8]}@example.com", UserRole.STUDENT)
    insert_enrollment(clean_db, str(room.subject), pupil.id)
    return room, teacher.email, stranger.email, pupil.email


def test_the_owner_reads_the_figures_over_real_http(
    on: Server, room: tuple[Classroom, str, str, str]
) -> None:
    classroom, owner, _, _ = room

    reply = request(
        on, "GET", f"/api/v1/subjects/{classroom.subject}/activity{WINDOW}", login(on, owner)
    )

    assert reply.status == 200, reply.body
    body = reply.json()
    assert isinstance(body, dict)
    assert body["active_students"] == 6 and body["questions"][0]["count"] == 6
    assert QUESTION.encode() not in reply.body and b"@" not in reply.body


def test_other_teacher_student_and_anonymous_are_refused_over_real_http(
    on: Server, room: tuple[Classroom, str, str, str]
) -> None:
    classroom, _, stranger, pupil = room
    path = f"/api/v1/subjects/{classroom.subject}/activity{WINDOW}"
    unknown = f"/api/v1/subjects/{uuid.uuid4()}/activity{WINDOW}"

    foreign = request(on, "GET", path, login(on, stranger))
    missing = request(on, "GET", unknown, login(on, stranger))

    assert foreign.status == missing.status == 404
    assert foreign.json() == missing.json()
    assert request(on, "GET", path, login(on, pupil)).status == 403
    assert request(on, "GET", path).status == 401


def test_an_invalid_window_is_a_422_over_real_http(
    on: Server, room: tuple[Classroom, str, str, str]
) -> None:
    classroom, owner, _, _ = room
    token = login(on, owner)
    base = f"/api/v1/subjects/{classroom.subject}/activity"

    assert request(on, "GET", f"{base}?start=2025-12-29&end=2026-03-29", token).status == 422
    assert request(on, "GET", f"{base}{WINDOW}&granularity=day", token).status == 422
    assert request(on, "GET", f"{base}?start=0001-01-01&end=9999-12-31", token).status == 422


def test_the_production_default_is_switched_off_over_real_http(
    default: Server, room: tuple[Classroom, str, str, str]
) -> None:
    classroom, owner, _, pupil = room
    path = f"/api/v1/subjects/{classroom.subject}/activity{WINDOW}"

    assert request(default, "GET", path, login(default, owner)).status == 404
    assert request(default, "GET", path, login(default, pupil)).status == 403
    assert request(default, "GET", path).status == 401
