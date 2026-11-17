"""What a failed commit looks like to the client, and which routes may write.

Task 15.2, findings F-1, B-1, F-2 and F-3.

- Every write route is classified here: a new `POST`, `PUT`, `PATCH` or `DELETE` fails the inventory
  until someone decides how it commits (TD-039: the `get_db` commit runs after the response).
- A refused commit is the standard 500, a connection lost at commit is the standard 503, and neither
  body carries SQL, parameters, addresses or credentials. The real exception handlers are used.
- The contract documents both answers for every operation that commits explicitly.
"""

import ast
from pathlib import Path
from typing import Any

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy.exc import IntegrityError, InterfaceError, OperationalError, ProgrammingError

from app.api.transaction import commit_or_rollback
from app.core.config import Settings
from app.core.error_middleware import UnhandledErrorMiddleware
from app.core.handlers import register_exception_handlers
from app.main import create_app
from tests.contract_support import load_spec

ENDPOINTS = Path(__file__).resolve().parents[2] / "app" / "api" / "v1" / "endpoints"
PREFIX = "/api/v1"

COMMITS = "commit_or_rollback before the response"
READ_ONLY = "reads only; the post-response commit has nothing to write"
OWN_SESSION = "its own session commits in the upload; every database error is a 503"
PERSIST_PHASE = (
    "the persist phase, in a new session, commits with the shared helper before the response"
)

# Every operation that is not a GET: how it commits. A new operation must be added here with its
# reason, which is the point of the test (finding F-3, TD-039).
WRITE_OPERATIONS: dict[tuple[str, str], str] = {
    ("POST", "/auth/register"): COMMITS,
    ("POST", "/auth/login"): READ_ONLY,
    ("POST", "/users/me/consent"): COMMITS,
    ("POST", "/subjects"): COMMITS,
    ("DELETE", "/subjects/{subject_id}"): COMMITS,
    ("POST", "/subjects/{subject_id}/enrollments"): COMMITS,
    ("DELETE", "/subjects/{subject_id}/enrollments/{student_id}"): COMMITS,
    ("POST", "/subjects/{subject_id}/documents"): OWN_SESSION,
    ("DELETE", "/subjects/{subject_id}/documents/{document_id}"): COMMITS,
    ("POST", "/chat"): PERSIST_PHASE,
    ("DELETE", "/conversations/{conversation_id}"): COMMITS,
    ("DELETE", "/users/me/conversations"): COMMITS,
}
# The handler names behind them (AST scan of the endpoint modules).
HANDLERS: dict[str, str] = {
    "auth.register": COMMITS,
    "auth.login": READ_ONLY,
    "users.record_consent": COMMITS,
    "subjects.create_subject": COMMITS,
    "subjects.delete_subject": COMMITS,
    "enrollments.enroll_student": COMMITS,
    "enrollments.remove_enrollment": COMMITS,
    "documents.upload_document": OWN_SESSION,
    "documents.delete_document": COMMITS,
    "chat.ask_question": PERSIST_PHASE,
    "conversations.delete_conversation": COMMITS,
    "users.delete_all_conversations": COMMITS,
}
SECRET = "very-secret-credential"
ERROR_TEXT = f"connection to server at 10.1.2.3 failed for user admin password {SECRET}"


def settings() -> Settings:
    return Settings(
        database_url=f"postgresql+psycopg://u:{SECRET}@h/d",
        jwt_secret="Zq8!vN3#rT6&wK1@mX9$pL4^bC7*dF2_hG5+yJ0",
        cors_origins=["http://x"],
        embedder_backend="fake",
        app_env="test",
    )


def declared_operations() -> set[tuple[str, str]]:
    document = create_app(settings()).openapi()
    return {
        (method.upper(), path.removeprefix(PREFIX))
        for path, item in document["paths"].items()
        for method in item
        if method.upper() != "GET"
    }


def test_every_write_operation_is_classified() -> None:
    declared = declared_operations()

    assert declared - set(WRITE_OPERATIONS) == set(), "classify the new operation in this test"
    assert set(WRITE_OPERATIONS) - declared == set(), (
        "the inventory lists an operation that is gone"
    )


def write_handlers() -> dict[str, ast.FunctionDef | ast.AsyncFunctionDef]:
    found: dict[str, ast.FunctionDef | ast.AsyncFunctionDef] = {}
    for path in sorted(ENDPOINTS.glob("*.py")):
        tree = ast.parse(path.read_text(encoding="utf-8"))
        for node in ast.walk(tree):
            if not isinstance(node, ast.FunctionDef | ast.AsyncFunctionDef):
                continue
            for decorator in node.decorator_list:
                if (
                    isinstance(decorator, ast.Call)
                    and isinstance(decorator.func, ast.Attribute)
                    and isinstance(decorator.func.value, ast.Name)
                    and decorator.func.value.id == "router"
                    and decorator.func.attr in {"post", "put", "patch", "delete"}
                ):
                    found[f"{path.stem}.{node.name}"] = node
    return found


