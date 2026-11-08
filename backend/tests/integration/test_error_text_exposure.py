"""Spike incident I2: database error text carries row data and must never reach logs or clients."""

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import text
from sqlalchemy.exc import DBAPIError

from app.core.database import create_db_engine
from tests.integration.helpers import build_app
from tests.leak_support import (
    CONTENT_MARKER,
    EMBEDDING_MARKER,
    ROW_DETAIL_MARKER,
    Violation,
    build_violations,
    spy_on_logs,
)

FORBIDDEN = (CONTENT_MARKER, EMBEDDING_MARKER, ROW_DETAIL_MARKER)


def violation_named(violations: list[Violation], name: str) -> Violation:
    return next(v for v in violations if v.name == name)


def test_precondition_database_messages_really_carry_row_data(clean_db: str) -> None:
    """If this fails the leak tests below prove nothing: the DETAIL must contain the data."""
    violations = build_violations(clean_db)

    with pytest.raises(DBAPIError) as raised:
        violation_named(violations, "check_violation").execute()
    original = str(raised.value.orig)
    assert ROW_DETAIL_MARKER in original
    assert CONTENT_MARKER in original
    assert EMBEDDING_MARKER in original

    with pytest.raises(DBAPIError) as raised_fk:
        violation_named(violations, "foreign_key_violation").execute()
    assert "Key (document_id, subject_id)" in str(raised_fk.value.orig)  # identifiers, no text


def test_sqlalchemy_error_text_does_not_render_bound_parameters(clean_db: str) -> None:
    engine = create_db_engine(clean_db)  # the application engine (hide_parameters=True)
    try:
        with pytest.raises(DBAPIError) as raised, engine.begin() as conn:
            conn.execute(text("SELECT CAST(:v AS integer)"), {"v": CONTENT_MARKER})
    finally:
        engine.dispose()

    assert "[parameters:" not in str(raised.value)


@pytest.mark.parametrize(
    "name",
    [
        "check_violation",
        "foreign_key_violation",
        "unique_violation",
        "wrong_dimension",
        "blank_content",
        "bad_parameter",
    ],
)
def test_application_never_logs_or_returns_database_error_text(clean_db: str, name: str) -> None:
    violations = build_violations(clean_db)
    violation = violation_named(violations, name)
    app = build_app(clean_db)

    def probe() -> dict[str, str]:
        violation.execute()
        return {"status": "no error"}

    app.add_api_route("/_probe", probe, methods=["GET"])

    with spy_on_logs() as spy, TestClient(app, raise_server_exceptions=False) as client:
        response = client.get("/_probe")

    assert response.status_code == 500
    assert response.json() == {"code": "INTERNAL_ERROR", "message": "Internal server error"}
    for marker in FORBIDDEN:
        assert marker not in response.text, f"{marker} reached the response"
        assert marker not in spy.text, f"{marker} reached the logs"
    assert "unhandled exception" in spy.text  # the failure itself is still logged, by type only
