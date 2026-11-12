import json
import logging
import uuid
from concurrent.futures import ThreadPoolExecutor

import pytest
from fastapi.testclient import TestClient
from httpx2 import Response
from sqlalchemy import event, text
from sqlalchemy.orm import Session

from app.models.user import UserRole
from tests.integration.helpers import (
    MakeUser,
    TestUser,
    bearer,
    insert_enrollment,
    insert_subject,
    login_token,
)

SUBJECTS = "/api/v1/subjects"


def enrollments_url(subject_id: str) -> str:
    return f"{SUBJECTS}/{subject_id}/enrollments"


@pytest.fixture
def teacher(make_user: MakeUser) -> TestUser:
    return make_user("teacher@example.com", UserRole.TEACHER)


@pytest.fixture
def other_teacher(make_user: MakeUser) -> TestUser:
    return make_user("other.teacher@example.com", UserRole.TEACHER)


@pytest.fixture
def student(make_user: MakeUser) -> TestUser:
    return make_user("student@example.com", UserRole.STUDENT)


@pytest.fixture
def other_student(make_user: MakeUser) -> TestUser:
    return make_user("other.student@example.com", UserRole.STUDENT)


@pytest.fixture
def subject_id(clean_db: str, teacher: TestUser) -> str:
    return insert_subject(clean_db, teacher.id, "Algebra")


def headers(client: TestClient, user: TestUser) -> dict[str, str]:
    return bearer(login_token(client, user.email))


def enroll(client: TestClient, user: TestUser, subject: str, email: str) -> Response:
    response: Response = client.post(
        enrollments_url(subject), json={"student_email": email}, headers=headers(client, user)
    )
    return response


def enroll_raw(
    client: TestClient, user: TestUser, subject: str, payload: dict[str, object]
) -> Response:
    """POST escaped JSON text (lone surrogates cannot be UTF-8 encoded by the HTTP client)."""
    response: Response = client.post(
        enrollments_url(subject),
        content=json.dumps(payload).encode("ascii"),
        headers={**headers(client, user), "Content-Type": "application/json"},
    )
    return response


def count(db_session: Session, table: str = "enrollments") -> int:
    return int(db_session.execute(text(f"SELECT count(*) FROM {table}")).scalar_one())  # noqa: S608


# --- Access control -----------------------------------------------------------------------


def test_students_get_403_on_every_enrollment_operation_and_nothing_changes(
    client: TestClient,
    clean_db: str,
    subject_id: str,
    student: TestUser,
    other_student: TestUser,
    db_session: Session,
) -> None:
    insert_enrollment(clean_db, subject_id, other_student.id)
    auth = headers(client, student)

    listed = client.get(enrollments_url(subject_id), headers=auth)
    added = client.post(
        enrollments_url(subject_id), json={"student_email": student.email}, headers=auth
    )
    removed = client.delete(f"{enrollments_url(subject_id)}/{other_student.id}", headers=auth)

    for response in (listed, added, removed):
        assert response.status_code == 403
        assert response.json()["code"] == "FORBIDDEN"
        assert other_student.email not in response.text
    assert count(db_session) == 1


def test_another_teacher_gets_the_same_404_as_for_a_missing_subject(
    client: TestClient,
    clean_db: str,
    subject_id: str,
    other_teacher: TestUser,
    student: TestUser,
    db_session: Session,
) -> None:
    insert_enrollment(clean_db, subject_id, student.id)
    auth = headers(client, other_teacher)
    missing = uuid.uuid4()
    expected = client.get(enrollments_url(str(missing)), headers=auth)

    responses = [
        client.get(enrollments_url(subject_id), headers=auth),
        client.post(
            enrollments_url(subject_id),
            json={"student_email": "other.student@example.com"},
            headers=auth,
        ),
        client.delete(f"{enrollments_url(subject_id)}/{student.id}", headers=auth),
    ]

    assert expected.status_code == 404
    for response in responses:
        assert response.status_code == 404
        assert response.json() == expected.json()
        assert student.email not in response.text
    assert count(db_session) == 1


