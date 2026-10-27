from collections.abc import Iterator
from pathlib import Path

import pytest
from dotenv import load_dotenv

from app.core.db_safety import UnsafeTestDatabaseError
from tests.db_support import MissingTestDatabaseError, require_test_database_url

# Integration tests run on the host: read backend/.env without overriding the real environment.
load_dotenv(Path(__file__).resolve().parents[2] / ".env", override=False)


@pytest.fixture(scope="session")
def test_db_url() -> Iterator[str]:
    """Guarded TEST_DATABASE_URL. Fails fast, before any connection, if missing or unsafe."""
    try:
        yield require_test_database_url()
    except (MissingTestDatabaseError, UnsafeTestDatabaseError) as exc:
        pytest.exit(f"Integration tests aborted: {exc}", returncode=2)
