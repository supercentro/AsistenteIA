import logging

import pytest
from fastapi.testclient import TestClient

from tests.constants import TEST_JWT_SECRET
from tests.integration.helpers import bearer

SECRET_PASSWORD = "very-secret-password-123"
WRONG_PASSWORD = "definitely-wrong-password-456"
EMAIL = "logs.person@example.com"


def test_authentication_flows_leave_no_secrets_or_emails_in_logs(
    client: TestClient, caplog: pytest.LogCaptureFixture
) -> None:
    with caplog.at_level(logging.DEBUG):
        client.post(
            "/api/v1/auth/register",
            json={"name": "Logs Person", "email": EMAIL, "password": SECRET_PASSWORD},
        )
        client.post(
            "/api/v1/auth/register",
            json={"name": "Logs Person", "email": EMAIL, "password": SECRET_PASSWORD},
        )
        failed = client.post(
            "/api/v1/auth/login", json={"email": EMAIL, "password": WRONG_PASSWORD}
        )
        unknown = client.post(
            "/api/v1/auth/login", json={"email": "ghost@example.com", "password": WRONG_PASSWORD}
        )
        ok = client.post("/api/v1/auth/login", json={"email": EMAIL, "password": SECRET_PASSWORD})
        token = ok.json()["access_token"]
        client.get("/api/v1/users/me", headers=bearer(token))
        client.get("/api/v1/users/me", headers=bearer(token + "tampered"))
        client.get("/api/v1/users/me", headers={"Authorization": "Bearer not.a.jwt"})

    assert failed.status_code == unknown.status_code == 401
    logged = caplog.text
    for forbidden in (
        SECRET_PASSWORD,
        WRONG_PASSWORD,
        token,
        token[:20],
        TEST_JWT_SECRET,
        EMAIL,
        "ghost@example.com",
        "argon2id",
        "Authorization",
    ):
        assert forbidden not in logged, forbidden


def test_successful_login_logs_the_user_id_only(
    client: TestClient, caplog: pytest.LogCaptureFixture
) -> None:
    created = client.post(
        "/api/v1/auth/register",
        json={"name": "Logs Person", "email": EMAIL, "password": SECRET_PASSWORD},
    ).json()

    with caplog.at_level(logging.INFO):
        client.post("/api/v1/auth/login", json={"email": EMAIL, "password": SECRET_PASSWORD})

    assert created["id"] in caplog.text
