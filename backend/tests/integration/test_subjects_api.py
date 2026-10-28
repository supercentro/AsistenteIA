import json
import uuid
from concurrent.futures import ThreadPoolExecutor

import pytest
from fastapi.testclient import TestClient
from httpx import Response
from sqlalchemy import text
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


def headers(client: TestClient, user: TestUser) -> dict[str, str]:
    return bearer(login_token(client, user.email))


def create(client: TestClient, user: TestUser, **body: object) -> Response:
    payload: dict[str, object] = {"name": "Algebra"}
    payload.update(body)
    response: Response = client.post(SUBJECTS, json=payload, headers=headers(client, user))
    return response


def subject_count(db_session: Session) -> int:
    return int(db_session.execute(text("SELECT count(*) FROM subjects")).scalar_one())


def post_json(client: TestClient, user: TestUser, payload: dict[str, object]) -> Response:
    """POST escaped JSON text (lone surrogates cannot be UTF-8 encoded by the HTTP client)."""
    response: Response = client.post(
        SUBJECTS,
        content=json.dumps(payload).encode("ascii"),
        headers={**headers(client, user), "Content-Type": "application/json"},
    )
    return response


# --- Create ------------------------------------------------------------------------------


def test_teacher_creates_a_subject(client: TestClient, teacher: TestUser) -> None:
    response = create(client, teacher, name="Algebra", description="Linear algebra")

    assert response.status_code == 201
    body = response.json()
    assert set(body) == {"id", "name", "description", "teacher_id", "created_at"}
    assert body["name"] == "Algebra"
    assert body["description"] == "Linear algebra"
    assert body["teacher_id"] == teacher.id
    uuid.UUID(body["id"])


def test_description_is_optional(client: TestClient, teacher: TestUser) -> None:
    response = client.post(SUBJECTS, json={"name": "Algebra"}, headers=headers(client, teacher))

    assert response.status_code == 201
    assert response.json()["description"] is None


def test_student_cannot_create_a_subject(
    client: TestClient, student: TestUser, db_session: Session
) -> None:
    response = client.post(SUBJECTS, json={"name": "Algebra"}, headers=headers(client, student))

    assert response.status_code == 403
    assert response.json()["code"] == "FORBIDDEN"
    assert subject_count(db_session) == 0


def test_anonymous_client_cannot_create_a_subject(
    client: TestClient, teacher: TestUser, db_session: Session
) -> None:
    response = client.post(SUBJECTS, json={"name": "Algebra"})

    assert response.status_code == 401
    assert subject_count(db_session) == 0


# --- Input validation -------------------------------------------------------------------


@pytest.mark.parametrize("name", ["", "   ", "a" * 151])
def test_blank_or_oversized_name_is_422_and_nothing_is_stored(
    client: TestClient, teacher: TestUser, db_session: Session, name: str
) -> None:
    response = client.post(SUBJECTS, json={"name": name}, headers=headers(client, teacher))

    assert response.status_code == 422
    assert response.json()["code"] == "VALIDATION_ERROR"
    assert subject_count(db_session) == 0


def test_name_is_trimmed(client: TestClient, teacher: TestUser) -> None:
    response = client.post(SUBJECTS, json={"name": "  Algebra  "}, headers=headers(client, teacher))

    assert response.status_code == 201
    assert response.json()["name"] == "Algebra"


def test_name_length_boundary_is_150(client: TestClient, teacher: TestUser) -> None:
    auth = headers(client, teacher)

    assert client.post(SUBJECTS, json={"name": "a" * 150}, headers=auth).status_code == 201
    assert client.post(SUBJECTS, json={"name": "a" * 151}, headers=auth).status_code == 422


def test_description_with_line_breaks_and_tabs_is_kept(
    client: TestClient, teacher: TestUser
) -> None:
    text_value = "line one\nline two\r\n\tindented"

    response = create(client, teacher, description=text_value)

    assert response.status_code == 201
    assert response.json()["description"] == text_value


def odd_text() -> list[str]:
    return [
        chr(0),
        "a" + chr(0) + "b",
        "a" + chr(1) + "b",
        "a" + chr(0x2028) + "b",
        "a" + chr(0x2029) + "b",
        "a" + chr(0x202E) + "b",
        "a" + chr(0x2066) + "b",
        "a" + chr(0xD800) + "b",
        chr(0xDFFF),
    ]


