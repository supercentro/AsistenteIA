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
        embedder_backend="fake",
        app_env="test",
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


# --- Finding P2 of the Codex review of 6e85470 (task 19.3.4): API and worker start-up ---

FRAGMENT = "Zq9-frag-secret"
MALFORMED = {
    "unescaped-at-in-password": f"postgresql+psycopg://app_user:pre@part:{FRAGMENT}@db/app",
    "malformed-port": "postgresql+psycopg://app_user:Pw-long-enough-123@db:notaport/app",
}
FORBIDDEN = (FRAGMENT, "Pw-long-enough-123", "notaport", "invalid literal", "int()", "app_user")


def assert_value_free(error: BaseException, url: str) -> None:
    """Nothing of the value, and no chained exception that a traceback would print."""
    message = str(error)
    assert url not in message
    for forbidden in FORBIDDEN:
        assert forbidden not in message, "the message holds part of the value or an internal text"
    assert error.__cause__ is None and error.__suppress_context__ is True


@pytest.mark.parametrize("case", [*MALFORMED, "not-a-url"])
def test_the_engine_rejects_a_malformed_url_without_leaking_any_part_of_it(case: str) -> None:
    url = MALFORMED.get(case, "this is not a url")

    with pytest.raises(ValueError) as caught:
        create_db_engine(url)

    assert_value_free(caught.value, url)


def test_the_engine_still_opens_for_a_valid_url_and_reports_operational_errors() -> None:
    engine = create_db_engine("postgresql+psycopg://u:p@127.0.0.1:1/x_test", 1)

    with pytest.raises(OperationalError):
        engine.connect()
    engine.dispose()
