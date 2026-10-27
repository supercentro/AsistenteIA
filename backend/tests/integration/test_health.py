import socket
import time

from fastapi.testclient import TestClient

from app.core.config import Settings
from app.main import create_app


def make_client(database_url: str) -> TestClient:
    settings = Settings(database_url=database_url, cors_origins=["http://localhost:5173"])
    return TestClient(create_app(settings), raise_server_exceptions=False)


def test_health_returns_200_ok_without_token(test_db_url: str) -> None:
    with make_client(test_db_url) as client:
        response = client.get("/api/v1/health")

    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


def test_health_body_contains_only_status(test_db_url: str) -> None:
    with make_client(test_db_url) as client:
        response = client.get("/api/v1/health")

    assert set(response.json()) == {"status"}


def test_health_returns_503_error_body_when_database_is_unreachable() -> None:
    unreachable = (
        "postgresql+psycopg://user:hidden-pw@127.0.0.1:1/unreachable_test?connect_timeout=2"
    )

    with make_client(unreachable) as client:
        response = client.get("/api/v1/health")

    assert response.status_code == 503
    assert response.json() == {"code": "SERVICE_UNAVAILABLE", "message": "Service unavailable"}
    for leaked in ("127.0.0.1", "hidden-pw", "psycopg", "Traceback"):
        assert leaked not in response.text


def test_health_is_the_only_documented_api_path(test_db_url: str) -> None:
    with make_client(test_db_url) as client:
        paths = set(client.app.openapi()["paths"])  # type: ignore[attr-defined]

    assert paths == {"/api/v1/health"}


def test_health_returns_503_quickly_when_database_never_answers() -> None:
    """A server that accepts TCP but never speaks PostgreSQL must not hang /health."""
    with socket.socket() as silent:
        silent.bind(("127.0.0.1", 0))
        silent.listen(5)
        port = silent.getsockname()[1]
        settings = Settings(
            database_url=f"postgresql+psycopg://u:p@127.0.0.1:{port}/silent_test",
            db_connect_timeout_seconds=1,
            cors_origins=["http://localhost:5173"],
        )

        with TestClient(create_app(settings), raise_server_exceptions=False) as client:
            started = time.monotonic()
            response = client.get("/api/v1/health")
            elapsed = time.monotonic() - started

    assert response.status_code == 503
    assert elapsed < 5
