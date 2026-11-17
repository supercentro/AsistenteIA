"""The API and the worker refuse to start as a superuser, against a real PostgreSQL (PG-01, 15.2).

A disposable cluster with the real roles. The decision is the server's answer about the effective
identity: a superuser with a harmless-looking name is refused, an unprivileged role with an
administrator-looking name is accepted, and `SET ROLE` to an unprivileged role does not hide the
superuser session. The production entry points are started as real processes.
"""

import os
import secrets
import subprocess
import sys
from collections.abc import Iterator
from pathlib import Path

import pytest
from sqlalchemy import event
from sqlalchemy.engine import Engine, make_url

from app.core.database import (
    SuperuserConnectionError,
    assert_restricted_database_role,
    create_db_engine,
)
from tests.constants import TEST_JWT_SECRET
from tests.db_admin_support import Cluster
from tests.db_admin_support import cluster as cluster  # noqa: F401  (fixture)
from tests.db_admin_support import scratch_database as scratch_database  # noqa: F401  (fixture)
from tests.db_roles_support import own_database as own_database
from tests.role_support import make_test_role_name
from tests.server_support import free_port

BACKEND_DIR = Path(__file__).resolve().parents[2]


def engine_for(url: str) -> Engine:
    return create_db_engine(url, 5)


@pytest.fixture
def decoy_roles(cluster: Cluster, own_database: str) -> Iterator[dict[str, tuple[str, str]]]:
    """A superuser named like a service role and an unprivileged role named like the admin."""
    password = secrets.token_urlsafe(24)
    names = {
        "super_with_a_service_name": make_test_role_name("app_looking_super"),
        "plain_with_an_admin_name": make_test_role_name("admin_looking_plain"),
    }
    with cluster.admin_connection() as conn:
        # The password is token_urlsafe (letters, digits, "-" and "_"): safe inside a literal.
        superuser, plain = names["super_with_a_service_name"], names["plain_with_an_admin_name"]
        conn.execute(f"CREATE ROLE \"{superuser}\" SUPERUSER LOGIN PASSWORD '{password}'")
        conn.execute(f"CREATE ROLE \"{plain}\" LOGIN PASSWORD '{password}'")
        conn.execute(
            f'GRANT CONNECT ON DATABASE "{own_database}" TO "{names["plain_with_an_admin_name"]}"'
        )
    try:
        yield {key: (name, password) for key, name in names.items()}
    finally:
        with cluster.admin_connection() as conn:
            for name in names.values():
                conn.execute(f'DROP OWNED BY "{name}"')
                conn.execute(f'DROP ROLE IF EXISTS "{name}"')


@pytest.mark.parametrize("logical", ["app", "worker"])
def test_the_service_roles_are_accepted(cluster: Cluster, own_database: str, logical: str) -> None:
    engine = engine_for(cluster.role_url(logical, own_database))
    try:
        assert_restricted_database_role(engine)
    finally:
        engine.dispose()


def test_the_administrator_is_refused(cluster: Cluster, own_database: str) -> None:
    engine = engine_for(cluster.admin(own_database))
    try:
        with pytest.raises(SuperuserConnectionError):
            assert_restricted_database_role(engine)
    finally:
        engine.dispose()


def test_a_superuser_with_a_service_name_is_refused(
    cluster: Cluster, own_database: str, decoy_roles: dict[str, tuple[str, str]]
) -> None:
    name, password = decoy_roles["super_with_a_service_name"]
    engine = engine_for(cluster.url(name, password, own_database))
    try:
        with pytest.raises(SuperuserConnectionError):
            assert_restricted_database_role(engine)
    finally:
        engine.dispose()


def test_an_unprivileged_role_with_an_administrator_name_is_accepted(
    cluster: Cluster, own_database: str, decoy_roles: dict[str, tuple[str, str]]
) -> None:
    name, password = decoy_roles["plain_with_an_admin_name"]
    engine = engine_for(cluster.url(name, password, own_database))
    try:
        assert_restricted_database_role(engine)
    finally:
        engine.dispose()


def test_set_role_to_an_unprivileged_role_does_not_hide_the_superuser_session(
    cluster: Cluster, own_database: str
) -> None:
    engine = engine_for(cluster.admin(own_database))
    target = cluster.names.app

    @event.listens_for(engine, "connect")
    def drop_privileges(dbapi_connection: object, _record: object) -> None:
        cursor = dbapi_connection.cursor()  # type: ignore[attr-defined]
        cursor.execute(f'SET ROLE "{target}"')
        cursor.close()

    try:
        with pytest.raises(SuperuserConnectionError):
            assert_restricted_database_role(engine)
    finally:
        engine.dispose()


