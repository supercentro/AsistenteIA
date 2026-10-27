from collections.abc import Iterator
from typing import Annotated

import pytest
from fastapi import Depends
from fastapi.testclient import TestClient
from sqlalchemy import text

from app.api.deps import require_student, require_teacher
from app.core.database import create_db_engine
from app.models.user import User, UserRole
from tests.integration.helpers import MakeUser, bearer, build_app, build_settings, login_token
from tests.tokens import forge_token


@pytest.fixture
def guarded_client(clean_db: str) -> Iterator[TestClient]:
    app = build_app(clean_db)

    def teacher_area(user: Annotated[User, Depends(require_teacher)]) -> dict[str, str]:
        return {"role": user.role.value}

    def student_area(user: Annotated[User, Depends(require_student)]) -> dict[str, str]:
        return {"role": user.role.value}

    app.add_api_route("/test/teacher-only", teacher_area)
    app.add_api_route("/test/student-only", student_area)
    with TestClient(app, raise_server_exceptions=False) as client:
        yield client


def set_role(database_url: str, user_id: str, role: str) -> None:
    engine = create_db_engine(database_url)
    with engine.begin() as conn:
        conn.execute(text("UPDATE users SET role = :r WHERE id = :id"), {"r": role, "id": user_id})
    engine.dispose()


def test_teacher_only_route_allows_teacher_and_denies_student_and_anonymous(
    guarded_client: TestClient, make_user: MakeUser
) -> None:
    teacher = make_user("teacher@example.com", UserRole.TEACHER)
    student = make_user("student@example.com", UserRole.STUDENT)

    as_teacher = guarded_client.get(
        "/test/teacher-only", headers=bearer(login_token(guarded_client, teacher.email))
    )
    as_student = guarded_client.get(
        "/test/teacher-only", headers=bearer(login_token(guarded_client, student.email))
    )
    anonymous = guarded_client.get("/test/teacher-only")

    assert as_teacher.status_code == 200
    assert as_student.status_code == 403
    assert as_student.json()["code"] == "FORBIDDEN"
    assert anonymous.status_code == 401


def test_student_only_route_allows_student_and_denies_teacher_and_anonymous(
    guarded_client: TestClient, make_user: MakeUser
) -> None:
    teacher = make_user("teacher@example.com", UserRole.TEACHER)
    student = make_user("student@example.com", UserRole.STUDENT)

    as_student = guarded_client.get(
        "/test/student-only", headers=bearer(login_token(guarded_client, student.email))
    )
    as_teacher = guarded_client.get(
        "/test/student-only", headers=bearer(login_token(guarded_client, teacher.email))
    )
    anonymous = guarded_client.get("/test/student-only")

    assert as_student.status_code == 200
    assert as_teacher.status_code == 403
    assert anonymous.status_code == 401


def test_role_change_in_the_database_applies_to_the_same_token(
    guarded_client: TestClient, make_user: MakeUser, clean_db: str
) -> None:
    user = make_user("grow@example.com", UserRole.STUDENT)
    token = login_token(guarded_client, user.email)
    assert guarded_client.get("/test/teacher-only", headers=bearer(token)).status_code == 403

    set_role(clean_db, user.id, "teacher")

    assert guarded_client.get("/test/teacher-only", headers=bearer(token)).status_code == 200
    assert guarded_client.get("/test/student-only", headers=bearer(token)).status_code == 403


def test_teacher_demoted_in_the_database_loses_access_with_the_same_token(
    guarded_client: TestClient, make_user: MakeUser, clean_db: str
) -> None:
    user = make_user("fall@example.com", UserRole.TEACHER)
    token = login_token(guarded_client, user.email)

    set_role(clean_db, user.id, "student")

    assert guarded_client.get("/test/teacher-only", headers=bearer(token)).status_code == 403


def test_role_claim_in_a_forged_token_is_ignored(
    guarded_client: TestClient, make_user: MakeUser, clean_db: str
) -> None:
    student = make_user("student@example.com", UserRole.STUDENT)
    forged = forge_token(build_settings(clean_db), student.id, role="teacher", is_admin=True)

    response = guarded_client.get("/test/teacher-only", headers=bearer(forged))

    assert response.status_code == 403
    assert guarded_client.get("/test/student-only", headers=bearer(forged)).status_code == 200


def test_no_endpoint_creates_teachers_or_changes_roles(guarded_client: TestClient) -> None:
    paths = guarded_client.app.openapi()["paths"]  # type: ignore[attr-defined]
    api_paths = {path for path in paths if path.startswith("/api/v1")}

    assert not any("teacher" in path or "role" in path for path in api_paths)
    methods = {(path, method) for path in api_paths for method in paths[path] if method != "get"}
    assert ("/api/v1/auth/register", "post") in methods
    schema = paths["/api/v1/auth/register"]["post"]["requestBody"]["content"]["application/json"][
        "schema"
    ]
    assert "RegisterRequest" in schema["$ref"]
    components = guarded_client.app.openapi()["components"]["schemas"]  # type: ignore[attr-defined]
    assert "role" not in components["RegisterRequest"]["properties"]