@pytest.mark.parametrize("value", odd_text())
def test_odd_text_in_the_name_is_a_4xx_and_never_a_server_error(
    client: TestClient, teacher: TestUser, db_session: Session, value: str
) -> None:
    response = post_json(client, teacher, {"name": value})

    assert response.status_code == 422
    assert subject_count(db_session) == 0


@pytest.mark.parametrize("value", [*odd_text(), "x" * 2001])
def test_invalid_descriptions_are_422_and_nothing_is_stored(
    client: TestClient, teacher: TestUser, db_session: Session, value: str
) -> None:
    if value == chr(0) or "\n" in value:
        pass
    response = post_json(client, teacher, {"name": "Algebra", "description": value})

    assert response.status_code == 422
    assert subject_count(db_session) == 0


def test_validation_errors_do_not_echo_the_submitted_values(
    client: TestClient, teacher: TestUser
) -> None:
    secret = "secret-name-" + chr(0)

    response = client.post(SUBJECTS, json={"name": secret}, headers=headers(client, teacher))

    assert response.status_code == 422
    assert "secret-name" not in response.text


# --- Uniqueness ---------------------------------------------------------------------------


def test_duplicate_name_for_the_same_teacher_is_409_and_keeps_the_first(
    client: TestClient, teacher: TestUser, db_session: Session
) -> None:
    first = create(client, teacher, name="Algebra", description="first")

    second = create(client, teacher, name="Algebra", description="second")

    assert second.status_code == 409
    assert second.json()["code"] == "CONFLICT"
    assert subject_count(db_session) == 1
    stored = db_session.execute(text("SELECT description FROM subjects")).scalar_one()
    assert stored == "first"
    assert first.status_code == 201


def test_names_are_case_sensitive_and_shared_between_teachers(
    client: TestClient, teacher: TestUser, other_teacher: TestUser
) -> None:
    assert create(client, teacher, name="Algebra").status_code == 201
    assert create(client, teacher, name="algebra").status_code == 201
    assert create(client, other_teacher, name="Algebra").status_code == 201


def test_concurrent_identical_creations_yield_one_subject_and_no_server_error(
    client: TestClient, teacher: TestUser, db_session: Session
) -> None:
    auth = headers(client, teacher)

    def attempt(_: int) -> int:
        status: int = client.post(SUBJECTS, json={"name": "Racing"}, headers=auth).status_code
        return status

    with ThreadPoolExecutor(max_workers=8) as pool:
        statuses = sorted(pool.map(attempt, range(8)))

    assert statuses == [201, *([409] * 7)]
    assert subject_count(db_session) == 1


# --- List -----------------------------------------------------------------------------------


def test_teacher_lists_only_their_own_subjects_ordered_by_name(
    client: TestClient, clean_db: str, teacher: TestUser, other_teacher: TestUser
) -> None:
    insert_subject(clean_db, teacher.id, "Zoology")
    insert_subject(clean_db, teacher.id, "Algebra")
    insert_subject(clean_db, other_teacher.id, "Biology")

    response = client.get(SUBJECTS, headers=headers(client, teacher))

    assert response.status_code == 200
    assert [item["name"] for item in response.json()] == ["Algebra", "Zoology"]


def test_student_lists_only_enrolled_subjects(
    client: TestClient, clean_db: str, teacher: TestUser, student: TestUser, other_student: TestUser
) -> None:
    enrolled = insert_subject(clean_db, teacher.id, "Algebra")
    insert_subject(clean_db, teacher.id, "Biology")
    other = insert_subject(clean_db, teacher.id, "Chemistry")
    insert_enrollment(clean_db, enrolled, student.id)
    insert_enrollment(clean_db, other, other_student.id)

    response = client.get(SUBJECTS, headers=headers(client, student))

    assert response.status_code == 200
    assert [item["id"] for item in response.json()] == [enrolled]


def test_list_is_an_empty_array_without_subjects(client: TestClient, student: TestUser) -> None:
    response = client.get(SUBJECTS, headers=headers(client, student))

    assert response.status_code == 200
    assert response.json() == []


def test_anonymous_client_cannot_list_subjects(client: TestClient) -> None:
    assert client.get(SUBJECTS).status_code == 401


