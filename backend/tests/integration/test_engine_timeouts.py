"""Connection timeouts of the worker engine (change 6, design A10)."""

import pytest
from sqlalchemy import text

from app.core.database import create_db_engine


def show(url: str, name: str, **kwargs: int) -> str:
    engine = create_db_engine(url, **kwargs)
    try:
        with engine.connect() as conn:
            return str(conn.execute(text(f"SHOW {name}")).scalar_one())
    finally:
        engine.dispose()


def test_the_worker_engine_sets_statement_and_idle_in_transaction_timeouts(
    clean_db: str,
) -> None:
    kwargs = {"statement_timeout_seconds": 60, "idle_in_transaction_timeout_seconds": 30}

    assert show(clean_db, "statement_timeout", **kwargs) == "1min"
    assert show(clean_db, "idle_in_transaction_session_timeout", **kwargs) == "30s"


def test_without_options_the_engine_keeps_the_server_defaults(clean_db: str) -> None:
    assert show(clean_db, "statement_timeout") == "0"


def test_a_statement_over_the_timeout_is_cancelled(clean_db: str) -> None:
    engine = create_db_engine(clean_db, statement_timeout_seconds=1)
    try:
        with engine.connect() as conn, pytest.raises(Exception, match="statement timeout"):
            conn.execute(text("SELECT pg_sleep(3)"))
    finally:
        engine.dispose()
