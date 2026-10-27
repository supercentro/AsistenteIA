"""Guard that restricts destructive database operations in tests to a dedicated test database."""

from sqlalchemy.engine import make_url
from sqlalchemy.exc import ArgumentError

TEST_DATABASE_SUFFIX = "_test"


class UnsafeTestDatabaseError(RuntimeError):
    """Raised when a database is not safe for migrations or destructive cleanup in tests."""


def assert_safe_test_database(test_url: str, app_url: str | None, app_env: str) -> None:
    """Raise unless `test_url` points to a database that is dedicated to tests.

    Must be called before any connection that can mutate data. Messages never include the
    password or the full URL.
    """
    if app_env == "production":
        raise UnsafeTestDatabaseError("Refusing test database operations when APP_ENV=production")

    try:
        test = make_url(test_url)
    except ArgumentError:
        raise UnsafeTestDatabaseError("TEST_DATABASE_URL is not a valid database URL") from None

    if not test.database or not test.database.endswith(TEST_DATABASE_SUFFIX):
        raise UnsafeTestDatabaseError(
            f"Refusing to use database {test.database!r}: its name must end in "
            f"'{TEST_DATABASE_SUFFIX}'"
        )

    if app_url:
        try:
            app = make_url(app_url)
        except ArgumentError:
            raise UnsafeTestDatabaseError("DATABASE_URL is not a valid database URL") from None
        # Same name is rejected even if hosts differ ("db" and "127.0.0.1" can be one server).
        if app.database == test.database:
            raise UnsafeTestDatabaseError(
                "TEST_DATABASE_URL must not point to the same database as DATABASE_URL"
            )
