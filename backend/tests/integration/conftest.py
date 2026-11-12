from collections.abc import Iterator
from pathlib import Path

import pytest
from alembic import command
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.core.database import create_db_engine, create_session_factory
from app.core.db_safety import UnsafeTestDatabaseError
from app.models.user import UserRole
from tests.db_support import (
    MissingTestDatabaseError,
    alembic_config,
    drop_everything,
    load_test_environment,
    require_test_database_url,
    truncate_all,
)
from tests.integration.helpers import MakeUser, TestUser, build_app, insert_user

# Integration tests run on the host: read backend/.env.test and backend/.env without overriding the
# real environment (the test variables are host-only and never reach a container).
load_test_environment(Path(__file__).resolve().parents[2])


@pytest.fixture(scope="session")
def test_db_url() -> Iterator[str]:
    """Guarded TEST_DATABASE_URL. Fails fast, before any connection, if missing or unsafe."""
    try:
        yield require_test_database_url()
    except (MissingTestDatabaseError, UnsafeTestDatabaseError) as exc:
        pytest.exit(f"Integration tests aborted: {exc}", returncode=2)


@pytest.fixture(scope="session")
def migrated_db(test_db_url: str) -> Iterator[str]:
    """Test database at `alembic head`, built from scratch once and emptied at the end."""
    drop_everything(test_db_url)
    command.upgrade(alembic_config(test_db_url), "head")
    yield test_db_url
    drop_everything(test_db_url)


@pytest.fixture
def clean_db(migrated_db: str) -> str:
    """Migrated test database with every table emptied before the test."""
    truncate_all(migrated_db)
    return migrated_db


@pytest.fixture
def db_session(clean_db: str) -> Iterator[Session]:
    engine = create_db_engine(clean_db)
    session = create_session_factory(engine)()
    try:
        yield session
    finally:
        session.rollback()
        session.close()
        engine.dispose()


@pytest.fixture
def client(clean_db: str) -> Iterator[TestClient]:
    with TestClient(build_app(clean_db), raise_server_exceptions=False) as test_client:
        yield test_client


@pytest.fixture
def make_user(clean_db: str) -> MakeUser:
    def _make(email: str, role: UserRole = UserRole.STUDENT, **kwargs: str) -> TestUser:
        return insert_user(clean_db, email, role, **kwargs)

    return _make
