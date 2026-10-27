import pytest
from fastapi.testclient import TestClient

from app.core import security
from tests.integration.helpers import DEFAULT_PASSWORD, MakeUser, bearer

LOGIN = "/api/v1/auth/login"


def test_login_returns_a_bearer_token_with_configured_lifetime(
    client: TestClient, make_user: MakeUser
) -> None:
    make_user("ana@example.com")

    response = client.post(LOGIN, json={"email": "ana@example.com", "password": DEFAULT_PASSWORD})

    body = response.json()
    assert response.status_code == 200
    assert body["token_type"] == "bearer"
    assert body["expires_in"] == 60 * 60
    assert isinstance(body["access_token"], str)
    assert set(body) == {"access_token", "token_type", "expires_in"}


def test_login_email_is_case_insensitive(client: TestClient, make_user: MakeUser) -> None:
    make_user("ana@example.com")

    response = client.post(LOGIN, json={"email": "ANA@Example.COM", "password": DEFAULT_PASSWORD})

    assert response.status_code == 200


def test_issued_token_authenticates_the_profile(client: TestClient, make_user: MakeUser) -> None:
    user = make_user("ana@example.com")
    token = client.post(LOGIN, json={"email": user.email, "password": user.password}).json()[
        "access_token"
    ]

    me = client.get("/api/v1/users/me", headers=bearer(token))

    assert me.status_code == 200
    assert me.json()["id"] == user.id


def test_wrong_password_and_unknown_email_return_identical_401(
    client: TestClient, make_user: MakeUser
) -> None:
    make_user("ana@example.com")

    wrong = client.post(LOGIN, json={"email": "ana@example.com", "password": "wrong-password-1"})
    unknown = client.post(
        LOGIN, json={"email": "ghost@example.com", "password": "wrong-password-1"}
    )

    assert wrong.status_code == unknown.status_code == 401
    assert wrong.json() == unknown.json()
    assert wrong.json()["code"] == "INVALID_CREDENTIALS"
    assert wrong.content == unknown.content
    assert wrong.headers.get("www-authenticate") == unknown.headers.get("www-authenticate")


def test_unknown_email_still_performs_a_password_verification(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    calls: list[str] = []
    original = security.PasswordService.verify_dummy

    def spy(self: security.PasswordService, password: str) -> bool:
        calls.append("dummy")
        return original(self, password)

    monkeypatch.setattr(security.PasswordService, "verify_dummy", spy)

    client.post(LOGIN, json={"email": "ghost@example.com", "password": "wrong-password-1"})

    assert calls == ["dummy"]


def test_login_missing_fields_return_422(client: TestClient) -> None:
    assert client.post(LOGIN, json={"password": DEFAULT_PASSWORD}).status_code == 422
    assert client.post(LOGIN, json={"email": "ana@example.com"}).status_code == 422
    assert client.post(LOGIN, json={}).status_code == 422


def test_login_rejects_oversized_password_with_422(client: TestClient) -> None:
    response = client.post(LOGIN, json={"email": "ana@example.com", "password": "p" * 129})

    assert response.status_code == 422


def test_login_response_never_exposes_the_password_or_hash(
    client: TestClient, make_user: MakeUser
) -> None:
    make_user("ana@example.com")

    response = client.post(LOGIN, json={"email": "ana@example.com", "password": DEFAULT_PASSWORD})

    assert DEFAULT_PASSWORD not in response.text
    assert "argon2" not in response.text