# --- Get ------------------------------------------------------------------------------------


def test_owner_and_enrolled_student_can_get_the_subject(
    client: TestClient, clean_db: str, teacher: TestUser, student: TestUser
) -> None:
    subject_id = insert_subject(clean_db, teacher.id)
    insert_enrollment(clean_db, subject_id, student.id)

    as_teacher = client.get(f"{SUBJECTS}/{subject_id}", headers=headers(client, teacher))
    as_student = client.get(f"{SUBJECTS}/{subject_id}", headers=headers(client, student))

    assert as_teacher.status_code == 200
    assert as_student.status_code == 200
    assert as_teacher.json() == as_student.json()
    assert as_teacher.json()["id"] == subject_id


def test_inaccessible_subjects_answer_the_same_404_as_missing_ones(
    client: TestClient,
    clean_db: str,
    teacher: TestUser,
    other_teacher: TestUser,
    other_student: TestUser,
) -> None:
    subject_id = insert_subject(clean_db, teacher.id)

    missing = client.get(f"{SUBJECTS}/{uuid.uuid4()}", headers=headers(client, other_teacher))
    other_teacher_response = client.get(
        f"{SUBJECTS}/{subject_id}", headers=headers(client, other_teacher)
    )
    not_enrolled = client.get(f"{SUBJECTS}/{subject_id}", headers=headers(client, other_student))

    for response in (other_teacher_response, not_enrolled):
        assert response.status_code == 404
        assert response.json() == missing.json()
        assert response.json()["code"] == "NOT_FOUND"
    assert subject_id not in other_teacher_response.text


def test_malformed_subject_id_is_422(client: TestClient, teacher: TestUser) -> None:
    response = client.get(f"{SUBJECTS}/not-a-uuid", headers=headers(client, teacher))

    assert response.status_code == 422
    assert response.json()["code"] == "VALIDATION_ERROR"


def test_anonymous_client_cannot_get_or_delete(client: TestClient) -> None:
    path = f"{SUBJECTS}/{uuid.uuid4()}"

    assert client.get(path).status_code == 401
    assert client.delete(path).status_code == 401


# --- Delete ---------------------------------------------------------------------------------


def test_owner_deletes_the_subject_with_its_enrollments_and_keeps_the_students(
    client: TestClient,
    clean_db: str,
    teacher: TestUser,
    student: TestUser,
    db_session: Session,
) -> None:
    subject_id = insert_subject(clean_db, teacher.id)
    insert_enrollment(clean_db, subject_id, student.id)

    response = client.delete(f"{SUBJECTS}/{subject_id}", headers=headers(client, teacher))

    assert response.status_code == 204
    assert response.content == b""
    assert subject_count(db_session) == 0
    assert db_session.execute(text("SELECT count(*) FROM enrollments")).scalar_one() == 0
    assert db_session.execute(text("SELECT count(*) FROM users")).scalar_one() == 2
    again = client.delete(f"{SUBJECTS}/{subject_id}", headers=headers(client, teacher))
    assert again.status_code == 404


def test_another_teacher_cannot_delete_the_subject(
    client: TestClient,
    clean_db: str,
    teacher: TestUser,
    other_teacher: TestUser,
    db_session: Session,
) -> None:
    subject_id = insert_subject(clean_db, teacher.id)

    response = client.delete(f"{SUBJECTS}/{subject_id}", headers=headers(client, other_teacher))

    assert response.status_code == 404
    assert subject_count(db_session) == 1


def test_student_cannot_delete_a_subject(
    client: TestClient, clean_db: str, teacher: TestUser, student: TestUser, db_session: Session
) -> None:
    subject_id = insert_subject(clean_db, teacher.id)
    insert_enrollment(clean_db, subject_id, student.id)

    response = client.delete(f"{SUBJECTS}/{subject_id}", headers=headers(client, student))

    assert response.status_code == 403
    assert response.json()["code"] == "FORBIDDEN"
    assert subject_count(db_session) == 1


def test_delete_with_a_malformed_id_is_422(client: TestClient, teacher: TestUser) -> None:
    response = client.delete(f"{SUBJECTS}/not-a-uuid", headers=headers(client, teacher))

    assert response.status_code == 422
