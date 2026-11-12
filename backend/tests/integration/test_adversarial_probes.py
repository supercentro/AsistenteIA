"""Adversarial probes found during the security review of auth-and-roles."""

import json
from concurrent.futures import ThreadPoolExecutor

import pytest
from fastapi.testclient import TestClient
from httpx2 import Response

from tests.integration.helpers import DEFAULT_PASSWORD, build_app

REGISTER = "/api/v1/auth/register"


def post_escaped_json(client: TestClient, url: str, payload: dict[str, object]) -> Response:
    """Send JSON with every non-ASCII character escaped, so lone surrogates reach the server."""
    response: Response = client.post(
        url,
        content=json.dumps(payload, ensure_ascii=True),
        headers={"Content-Type": "application/json"},
    )
    return response


def body(**overrides: object) -> dict[str, object]:
    base: dict[str, object] = {
        "name": "Probe",
        "email": "probe@example.com",
        "password": DEFAULT_PASSWORD,
    }
    base.update(overrides)
    return base


@pytest.mark.parametrize(
    "overrides",
    [
        {"name": "a\u0000b"},
        {"name": "\ud800"},
        {"name": "tab\tname"},
        {"name": "line\nbreak"},
        {"name": "bell\u0007"},
        {"email": "İstanbul@example.com"},
        {"email": "ünï@example.com"},
        {"email": "ｕｓｅｒ@example.com"},
        {"email": "user\u0000@example.com"},
        {"password": "p\u0000" + "x" * 12},
        {"password": "\ud800" + "x" * 12},
    ],
    ids=[
        "nul-in-name",
        "lone-surrogate-name",
        "tab-in-name",
        "newline-in-name",
        "control-in-name",
        "dotted-capital-i-email",
        "non-ascii-email",
        "fullwidth-email",
        "nul-in-email",
        "nul-in-password",
        "surrogate-password",
    ],
)
def test_register_never_answers_500_for_odd_input(
    client: TestClient, overrides: dict[str, object]
) -> None:
    response = post_escaped_json(client, REGISTER, body(**overrides))

    assert response.status_code in (201, 422), response.text


def test_login_never_answers_500_for_odd_input(client: TestClient) -> None:
    for email, password in (
        ("probe@example.com", "p\u0000x"),
        ("probe@example.com", "\ud800"),
        ("İstanbul@example.com", "x" * 12),
        ("a\u0000@example.com", "x" * 12),
    ):
        response = post_escaped_json(
            client, "/api/v1/auth/login", {"email": email, "password": password}
        )

        assert response.status_code in (401, 422), (email, response.text)


def test_concurrent_registrations_of_the_same_email_yield_one_account_and_no_500(
    clean_db: str,
) -> None:
    app = build_app(clean_db)

    def register(_: int) -> int:
        with TestClient(app, raise_server_exceptions=False) as client:
            return int(client.post(REGISTER, json=body(email="race@example.com")).status_code)

    with ThreadPoolExecutor(max_workers=6) as pool:
        statuses = sorted(pool.map(register, range(6)))

    assert statuses.count(201) == 1
    assert set(statuses) <= {201, 409}
