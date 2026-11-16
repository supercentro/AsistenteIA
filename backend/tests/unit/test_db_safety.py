import pytest

from app.core.db_safety import UnsafeTestDatabaseError, assert_safe_test_database
from tests.db_support import MissingTestDatabaseError, require_test_database_url

APP_URL = "postgresql+psycopg://u:p@db:5432/asistenteia"
TEST_URL = "postgresql+psycopg://u:p@localhost:5442/asistenteia_test"


def test_guard_accepts_dedicated_test_database() -> None:
    assert_safe_test_database(TEST_URL, APP_URL, "development")


def test_guard_accepts_test_environment_without_app_url() -> None:
    assert_safe_test_database(TEST_URL, None, "test")


def test_guard_rejects_same_server_and_database_as_application() -> None:
    same = "postgresql+psycopg://u:p@db:5432/asistenteia_test"

    with pytest.raises(UnsafeTestDatabaseError):
        assert_safe_test_database(same, same, "development")


def test_guard_rejects_same_database_name_on_another_host_alias() -> None:
    app_url = "postgresql+psycopg://u:p@db:5432/asistenteia_test"

    with pytest.raises(UnsafeTestDatabaseError):
        assert_safe_test_database(TEST_URL, app_url, "development")


@pytest.mark.parametrize("name", ["asistenteia", "asistenteia_testing", "test_asistenteia", "prod"])
def test_guard_rejects_database_name_not_ending_in_test(name: str) -> None:
    url = f"postgresql+psycopg://u:p@localhost:5442/{name}"

    with pytest.raises(UnsafeTestDatabaseError, match="_test"):
        assert_safe_test_database(url, APP_URL, "development")


def test_guard_rejects_production_environment() -> None:
    with pytest.raises(UnsafeTestDatabaseError, match="production"):
        assert_safe_test_database(TEST_URL, APP_URL, "production")


def test_guard_rejects_unparsable_url() -> None:
    with pytest.raises(UnsafeTestDatabaseError):
        assert_safe_test_database("not-a-url", APP_URL, "development")


def test_guard_error_never_contains_the_password() -> None:
    url = "postgresql+psycopg://u:super-secret@localhost:5442/asistenteia"

    with pytest.raises(UnsafeTestDatabaseError) as exc:
        assert_safe_test_database(url, APP_URL, "development")

    assert "super-secret" not in str(exc.value)


def test_require_test_database_url_fails_fast_when_unset(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.delenv("TEST_DATABASE_URL", raising=False)

    with pytest.raises(MissingTestDatabaseError, match="TEST_DATABASE_URL"):
        require_test_database_url()


def test_require_test_database_url_returns_a_guarded_url(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("TEST_DATABASE_URL", TEST_URL)
    monkeypatch.setenv("DATABASE_URL", APP_URL)
    monkeypatch.delenv("APP_ENV", raising=False)

    assert require_test_database_url() == TEST_URL


def test_require_test_database_url_rejects_unsafe_url(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("TEST_DATABASE_URL", APP_URL)
    monkeypatch.setenv("DATABASE_URL", APP_URL)

    with pytest.raises(UnsafeTestDatabaseError):
        require_test_database_url()


# --- Finding P2 of the Codex review of 6e85470 (task 19.3.4): malformed URLs ---

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


@pytest.mark.parametrize("case", list(MALFORMED))
def test_guard_rejects_a_malformed_test_url_without_leaking_any_part_of_it(case: str) -> None:
    with pytest.raises(UnsafeTestDatabaseError) as caught:
        assert_safe_test_database(MALFORMED[case], APP_URL, "development")

    assert str(caught.value).startswith("TEST_DATABASE_URL")
    assert_value_free(caught.value, MALFORMED[case])


@pytest.mark.parametrize("case", list(MALFORMED))
def test_guard_rejects_a_malformed_application_url_without_leaking_any_part_of_it(
    case: str,
) -> None:
    with pytest.raises(UnsafeTestDatabaseError) as caught:
        assert_safe_test_database(TEST_URL, MALFORMED[case], "development")

    assert str(caught.value).startswith("DATABASE_URL")
    assert_value_free(caught.value, MALFORMED[case])


@pytest.mark.parametrize("which", ["test", "application"])
def test_guard_keeps_its_safe_rejection_of_an_unparsable_url(which: str) -> None:
    test_url, app_url = ("this is not a url", APP_URL) if which == "test" else (TEST_URL, "no url")

    with pytest.raises(UnsafeTestDatabaseError) as caught:
        assert_safe_test_database(test_url, app_url, "development")

    assert "is not a valid database URL" in str(caught.value)
    assert_value_free(caught.value, "this is not a url")
