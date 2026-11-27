"""Open risk: the aggregate does not look at what a student accepted (TD-072).

Characterisations against a real database: a **pass means that the condition is still open**, not
that anything is protected. The chat requires consent for the policy in force when a message is
written, so the history was written under earlier texts; the aggregate counts it anyway. The tests
say what the code processes, not what the law requires: which legal basis covers that history is for
the legal evaluation, and no consent rule changes without the owner's approval. Fictitious data
only; the switch is on for this test application only.
"""

import uuid
from collections.abc import Iterator

import pytest
from fastapi.testclient import TestClient

from app.models.user import UserRole
from tests.activity_support import Classroom, at
from tests.integration.helpers import MakeUser, TestUser, bearer, build_app, login_token
from tests.sql_support import run, scalar

WINDOW = {"start": "2026-03-02", "end": "2026-03-29"}
OLD_POLICY, NEW_POLICY = "old-version", "new-version"  # fictitious


@pytest.fixture
def enabled(clean_db: str) -> Iterator[TestClient]:
    app = build_app(clean_db, teacher_activity_enabled=True, privacy_policy_version=NEW_POLICY)
    with TestClient(app, raise_server_exceptions=False) as test_client:
        yield test_client


@pytest.fixture
def owner(make_user: MakeUser) -> TestUser:
    return make_user("owner-consent@example.com", UserRole.TEACHER)


def history(clean_db: str, owner: TestUser) -> Classroom:
    """Five students, one question and answer each, in an ended week."""
    room = Classroom(clean_db, students=5, teacher=uuid.UUID(owner.id))
    for student in room.students:
        room.turn(student, at("2026-03-03"))
    return room


def figures(client: TestClient, owner: TestUser, room: Classroom) -> tuple[int | None, int | None]:
    headers = bearer(login_token(client, owner.email, owner.password))
    response = client.get(
        f"/api/v1/subjects/{room.subject}/activity", params=WINDOW, headers=headers
    )
    assert response.status_code == 200, response.text
    body = response.json()
    return body["active_students"], body["questions"][0]["count"]


def accept(clean_db: str, room: Classroom, version: str, when: str) -> None:
    for student in room.students:
        run(
            clean_db,
            "UPDATE users SET consent_version = :version, consent_accepted_at = :accepted "
            "WHERE id = :id",
            version=version,
            accepted=at(when),
            id=student,
        )


def test_students_who_never_accept_the_new_policy_are_counted(
    enabled: TestClient, owner: TestUser, clean_db: str
) -> None:
    room = history(clean_db, owner)
    accept(clean_db, room, OLD_POLICY, "2026-02-02")

    accepted = scalar(
        clean_db, "SELECT count(*) FROM users WHERE consent_version = :v", v=NEW_POLICY
    )

    assert accepted == 0
    assert figures(enabled, owner, room) == (5, 5)


def test_activity_older_than_the_latest_acceptance_is_counted(
    enabled: TestClient, owner: TestUser, clean_db: str
) -> None:
    room = history(clean_db, owner)
    accept(clean_db, room, NEW_POLICY, "2026-04-15")

    assert figures(enabled, owner, room) == (5, 5)