def test_an_unreachable_database_is_refused_without_leaking_the_address() -> None:
    engine = create_db_engine("postgresql+psycopg://nobody:very-secret-x@127.0.0.1:1/none", 1)
    try:
        with pytest.raises(SuperuserConnectionError) as refused:
            assert_restricted_database_role(engine)
    finally:
        engine.dispose()

    assert "very-secret-x" not in str(refused.value)
    assert "127.0.0.1" not in str(refused.value)


# --- the production entry points, as real processes -----------------------------------------


def run_entry_point(code: str, env: dict[str, str]) -> subprocess.CompletedProcess[str]:
    return subprocess.run(  # noqa: S603 - fixed arguments, test-only
        [sys.executable, "-c", code],
        capture_output=True,
        text=True,
        cwd=BACKEND_DIR,
        env={"PATH": os.environ.get("PATH", ""), "PYTHONPATH": str(BACKEND_DIR), **env},
        timeout=90,
        check=False,
    )


API_CODE = "from app.main import app_factory; app_factory(); print('started')"


def api_env(url: str, **extra: str) -> dict[str, str]:
    return {
        "DATABASE_URL": url,
        "JWT_SECRET": TEST_JWT_SECRET,
        "APP_ENV": "development",
        "LLM_BACKEND": "fake",
        "ALLOW_FAKE_LLM": "true",
        "EMBEDDER_BACKEND": "fake",
        "ALLOW_FAKE_EMBEDDER": "true",
        "CORS_ORIGINS": "http://localhost:5173",
        **extra,
    }


def test_the_api_process_refuses_to_start_as_the_administrator(
    cluster: Cluster, own_database: str
) -> None:
    result = run_entry_point(API_CODE, api_env(cluster.admin(own_database)))

    assert result.returncode != 0
    assert "started" not in result.stdout
    assert "superuser" in result.stderr.lower()
    password = make_url(cluster.admin(own_database)).password
    assert password is not None
    assert password not in result.stdout + result.stderr


def test_the_api_process_starts_as_its_own_role(cluster: Cluster, own_database: str) -> None:
    result = run_entry_point(API_CODE, api_env(cluster.role_url("app", own_database)))

    assert result.returncode == 0, result.stderr
    assert "started" in result.stdout


def test_the_test_exception_lets_a_test_process_start_as_the_owner(
    cluster: Cluster, own_database: str
) -> None:
    env = api_env(cluster.admin(own_database), APP_ENV="test", ALLOW_SUPERUSER_DATABASE_ROLE="true")

    assert run_entry_point(API_CODE, env).returncode == 0


def test_the_exception_is_rejected_outside_the_test_environment(
    cluster: Cluster, own_database: str
) -> None:
    env = api_env(cluster.admin(own_database), ALLOW_SUPERUSER_DATABASE_ROLE="true")

    result = run_entry_point(API_CODE, env)

    assert result.returncode != 0
    assert "started" not in result.stdout


@pytest.mark.skipif(not sys.platform.startswith("linux"), reason="the worker runs on Linux only")
def test_the_worker_process_refuses_to_start_as_the_administrator(
    cluster: Cluster, own_database: str
) -> None:
    env = {
        "DATABASE_URL": cluster.admin(own_database),
        "APP_ENV": "development",
        "EMBEDDER_BACKEND": "fake",
        "ALLOW_FAKE_EMBEDDER": "true",
    }
    result = run_entry_point("import sys; from app.worker import main; sys.exit(main())", env)

    assert result.returncode == 2
    assert "superuser" in (result.stdout + result.stderr).lower()


def test_uvicorn_with_the_production_arguments_does_not_serve_as_the_administrator(
    cluster: Cluster, own_database: str
) -> None:
    """The factory exception stops the real server: it exits instead of listening (R3)."""
    env = api_env(cluster.admin(own_database))
    command = [
        sys.executable,
        "-m",
        "uvicorn",
        "app.main:app_factory",
        "--factory",
        "--no-proxy-headers",
        "--host",
        "127.0.0.1",
        "--port",
        str(free_port()),
    ]
    result = subprocess.run(  # noqa: S603 - fixed arguments, test-only
        command,
        capture_output=True,
        text=True,
        cwd=BACKEND_DIR,
        env={"PATH": os.environ.get("PATH", ""), "PYTHONPATH": str(BACKEND_DIR), **env},
        timeout=90,
        check=False,
    )

    assert result.returncode != 0
    assert "Uvicorn running" not in result.stdout + result.stderr
    assert "superuser" in (result.stdout + result.stderr).lower()
