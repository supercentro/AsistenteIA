from fastapi.testclient import TestClient
from sqlalchemy import text

from app.core.database import create_db_engine
from tests.integration.helpers import DEFAULT_PASSWORD

URL = "/api/v1/auth/register"


def payload(**overrides: object) -> dict[str, object]:
    body: dict[str, object] = {
        "name": "Ana Pérez",
        "email": "Ana@Example.com",
        "password": DEFAULT_PASSWORD,
    }
    body.update(overrides)
    return body


def rows(clean_db: str, sql: str) -> list[tuple[object, ...]]:
    engine = create_db_engine(clean_db)
    try:
        with engine.connect() as conn:
            return [tuple(row) for row in conn.execute(text(sql))]
    finally:
        engine.dispose()


def test_register_creates_a_student_with_lowercase_email(client: TestClient, clean_db: str) -> None:
    response = client.post(URL, json=payload())

    body = response.json()
    assert response.status_code == 201
    assert body["email"] == "ana@example.com"
    assert body["name"] == "Ana Pérez"
    assert body["role"] == "student"
    assert body["consent_version"] is None
    assert body["consent_accepted_at"] is None
    assert set(body) == {
        "id",
        "name",
        "email",
        "role",
        "consent_version",
        "consent_accepted_at",
    }
    assert rows(clean_db, "SELECT count(*) FROM users") == [(1,)]


def test_register_response_never_contains_password_or_hash(client: TestClient) -> None:
    response = client.post(URL, json=payload())

    assert DEFAULT_PASSWORD not in response.text
    assert "argon2" not in response.text
    assert "password" not in response.text.lower()


def test_register_stores_an_argon2id_hash_not_the_password(
    client: TestClient, clean_db: str
) -> None:
    client.post(URL, json=payload())

    [(stored,)] = rows(clean_db, "SELECT password_hash FROM users")
    assert isinstance(stored, str)
    assert stored.startswith("$argon2id$")
    assert DEFAULT_PASSWORD not in stored


def test_register_ignores_a_role_in_the_payload(client: TestClient, clean_db: str) -> None:
    response = client.post(URL, json=payload(role="teacher"))

    assert response.status_code == 201
    assert response.json()["role"] == "student"
    assert rows(clean_db, "SELECT role::text FROM users") == [("student",)]


def test_register_duplicate_email_in_any_case_returns_409_and_keeps_one_row(
    client: TestClient, clean_db: str
) -> None:
    client.post(URL, json=payload(email="ana@example.com"))

    response = client.post(URL, json=payload(email="ANA@EXAMPLE.COM", name="Impostor"))

    assert response.status_code == 409
    assert response.json()["code"] == "CONFLICT"
    assert rows(clean_db, "SELECT count(*) FROM users") == [(1,)]


def test_register_rejects_a_password_of_9_characters(client: TestClient, clean_db: str) -> None:
    response = client.post(URL, json=payload(password="123456789"))

    assert response.status_code == 422
    assert response.json()["code"] == "VALIDATION_ERROR"
    assert rows(clean_db, "SELECT count(*) FROM users") == [(0,)]


def test_register_accepts_a_password_of_exactly_10_and_128_characters(
    client: TestClient,
) -> None:
    assert (
        client.post(URL, json=payload(email="a@example.com", password="x" * 10)).status_code == 201
    )
    assert (
        client.post(URL, json=payload(email="b@example.com", password="y" * 128)).status_code == 201
    )


def test_register_rejects_a_password_of_129_characters_without_hashing(
    client: TestClient, clean_db: str
) -> None:
    response = client.post(URL, json=payload(password="z" * 129))

    assert response.status_code == 422
    assert rows(clean_db, "SELECT count(*) FROM users") == [(0,)]


def test_register_does_not_apply_complexity_rules(client: TestClient) -> None:
    assert client.post(URL, json=payload(password="aaaaaaaaaa")).status_code == 201


def test_register_rejects_invalid_email_and_blank_or_long_name(client: TestClient) -> None:
    assert client.post(URL, json=payload(email="not-an-email")).status_code == 422
    assert client.post(URL, json=payload(name="   ")).status_code == 422
    assert client.post(URL, json=payload(name="")).status_code == 422
    assert client.post(URL, json=payload(name="n" * 101)).status_code == 422
    assert client.post(URL, json=payload(email=f"{'a' * 250}@example.com")).status_code == 422


def test_register_validation_errors_do_not_echo_submitted_values(client: TestClient) -> None:
    response = client.post(URL, json=payload(email="leaky-value", password="short"))

    assert response.status_code == 422
    assert "leaky-value" not in response.text
    assert "short" not in response.text


def test_register_missing_fields_return_422(client: TestClient) -> None:
    assert client.post(URL, json={}).status_code == 422
    assert client.post(URL, json={"email": "a@example.com"}).status_code == 422
