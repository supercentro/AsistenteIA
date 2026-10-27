"""Regression tests for the independent adversarial review of auth-and-roles."""

import json
import os
import re
import socket
import subprocess
import sys
import time
from collections.abc import Iterator
from pathlib import Path

import httpx
import pytest
from fastapi.testclient import TestClient
from sqlalchemy import text
from sqlalchemy.exc import DBAPIError

from app.core.database import create_db_engine
from tests.constants import TEST_JWT_SECRET
from tests.integration.helpers import DEFAULT_PASSWORD, build_app

REPO_ROOT = Path(__file__).resolve().parents[3]
BACKEND_DIR = REPO_ROOT / "backend"


# ------------------------------------------------------------------ F1 / F7


def test_statement_error_text_does_not_contain_the_bound_parameters(clean_db: str) -> None:
    engine = create_db_engine(clean_db)
    hash_value = "$argon2id$v=19$m=8,t=1,p=1$secret-hash-value"
    try:
        with pytest.raises(DBAPIError) as exc, engine.begin() as conn:
            conn.execute(
                text(
                    "INSERT INTO users (name, email, password_hash, role) "
                    "VALUES (:n, :e, :h, 'admin')"
                ),
                {"n": "Name", "e": "leak.me@example.com", "h": hash_value},
            )
    finally:
        engine.dispose()

    rendered = str(exc.value)
    assert "leak.me@example.com" not in rendered
    assert hash_value not in rendered


@pytest.mark.parametrize("path", ["/api/v1/auth/login", "/api/v1/auth/register"])
def test_database_outage_on_auth_endpoints_is_503(path: str) -> None:
    unreachable = "postgresql+psycopg://u:hidden-pw@127.0.0.1:1/unreachable_test"
    from app.main import create_app
    from tests.integration.helpers import build_settings

    settings = build_settings(unreachable, db_connect_timeout_seconds=1)
    body = {"name": "N", "email": "outage@example.com", "password": DEFAULT_PASSWORD}
    with TestClient(create_app(settings)) as client:
        response = client.post(path, json=body)

    assert response.status_code == 503
    assert response.json()["code"] == "SERVICE_UNAVAILABLE"
    for leaked in ("127.0.0.1", "hidden-pw", "outage@example.com", "psycopg"):
        assert leaked not in response.text


# ----------------------------------------------------------------------- F3


@pytest.mark.parametrize(
    "name",
    ["a b", "a b", "a‮b", "a‪b", "a⁦b", "a⁩b", "a‎b", "a‏b"],
    ids=["ls", "ps", "rlo", "lre", "lri", "pdi", "lrm", "rlm"],
)
def test_register_rejects_line_separators_and_bidi_controls_in_names(
    client: TestClient, name: str
) -> None:
    response = client.post(
        "/api/v1/auth/register",
        json={"name": name, "email": "bidi@example.com", "password": DEFAULT_PASSWORD},
    )

    assert response.status_code == 422


@pytest.mark.parametrize(
    "name", ["Ana María", "李雷", "نام‌خانوادگی", "👩‍🏫 Teacher", "O'Brien-Smith"]
)
def test_register_still_accepts_legitimate_international_names(
    client: TestClient, name: str
) -> None:
    response = client.post(
        "/api/v1/auth/register",
        json={
            "name": name,
            "email": f"n{abs(hash(name))}@example.com",
            "password": DEFAULT_PASSWORD,
        },
    )

    assert response.status_code == 201, name


# ----------------------------------------------------------------------- F2


def dockerfile_command() -> list[str]:
    source = (BACKEND_DIR / "Dockerfile").read_text(encoding="utf-8")
    match = re.search(r"^CMD (\[.*\])\s*$", source, re.MULTILINE)
    assert match, "CMD not found in backend/Dockerfile"
    command: list[str] = json.loads(match.group(1))
    return command


def test_default_server_commands_disable_proxy_headers() -> None:
    assert "--no-proxy-headers" in dockerfile_command()
    compose = (REPO_ROOT / "docker-compose.yml").read_text(encoding="utf-8")
    assert '"--no-proxy-headers"' in compose


def free_port() -> int:
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        return int(sock.getsockname()[1])


@pytest.fixture
def real_server(clean_db: str, tmp_path: Path) -> Iterator[str]:
    """The real Uvicorn started with the Dockerfile's own arguments, on loopback."""
    port = free_port()
    command = [
        "127.0.0.1" if arg == "0.0.0.0" else str(port) if arg == "8000" else arg  # noqa: S104
        for arg in dockerfile_command()
    ]
    command[0:1] = [sys.executable, "-m", "uvicorn"]
    env = {
        "PYTHONPATH": str(BACKEND_DIR),
        "DATABASE_URL": clean_db,
        "JWT_SECRET": TEST_JWT_SECRET,
        "APP_ENV": "test",
        "LOGIN_RATE_LIMIT": "2/minute",
        "REGISTER_RATE_LIMIT": "2/minute",
    }
    env.update(
        {
            key: value
            for key, value in os.environ.items()
            if key in {"PATH", "SYSTEMROOT", "SYSTEMDRIVE", "TEMP", "TMP", "HOME", "USERPROFILE"}
        }
    )
    log_file = (tmp_path / "server.log").open("w+")
    process = subprocess.Popen(  # noqa: S603
        command, env=env, cwd=tmp_path, stdout=log_file, stderr=subprocess.STDOUT
    )
    base = f"http://127.0.0.1:{port}/api/v1"
    try:
        for _ in range(80):
            try:
                if httpx.get(f"{base}/health", timeout=1).status_code == 200:
                    break
            except httpx.TransportError:
                time.sleep(0.25)
        else:
            log_file.seek(0)
            pytest.fail("the real server did not start: " + log_file.read()[-1500:])
        yield base
    finally:
        process.terminate()
        process.wait(timeout=15)
        log_file.close()


def test_rotating_forwarding_headers_do_not_bypass_the_login_limit(real_server: str) -> None:
    statuses = [
        httpx.post(
            f"{real_server}/auth/login",
            json={"email": "ghost@example.com", "password": "wrong-password-1"},
            headers={
                "X-Forwarded-For": f"203.0.113.{i}",
                "Forwarded": f"for=192.0.2.{i}",
                "X-Real-IP": f"198.51.100.{i}",
            },
            timeout=10,
        ).status_code
        for i in range(1, 6)
    ]

    assert statuses == [401, 401, 429, 429, 429]


def test_rotating_forwarding_headers_do_not_bypass_the_register_limit(real_server: str) -> None:
    statuses = [
        httpx.post(
            f"{real_server}/auth/register",
            json={"name": "N", "email": f"u{i}@example.com", "password": DEFAULT_PASSWORD},
            headers={"X-Forwarded-For": f"203.0.113.{i}"},
            timeout=10,
        ).status_code
        for i in range(1, 6)
    ]

    assert statuses == [201, 201, 429, 429, 429]


def test_app_factory_import_is_used_by_the_dockerfile() -> None:
    assert "app.main:app_factory" in dockerfile_command()
    assert build_app is not None
