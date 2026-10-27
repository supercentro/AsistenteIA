import json

import pytest
from fastapi.testclient import TestClient
from httpx import Response
from sqlalchemy import text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.core.database import create_db_engine
from app.models.user import User, UserRole
from app.repositories.user_repository import UserRepository
from tests.integration.helpers import DEFAULT_PASSWORD, MakeUser

REGISTER = "/api/v1/auth/register"
LOGIN = "/api/v1/auth/login"
NON_ASCII = [
    "ünï@example.com",
    "ｕｓｅｒ@example.com",
    "user@bücher.com",
    "ΣΑΣ@example.com",
    "аdmin@example.com",  # first letter is Cyrillic
]


def post_json(client: TestClient, url: str, payload: dict[str, object]) -> Response:
    response: Response = client.post(
        url,
        content=json.dumps(payload, ensure_ascii=True),
        headers={"Content-Type": "application/json"},
    )
    return response


def user_count(database_url: str) -> int:
    engine = create_db_engine(database_url)
    try:
        with engine.connect() as conn:
            return int(conn.execute(text("SELECT count(*) FROM users")).scalar_one())
    finally:
        engine.dispose()


@pytest.mark.parametrize("email", NON_ASCII)
def test_register_rejects_non_ascii_emails_and_stores_nothing(
    client: TestClient, clean_db: str, email: str
) -> None:
    response = post_json(
        client, REGISTER, {"name": "N", "email": email, "password": DEFAULT_PASSWORD}
    )

    assert response.status_code == 422
    assert response.json()["code"] == "VALIDATION_ERROR"
    assert email not in response.text
    assert user_count(clean_db) == 0


@pytest.mark.parametrize("email", NON_ASCII)
def test_login_with_a_non_ascii_email_is_422_never_500(client: TestClient, email: str) -> None:
    response = post_json(client, LOGIN, {"email": email, "password": "whatever-pass"})

    assert response.status_code == 422


def test_uppercase_ascii_is_stored_lowercase_and_duplicates_conflict(
    client: TestClient, clean_db: str
) -> None:
    first = client.post(
        REGISTER, json={"name": "N", "email": "Ana.Perez@Example.COM", "password": DEFAULT_PASSWORD}
    )
    second = client.post(
        REGISTER, json={"name": "N", "email": "ANA.PEREZ@example.com", "password": DEFAULT_PASSWORD}
    )

    assert first.status_code == 201
    assert first.json()["email"] == "ana.perez@example.com"
    assert second.status_code == 409
    assert user_count(clean_db) == 1


def test_punycode_domain_can_register_and_log_in(client: TestClient) -> None:
    email = "User@XN--BCHER-KVA.com"

    created = client.post(
        REGISTER, json={"name": "N", "email": email, "password": DEFAULT_PASSWORD}
    )
    login = client.post(LOGIN, json={"email": email.lower(), "password": DEFAULT_PASSWORD})

    assert created.status_code == 201
    assert created.json()["email"] == "user@xn--bcher-kva.com"
    assert login.status_code == 200


def test_existing_ascii_accounts_keep_working(client: TestClient, make_user: MakeUser) -> None:
    user = make_user("legacy.user@example.com")

    response = client.post(LOGIN, json={"email": user.email, "password": user.password})

    assert response.status_code == 200


def test_database_rejects_non_ascii_emails_even_if_the_application_did_not(
    db_session: Session,
) -> None:
    with pytest.raises(IntegrityError):
        UserRepository(db_session).add(
            User(name="N", email="ñandú@example.com", password_hash="h", role=UserRole.STUDENT)
        )