def test_anonymous_clients_get_401(client: TestClient, subject_id: str, student: TestUser) -> None:
    url = enrollments_url(subject_id)

    assert client.get(url).status_code == 401
    assert client.post(url, json={"student_email": student.email}).status_code == 401
    assert client.delete(f"{url}/{student.id}").status_code == 401


def test_malformed_identifiers_are_422_and_never_a_server_error(
    client: TestClient, subject_id: str, teacher: TestUser
) -> None:
    auth = headers(client, teacher)

    assert client.get(enrollments_url("not-a-uuid"), headers=auth).status_code == 422
    assert (
        client.post(
            enrollments_url("not-a-uuid"), json={"student_email": "a@example.com"}, headers=auth
        ).status_code
        == 422
    )
    assert (
        client.delete(f"{enrollments_url(subject_id)}/not-a-uuid", headers=auth).status_code == 422
    )
    assert client.delete(f"{enrollments_url('x')}/{uuid.uuid4()}", headers=auth).status_code == 422


# --- Enrolling ----------------------------------------------------------------------------


def test_owner_enrolls_a_registered_student_regardless_of_letter_case(
    client: TestClient, subject_id: str, teacher: TestUser, student: TestUser
) -> None:
    response = enroll(client, teacher, subject_id, "  STUDENT@Example.COM ")

    assert response.status_code == 201
    body = response.json()
    assert set(body) == {"id", "subject_id", "student_id", "student_email", "created_at"}
    assert body["subject_id"] == subject_id
    assert body["student_id"] == student.id
    assert body["student_email"] == "student@example.com"


def test_enrolled_student_can_then_see_the_subject(
    client: TestClient, subject_id: str, teacher: TestUser, student: TestUser
) -> None:
    enroll(client, teacher, subject_id, student.email)

    response = client.get(f"{SUBJECTS}/{subject_id}", headers=headers(client, student))

    assert response.status_code == 200


def invalid_emails() -> list[str]:
    return [
        "not-an-email",
        "",
        "jos" + chr(0xE9) + "@example.com",
        "user@b" + chr(0xFC) + "cher.com",
        "a" * 250 + "@example.com",
        "a" + chr(0) + "b@example.com",
        "a" + chr(0xD800) + "b@example.com",
        "a" + chr(1) + "b@example.com",
    ]


@pytest.mark.parametrize("email", invalid_emails())
def test_invalid_emails_are_422_without_echo_and_nothing_is_stored(
    client: TestClient, subject_id: str, teacher: TestUser, db_session: Session, email: str
) -> None:
    response = enroll_raw(client, teacher, subject_id, {"student_email": email})

    assert response.status_code == 422
    assert response.json()["code"] == "VALIDATION_ERROR"
    if email:
        assert email not in response.text
    assert count(db_session) == 0


def test_missing_email_field_is_422(client: TestClient, subject_id: str, teacher: TestUser) -> None:
    response = client.post(enrollments_url(subject_id), json={}, headers=headers(client, teacher))

    assert response.status_code == 422


def test_unknown_and_teacher_emails_get_the_identical_404_without_the_email(
    client: TestClient,
    subject_id: str,
    teacher: TestUser,
    other_teacher: TestUser,
    db_session: Session,
) -> None:
    unknown = enroll(client, teacher, subject_id, "nobody@example.com")
    colleague = enroll(client, teacher, subject_id, other_teacher.email)

    for response, email in ((unknown, "nobody@example.com"), (colleague, other_teacher.email)):
        assert response.status_code == 404
        assert response.json()["code"] == "NOT_FOUND"
        assert email not in response.text
    assert unknown.json() == colleague.json()
    assert count(db_session) == 0


def test_there_is_no_pre_enrollment_for_unregistered_emails(
    client: TestClient, subject_id: str, teacher: TestUser
) -> None:
    assert enroll(client, teacher, subject_id, "later@example.com").status_code == 404

    registered = client.post(
        "/api/v1/auth/register",
        json={"name": "Later", "email": "later@example.com", "password": "a-very-long-password"},
    )
    assert registered.status_code == 201

    listed = client.get(enrollments_url(subject_id), headers=headers(client, teacher))
    assert listed.json() == []


