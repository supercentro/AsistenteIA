"""Browsers only expose CORS-safelisted response headers to scripts: `Retry-After` of a 429 must be
listed in `Access-Control-Expose-Headers` or the frontend can never show the wait time (TD-021).
The rest of the CORS policy (origins, methods, credentials, headers) must stay as it was."""

import pytest
from fastapi.testclient import TestClient

from tests.integration.helpers import MakeUser, build_app

ALLOWED_ORIGIN = "http://localhost:5173"
OTHER_ORIGIN = "http://evil.example"
LOGIN = "/api/v1/auth/login"
REGISTER = "/api/v1/auth/register"


def exposed_headers(headers: dict[str, str]) -> set[str]:
    raw = headers.get("access-control-expose-headers", "")
    return {item.strip().lower() for item in raw.split(",") if item.strip()}


@pytest.fixture
def limited_client(clean_db: str) -> TestClient:
    app = build_app(clean_db, login_rate_limit="2/minute", register_rate_limit="2/minute")
    return TestClient(app, raise_server_exceptions=False)


def block_login(client: TestClient, origin: str) -> dict[str, str]:
    body = {"email": "nobody@example.com", "password": "wrong-password-xx"}
    for _ in range(2):
        client.post(LOGIN, json=body, headers={"Origin": origin})
    blocked = client.post(LOGIN, json=body, headers={"Origin": origin})
    assert blocked.status_code == 429
    return dict(blocked.headers)


def test_login_429_exposes_retry_after_to_the_allowed_origin(limited_client: TestClient) -> None:
    headers = block_login(limited_client, ALLOWED_ORIGIN)

    assert headers["access-control-allow-origin"] == ALLOWED_ORIGIN
    assert "retry-after" in headers
    assert "retry-after" in exposed_headers(headers)


def test_register_429_exposes_retry_after_to_the_allowed_origin(limited_client: TestClient) -> None:
    body = {"name": "Ana", "email": "not-an-email", "password": "a-very-long-password"}
    for _ in range(2):
        limited_client.post(REGISTER, json=body, headers={"Origin": ALLOWED_ORIGIN})
    blocked = limited_client.post(REGISTER, json=body, headers={"Origin": ALLOWED_ORIGIN})

    assert blocked.status_code == 429
    assert "retry-after" in exposed_headers(dict(blocked.headers))


def test_a_disallowed_origin_is_not_granted_access_even_on_a_429(
    limited_client: TestClient,
) -> None:
    headers = block_login(limited_client, OTHER_ORIGIN)

    # Without Access-Control-Allow-Origin a browser ignores every other CORS header (Starlette
    # still adds the credentials and expose headers for any Origin; that was already the case).
    assert "access-control-allow-origin" not in headers


def test_only_retry_after_is_exposed(limited_client: TestClient, make_user: MakeUser) -> None:
    user = make_user("ana@example.com")

    ok = limited_client.post(
        LOGIN,
        json={"email": user.email, "password": user.password},
        headers={"Origin": ALLOWED_ORIGIN},
    )

    assert ok.status_code == 200
    assert exposed_headers(dict(ok.headers)) == {"retry-after"}


def test_the_rest_of_the_cors_policy_is_unchanged(limited_client: TestClient) -> None:
    allowed = limited_client.options(
        LOGIN,
        headers={
            "Origin": ALLOWED_ORIGIN,
            "Access-Control-Request-Method": "POST",
            "Access-Control-Request-Headers": "authorization,content-type",
        },
    )
    refused = limited_client.options(
        LOGIN,
        headers={
            "Origin": OTHER_ORIGIN,
            "Access-Control-Request-Method": "POST",
            "Access-Control-Request-Headers": "authorization",
        },
    )

    assert allowed.status_code == 200
    assert allowed.headers["access-control-allow-origin"] == ALLOWED_ORIGIN
    assert allowed.headers["access-control-allow-credentials"] == "true"
    assert "POST" in allowed.headers["access-control-allow-methods"]
    assert allowed.headers["access-control-allow-headers"] == "authorization,content-type"
    assert refused.status_code == 400
    assert "access-control-allow-origin" not in refused.headers


def test_requests_without_an_origin_get_no_cors_headers(limited_client: TestClient) -> None:
    response = limited_client.post(LOGIN, json={"email": "a@b.co", "password": "wrong-password-xx"})

    assert "access-control-allow-origin" not in response.headers
    assert "access-control-expose-headers" not in response.headers
