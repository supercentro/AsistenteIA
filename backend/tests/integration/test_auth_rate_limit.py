import time

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import text

from app.core import security
from app.core.config import Settings
from app.core.database import create_db_engine
from tests.constants import TEST_JWT_SECRET
from tests.integration.helpers import DEFAULT_PASSWORD, MakeUser, build_app

LOGIN = "/api/v1/auth/login"


def attempt(client: TestClient, email: str, password: str, **headers: str) -> int:
    response = client.post(LOGIN, json={"email": email, "password": password}, headers=headers)
    return int(response.status_code)


@pytest.fixture
def limited_client(clean_db: str) -> TestClient:
    return TestClient(
        build_app(clean_db, login_rate_limit="3/minute"), raise_server_exceptions=False
    )


def test_attempt_over_the_limit_gets_429_with_retry_after_even_with_correct_credentials(
    limited_client: TestClient, make_user: MakeUser
) -> None:
    user = make_user("ana@example.com")

    results = [attempt(limited_client, user.email, "bad-password-xx") for _ in range(3)]
    blocked = limited_client.post(LOGIN, json={"email": user.email, "password": user.password})

    assert results == [401, 401, 401]
    assert blocked.status_code == 429
    assert blocked.json()["code"] == "RATE_LIMITED"
    assert 1 <= int(blocked.headers["retry-after"]) <= 60
    assert "access_token" not in blocked.text


def test_successful_logins_also_count(limited_client: TestClient, make_user: MakeUser) -> None:
    user = make_user("ana@example.com")

    results = [attempt(limited_client, user.email, user.password) for _ in range(4)]

    assert results == [200, 200, 200, 429]


def test_limit_is_released_after_the_window(clean_db: str, make_user: MakeUser) -> None:
    client = TestClient(build_app(clean_db, login_rate_limit="2/second"))
    user = make_user("ana@example.com")

    first = [attempt(client, user.email, user.password) for _ in range(3)]
    time.sleep(1.2)
    after = attempt(client, user.email, user.password)

    assert first == [200, 200, 429]
    assert after == 200


def test_other_endpoints_are_not_limited(limited_client: TestClient, make_user: MakeUser) -> None:
    user = make_user("ana@example.com")
    for _ in range(4):
        attempt(limited_client, user.email, "bad-password-xx")

    me = limited_client.get("/api/v1/users/me")
    register = limited_client.post(
        "/api/v1/auth/register",
        json={"name": "N", "email": "new@example.com", "password": DEFAULT_PASSWORD},
    )

    assert me.status_code == 401  # unauthenticated, but not 429
    assert register.status_code == 201


def test_forged_forwarding_headers_do_not_change_the_bucket(
    limited_client: TestClient, make_user: MakeUser
) -> None:
    user = make_user("ana@example.com")

    results = [
        attempt(
            limited_client,
            user.email,
            "bad-password-xx",
            **{
                "X-Forwarded-For": f"203.0.113.{index}",
                "X-Real-IP": f"198.51.100.{index}",
                "Forwarded": f"for=192.0.2.{index}",
            },
        )
        for index in range(1, 6)
    ]

    assert results == [401, 401, 401, 429, 429]


def test_limit_is_checked_before_any_hashing_or_database_work(
    limited_client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    for _ in range(3):
        attempt(limited_client, "ghost@example.com", "bad-password-xx")
    calls: list[str] = []

    def forbidden(*args: object, **kwargs: object) -> bool:
        calls.append("hash")
        return False

    monkeypatch.setattr(security.PasswordService, "verify", forbidden)
    monkeypatch.setattr(security.PasswordService, "verify_dummy", forbidden)

    status = attempt(limited_client, "ghost@example.com", "bad-password-xx")

    assert status == 429
    assert calls == []


# ------------------------------------------------------------------ register

REGISTER = "/api/v1/auth/register"


def register_attempt(client: TestClient, email: str, **headers: str) -> int:
    response = client.post(
        REGISTER,
        json={"name": "N", "email": email, "password": DEFAULT_PASSWORD},
        headers=headers,
    )
    return int(response.status_code)


@pytest.fixture
def register_limited_client(clean_db: str) -> TestClient:
    return TestClient(
        build_app(clean_db, register_rate_limit="3/minute"), raise_server_exceptions=False
    )


def user_count(database_url: str) -> int:
    engine = create_db_engine(database_url)
    try:
        with engine.connect() as conn:
            return int(conn.execute(text("SELECT count(*) FROM users")).scalar_one())
    finally:
        engine.dispose()


def test_register_over_the_limit_gets_429_with_retry_after(
    register_limited_client: TestClient, clean_db: str
) -> None:
    results = [register_attempt(register_limited_client, f"u{i}@example.com") for i in range(3)]

    blocked = register_limited_client.post(
        REGISTER, json={"name": "N", "email": "late@example.com", "password": DEFAULT_PASSWORD}
    )

    assert results == [201, 201, 201]
    assert blocked.status_code == 429
    assert blocked.json()["code"] == "RATE_LIMITED"
    assert 1 <= int(blocked.headers["retry-after"]) <= 60
    assert user_count(clean_db) == 3


def test_blocked_registration_runs_no_argon2_and_stores_nothing(
    register_limited_client: TestClient, clean_db: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    for i in range(3):
        register_attempt(register_limited_client, f"u{i}@example.com")
    hashes: list[str] = []

    def spy_hash(self: security.PasswordService, password: str) -> str:
        hashes.append("hash")
        return "$argon2id$should-not-exist"

    monkeypatch.setattr(security.PasswordService, "hash", spy_hash)

    status = register_attempt(register_limited_client, "blocked@example.com")

    assert status == 429
    assert hashes == []
    assert user_count(clean_db) == 3


def test_register_default_limit_is_five_per_minute(clean_db: str) -> None:
    settings = Settings(database_url=clean_db, jwt_secret=TEST_JWT_SECRET)

    assert settings.register_rate_limit == "5/minute"


def test_register_limit_ignores_forged_forwarding_headers(
    register_limited_client: TestClient,
) -> None:
    results = [
        register_attempt(
            register_limited_client,
            f"u{i}@example.com",
            **{"X-Forwarded-For": f"203.0.113.{i}", "X-Real-IP": f"198.51.100.{i}"},
        )
        for i in range(1, 6)
    ]

    assert results == [201, 201, 201, 429, 429]


def test_register_and_login_limits_are_independent(clean_db: str, make_user: MakeUser) -> None:
    client = TestClient(
        build_app(clean_db, register_rate_limit="2/minute", login_rate_limit="2/minute"),
        raise_server_exceptions=False,
    )
    user = make_user("ana@example.com")

    register_statuses = [register_attempt(client, f"n{i}@example.com") for i in range(3)]
    login_status = attempt(client, user.email, user.password)

    assert register_statuses == [201, 201, 429]
    assert login_status == 200


def test_validation_failures_also_count_against_the_register_limit(
    register_limited_client: TestClient,
) -> None:
    for _ in range(3):
        register_limited_client.post(REGISTER, json={"name": "N", "email": "bad", "password": "x"})

    assert register_attempt(register_limited_client, "ok@example.com") == 429
