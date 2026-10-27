"""Unexpected failures must not leak request data to logs (review findings F1 and F7)."""

import logging
from collections.abc import Iterator

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.exc import OperationalError

from app.core.config import Settings
from app.core.database import create_db_engine
from app.main import create_app
from tests.constants import TEST_JWT_SECRET

LEAKY = "leaky-email@example.com $argon2id$v=19$m=65536,t=3,p=4$abc"


@pytest.fixture
def client() -> Iterator[TestClient]:
    settings = Settings(
        database_url="postgresql+psycopg://u:p@localhost:5432/x_test",
        jwt_secret=TEST_JWT_SECRET,
    )
    app = create_app(settings)

    def boom() -> None:
        raise RuntimeError(f"DETAIL: Failing row contains ({LEAKY})")

    def outage() -> None:
        raise OperationalError("SELECT 1", {"host": "10.0.0.5"}, Exception("connection refused"))

    app.add_api_route("/test/boom", boom)
    app.add_api_route("/test/outage", outage)
    # Default raise_server_exceptions=True: a re-raised exception would fail the test, exactly as
    # a re-raised exception ends up in the server's error log with a traceback.
    with TestClient(app) as test_client:
        yield test_client


def test_engine_hides_sql_parameters() -> None:
    engine = create_db_engine("postgresql+psycopg://u:p@localhost:5432/x_test")

    assert engine.hide_parameters is True
    engine.dispose()


def test_unexpected_exception_is_answered_without_propagating_to_the_server(
    client: TestClient,
) -> None:
    response = client.get("/test/boom")

    assert response.status_code == 500
    assert response.json() == {"code": "INTERNAL_ERROR", "message": "Internal server error"}
    assert response.headers["x-content-type-options"] == "nosniff"


def test_unexpected_exception_logs_only_type_method_and_path(
    client: TestClient, caplog: pytest.LogCaptureFixture
) -> None:
    with caplog.at_level(logging.DEBUG):
        client.get("/test/boom")

    assert "RuntimeError" in caplog.text
    assert "/test/boom" in caplog.text
    assert "leaky-email" not in caplog.text
    assert "argon2id" not in caplog.text
    assert all(record.exc_info is None for record in caplog.records)


def test_database_outage_is_a_generic_503_on_any_endpoint(
    client: TestClient, caplog: pytest.LogCaptureFixture
) -> None:
    with caplog.at_level(logging.DEBUG):
        response = client.get("/test/outage")

    assert response.status_code == 503
    assert response.json()["code"] == "SERVICE_UNAVAILABLE"
    assert "10.0.0.5" not in response.text + caplog.text
    assert "connection refused" not in response.text