def test_duplicate_enrollment_is_409_and_keeps_a_single_row(
    client: TestClient, subject_id: str, teacher: TestUser, student: TestUser, db_session: Session
) -> None:
    assert enroll(client, teacher, subject_id, student.email).status_code == 201

    second = enroll(client, teacher, subject_id, student.email)

    assert second.status_code == 409
    assert second.json()["code"] == "CONFLICT"
    assert count(db_session) == 1


def test_same_student_can_be_enrolled_by_two_teachers_in_their_own_subjects(
    client: TestClient,
    clean_db: str,
    subject_id: str,
    teacher: TestUser,
    other_teacher: TestUser,
    student: TestUser,
) -> None:
    other_subject = insert_subject(clean_db, other_teacher.id, "Algebra")

    assert enroll(client, teacher, subject_id, student.email).status_code == 201
    assert enroll(client, other_teacher, other_subject, student.email).status_code == 201


def test_concurrent_identical_enrollments_yield_one_row_and_no_server_error(
    client: TestClient, subject_id: str, teacher: TestUser, student: TestUser, db_session: Session
) -> None:
    auth = headers(client, teacher)

    def attempt(_: int) -> int:
        status: int = client.post(
            enrollments_url(subject_id), json={"student_email": student.email}, headers=auth
        ).status_code
        return status

    with ThreadPoolExecutor(max_workers=8) as pool:
        statuses = sorted(pool.map(attempt, range(8)))

    assert statuses == [201, *([409] * 7)]
    assert count(db_session) == 1


# --- Listing ------------------------------------------------------------------------------


def test_list_is_scoped_to_the_subject_ordered_and_exposes_only_ids_and_email(
    client: TestClient,
    clean_db: str,
    subject_id: str,
    teacher: TestUser,
    student: TestUser,
    other_student: TestUser,
    make_user: MakeUser,
) -> None:
    third = make_user("third@example.com", UserRole.STUDENT)
    other_subject = insert_subject(clean_db, teacher.id, "Biology")
    insert_enrollment(clean_db, subject_id, other_student.id)
    insert_enrollment(clean_db, subject_id, student.id)
    insert_enrollment(clean_db, other_subject, third.id)

    response = client.get(enrollments_url(subject_id), headers=headers(client, teacher))

    assert response.status_code == 200
    rows = response.json()
    assert [row["student_email"] for row in rows] == [other_student.email, student.email]
    for row in rows:
        assert set(row) == {"id", "subject_id", "student_id", "student_email", "created_at"}
        assert row["subject_id"] == subject_id
    assert "third@example.com" not in response.text
    assert "password" not in response.text


def test_list_of_an_owned_subject_without_students_is_an_empty_array(
    client: TestClient, subject_id: str, teacher: TestUser
) -> None:
    response = client.get(enrollments_url(subject_id), headers=headers(client, teacher))

    assert response.status_code == 200
    assert response.json() == []


# --- Removing -----------------------------------------------------------------------------


def test_removing_an_enrollment_revokes_access_and_keeps_the_account(
    client: TestClient,
    clean_db: str,
    subject_id: str,
    teacher: TestUser,
    student: TestUser,
    db_session: Session,
) -> None:
    insert_enrollment(clean_db, subject_id, student.id)

    response = client.delete(
        f"{enrollments_url(subject_id)}/{student.id}", headers=headers(client, teacher)
    )

    assert response.status_code == 204
    assert (
        client.get(f"{SUBJECTS}/{subject_id}", headers=headers(client, student)).status_code == 404
    )
    assert count(db_session, "users") == 2


