from collections.abc import Iterator
from typing import Annotated

import pytest
from fastapi import Depends
from fastapi.testclient import TestClient
from sqlalchemy import text
from sqlalchemy.orm import Session

from app.api.deps import get_db
from app.core.config import Settings
from app.main import create_app
from tests.db_support import guarded_engine


@pytest.fixture
def probe_table(test_db_url: str) -> Iterator[None]:
    with guarded_engine(test_db_url) as engine, engine.connect() as conn:
        conn.execute(text("CREATE TABLE tx_probe (id serial PRIMARY KEY, label text NOT NULL)"))
    yield
    with guarded_engine(test_db_url) as engine, engine.connect() as conn:
        conn.execute(text("DROP TABLE IF EXISTS tx_probe"))


def count_rows(test_db_url: str) -> int:
    with guarded_engine(test_db_url) as engine, engine.connect() as conn:
        return int(conn.execute(text("SELECT count(*) FROM tx_probe")).scalar_one())


def make_client(test_db_url: str) -> TestClient:
    app = create_app(Settings(database_url=test_db_url, cors_origins=["http://localhost:5173"]))

    def write_ok(db: Annotated[Session, Depends(get_db)]) -> dict[str, str]:
        db.execute(text("INSERT INTO tx_probe (label) VALUES ('ok')"))
        return {"status": "written"}

    def write_then_fail(db: Annotated[Session, Depends(get_db)]) -> dict[str, str]:
        db.execute(text("INSERT INTO tx_probe (label) VALUES ('doomed')"))
        raise RuntimeError("failure after write")

    app.add_api_route("/test/write-ok", write_ok, methods=["POST"])
    app.add_api_route("/test/write-fail", write_then_fail, methods=["POST"])
    return TestClient(app, raise_server_exceptions=False)


@pytest.mark.usefixtures("probe_table")
def test_successful_request_commits(test_db_url: str) -> None:
    with make_client(test_db_url) as client:
        response = client.post("/test/write-ok")

    assert response.status_code == 200
    assert count_rows(test_db_url) == 1


@pytest.mark.usefixtures("probe_table")
def test_failing_request_rolls_back_its_writes(test_db_url: str) -> None:
    with make_client(test_db_url) as client:
        response = client.post("/test/write-fail")

    assert response.status_code == 500
    assert count_rows(test_db_url) == 0
