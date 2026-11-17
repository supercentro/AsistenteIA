from collections.abc import Iterator

import pytest
from fastapi.testclient import TestClient
from pydantic import BaseModel

from app.core.config import Settings
from app.core.errors import ConflictError, ForbiddenError, NotFoundError, UnauthorizedError
from app.main import create_app
from tests.constants import TEST_JWT_SECRET

SECURE_HEADERS = {
    "x-content-type-options": "nosniff",
    "x-frame-options": "DENY",
    "referrer-policy": "no-referrer",
}


class Payload(BaseModel):
    name: str
    age: int


@pytest.fixture
def client() -> Iterator[TestClient]:
    settings = Settings(
        jwt_secret=TEST_JWT_SECRET,
        database_url="postgresql+psycopg://u:p@localhost:5432/asistenteia",
        cors_origins=["http://localhost:5173"],
        google_api_key="AIza-test-key-for-unit-tests-only",
        embedder_backend="fake",
        app_env="test",
    )
    app = create_app(settings)

    def not_found() -> None:
        raise NotFoundError("thing not found")

    def forbidden() -> None:
        raise ForbiddenError("not allowed")

    def conflict() -> None:
        raise ConflictError("already exists")

    def unauthorized() -> None:
        raise UnauthorizedError("login required")

    def boom() -> None:
        raise RuntimeError("secret-internal-detail /srv/app.py SELECT * FROM users")

    def create(payload: Payload) -> Payload:
        return payload

    app.add_api_route("/test/not-found", not_found)
    app.add_api_route("/test/forbidden", forbidden)
    app.add_api_route("/test/conflict", conflict)
    app.add_api_route("/test/unauthorized", unauthorized)
    app.add_api_route("/test/boom", boom)
    app.add_api_route("/test/create", create, methods=["POST"])

    with TestClient(app, raise_server_exceptions=False) as test_client:
        yield test_client


def assert_error_body(body: dict[str, object], code: str) -> None:
    assert body["code"] == code
    assert isinstance(body["message"], str)


def test_unknown_route_returns_404_error_body(client: TestClient) -> None:
    response = client.get("/api/v1/does-not-exist")

    assert response.status_code == 404
    assert_error_body(response.json(), "NOT_FOUND")


@pytest.mark.parametrize(
    ("path", "status", "code"),
    [
        ("/test/not-found", 404, "NOT_FOUND"),
        ("/test/forbidden", 403, "FORBIDDEN"),
        ("/test/conflict", 409, "CONFLICT"),
        ("/test/unauthorized", 401, "UNAUTHORIZED"),
    ],
)
def test_domain_errors_are_mapped_to_status_and_code(
    client: TestClient, path: str, status: int, code: str
) -> None:
    response = client.get(path)

    assert response.status_code == status
    assert_error_body(response.json(), code)


def test_validation_error_lists_fields_without_echoing_values(client: TestClient) -> None:
    response = client.post("/test/create", json={"name": "super-secret-value", "age": "not-int"})

    body = response.json()
    assert response.status_code == 422
    assert_error_body(body, "VALIDATION_ERROR")
    assert any("age" in item["field"] for item in body["details"]["errors"])
    assert "super-secret-value" not in response.text
    assert "not-int" not in response.text


def test_unhandled_exception_returns_generic_500_without_internals(client: TestClient) -> None:
    response = client.get("/test/boom")

    assert response.status_code == 500
    assert_error_body(response.json(), "INTERNAL_ERROR")
    for leaked in ("secret-internal-detail", "SELECT", "app.py", "Traceback"):
        assert leaked not in response.text


def test_unhandled_exception_logs_no_message_content(
    client: TestClient, caplog: pytest.LogCaptureFixture
) -> None:
    with caplog.at_level("ERROR"):
        client.get("/test/boom")

    assert "secret-internal-detail" not in caplog.text
    assert "RuntimeError" in caplog.text


@pytest.mark.parametrize("path", ["/api/v1/does-not-exist", "/test/forbidden", "/test/boom"])
def test_secure_headers_are_present_on_error_responses(client: TestClient, path: str) -> None:
    response = client.get(path)

    for name, value in SECURE_HEADERS.items():
        assert response.headers[name] == value


def test_secure_headers_are_present_on_success(client: TestClient) -> None:
    response = client.post("/test/create", json={"name": "a", "age": 1})

    assert response.status_code == 200
    for name, value in SECURE_HEADERS.items():
        assert response.headers[name] == value


def test_cors_allows_configured_origin(client: TestClient) -> None:
    response = client.get("/test/forbidden", headers={"Origin": "http://localhost:5173"})

    assert response.headers["access-control-allow-origin"] == "http://localhost:5173"


def test_cors_does_not_allow_other_origin(client: TestClient) -> None:
    response = client.get("/test/forbidden", headers={"Origin": "http://evil.example"})

    assert "access-control-allow-origin" not in response.headers