def test_removing_a_missing_enrollment_is_404_and_leaves_the_others(
    client: TestClient,
    clean_db: str,
    subject_id: str,
    teacher: TestUser,
    student: TestUser,
    other_student: TestUser,
    db_session: Session,
) -> None:
    insert_enrollment(clean_db, subject_id, student.id)
    auth = headers(client, teacher)

    not_enrolled = client.delete(f"{enrollments_url(subject_id)}/{other_student.id}", headers=auth)
    random_student = client.delete(f"{enrollments_url(subject_id)}/{uuid.uuid4()}", headers=auth)

    assert not_enrolled.status_code == 404
    assert random_student.status_code == 404
    assert count(db_session) == 1


def test_removing_a_student_who_is_enrolled_only_in_another_subject_is_404(
    client: TestClient,
    clean_db: str,
    subject_id: str,
    teacher: TestUser,
    student: TestUser,
    db_session: Session,
) -> None:
    other_subject = insert_subject(clean_db, teacher.id, "Biology")
    insert_enrollment(clean_db, other_subject, student.id)

    response = client.delete(
        f"{enrollments_url(subject_id)}/{student.id}", headers=headers(client, teacher)
    )

    assert response.status_code == 404
    assert count(db_session) == 1


def test_deleting_the_subject_removes_enrollments_visible_through_the_api(
    client: TestClient,
    clean_db: str,
    subject_id: str,
    teacher: TestUser,
    student: TestUser,
    db_session: Session,
) -> None:
    insert_enrollment(clean_db, subject_id, student.id)

    assert (
        client.delete(f"{SUBJECTS}/{subject_id}", headers=headers(client, teacher)).status_code
        == 204
    )

    assert count(db_session) == 0
    assert client.get(f"{SUBJECTS}", headers=headers(client, student)).json() == []


# --- Logs and error paths -----------------------------------------------------------------


def test_emails_of_rejected_enrollments_do_not_reach_the_log(
    client: TestClient,
    subject_id: str,
    teacher: TestUser,
    other_teacher: TestUser,
    caplog: pytest.LogCaptureFixture,
) -> None:
    auth_email = "nobody.at.all@example.com"
    with caplog.at_level(logging.DEBUG):
        enroll(client, teacher, subject_id, auth_email)
        enroll(client, teacher, subject_id, other_teacher.email)
        enroll_raw(client, teacher, subject_id, {"student_email": "bad" + chr(0) + "@example.com"})

    assert auth_email not in caplog.text
    assert other_teacher.email not in caplog.text


def break_statement(client: TestClient, contains: str, old: str, new: str) -> None:
    """Make PostgreSQL reject statements containing `contains` (real error, bound parameters)."""
    engine = client.app.state.session_factory.kw["bind"]  # type: ignore[attr-defined]

    @event.listens_for(engine, "before_cursor_execute", retval=True)
    def rewrite(conn, cursor, statement, parameters, context, executemany):  # type: ignore[no-untyped-def]
        if contains in statement:
            statement = statement.replace(old, new, 1)
        return statement, parameters


def test_a_database_error_during_enrollment_never_logs_the_email(
    client: TestClient,
    subject_id: str,
    teacher: TestUser,
    student: TestUser,
    caplog: pytest.LogCaptureFixture,
) -> None:
    auth = headers(client, teacher)
    break_statement(client, "users.email =", "FROM users", "FROM users_missing")
    with caplog.at_level(logging.DEBUG):
        response = client.post(
            enrollments_url(subject_id), json={"student_email": student.email}, headers=auth
        )

    assert response.status_code == 500
    assert response.json()["code"] == "INTERNAL_ERROR"
    assert student.email not in response.text
    assert student.email not in caplog.text


def test_a_database_error_during_subject_creation_never_logs_the_name(
    client: TestClient, teacher: TestUser, caplog: pytest.LogCaptureFixture
) -> None:
    auth = headers(client, teacher)
    break_statement(client, "INSERT INTO subjects", "INTO subjects", "INTO subjects_missing")
    with caplog.at_level(logging.DEBUG):
        response = client.post(
            SUBJECTS,
            json={"name": "Confidential Course", "description": "Private text"},
            headers=auth,
        )

    assert response.status_code == 500
    assert "Confidential Course" not in response.text
    assert "Confidential Course" not in caplog.text
    assert "Private text" not in caplog.text