def test_every_write_handler_is_classified() -> None:
    assert set(write_handlers()) == set(HANDLERS)


@pytest.mark.parametrize("name", [n for n, how in HANDLERS.items() if how == COMMITS])
def test_a_handler_that_stores_something_commits_with_the_shared_helper(name: str) -> None:
    handler = write_handlers()[name]
    calls = [
        node.func.id
        for node in ast.walk(handler)
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Name)
    ]
    attributes = [
        node.func.attr
        for node in ast.walk(handler)
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute)
    ]

    assert "commit_or_rollback" in calls, f"{name} must use the shared helper"
    assert "commit" not in attributes, f"{name} must not call a bare commit()"


def test_the_chat_persist_phase_commits_with_the_shared_helper_and_never_bare() -> None:
    tree = ast.parse((ENDPOINTS / "chat.py").read_text(encoding="utf-8"))
    phase = next(
        node
        for node in ast.walk(tree)
        if isinstance(node, ast.FunctionDef) and node.name == "_persist_phase"
    )
    calls = [
        node.func.id
        for node in ast.walk(phase)
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Name)
    ]
    attributes = [
        node.func.attr
        for node in ast.walk(phase)
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute)
    ]
    assert "commit_or_rollback" in calls
    assert "commit" not in attributes


# --- what the client sees ---------------------------------------------------------------------


class _Session:
    def __init__(self, error: Exception) -> None:
        self.error = error
        self.rolled_back = False

    def commit(self) -> None:
        raise self.error

    def rollback(self) -> None:
        self.rolled_back = True


def app_failing_with(error: Exception) -> tuple[TestClient, _Session]:
    session = _Session(error)
    app = FastAPI()
    app.add_middleware(UnhandledErrorMiddleware)
    register_exception_handlers(app)

    @app.post("/write")
    def write() -> dict[str, str]:
        commit_or_rollback(session)  # type: ignore[arg-type]
        return {"status": "stored"}

    return TestClient(app, raise_server_exceptions=False), session


def lost_connection() -> Exception:
    return OperationalError("COMMIT", {"p": SECRET}, Exception(ERROR_TEXT))


def refused_write() -> Exception:
    return ProgrammingError("COMMIT", {"p": SECRET}, Exception(ERROR_TEXT))


def constraint_violation() -> Exception:
    return IntegrityError("INSERT", {"p": SECRET}, Exception(ERROR_TEXT))


@pytest.mark.parametrize(
    "make", [lost_connection, lambda: InterfaceError("COMMIT", {}, Exception(ERROR_TEXT))]
)
def test_a_connection_lost_at_commit_is_a_503_with_the_fixed_body(make: Any) -> None:
    client, session = app_failing_with(make())

    response = client.post("/write")

    assert response.status_code == 503
    assert response.json()["code"] == "SERVICE_UNAVAILABLE"
    assert session.rolled_back
    for text in (SECRET, "10.1.2.3", "admin", "COMMIT"):
        assert text not in response.text


@pytest.mark.parametrize("make", [refused_write, constraint_violation])
def test_a_write_refused_at_commit_is_a_500_with_the_fixed_body(make: Any) -> None:
    client, session = app_failing_with(make())

    response = client.post("/write")

    assert response.status_code == 500
    assert response.json()["code"] == "INTERNAL_ERROR"
    assert session.rolled_back
    for text in (SECRET, "10.1.2.3", "admin", "INSERT", "COMMIT"):
        assert text not in response.text


def test_a_constraint_violation_is_not_reported_as_a_transient_outage() -> None:
    """The distinction asked for in F-2: only a lost connection says 'try again later'."""
    client, _ = app_failing_with(constraint_violation())

    assert client.post("/write").status_code != 503


# --- the contract -----------------------------------------------------------------------------

COMMITTING_OPERATIONS = [key for key, how in WRITE_OPERATIONS.items() if how == COMMITS]


@pytest.mark.parametrize(("method", "path"), COMMITTING_OPERATIONS)
def test_the_contract_documents_the_500_and_the_503_of_every_committing_operation(
    method: str, path: str
) -> None:
    responses = load_spec()["paths"][path][method.lower()]["responses"]

    assert responses["500"] == {"$ref": "#/components/responses/InternalError"}
    assert responses["503"] == {"$ref": "#/components/responses/ServiceUnavailable"}


def test_the_500_does_not_claim_that_nothing_was_stored_in_every_case() -> None:
    description = str(load_spec()["components"]["responses"]["InternalError"]["description"])

    assert "nothing was stored or removed and the client may retry" not in description
    assert "after a successful commit" in description  # the error that follows a stored write
    assert "rolled back" in description


def test_the_503_says_the_outcome_may_be_unknown_when_the_commit_was_lost() -> None:
    description = str(load_spec()["components"]["responses"]["ServiceUnavailable"]["description"])

    assert "uncertain" in description
    assert "read the resource" in description
