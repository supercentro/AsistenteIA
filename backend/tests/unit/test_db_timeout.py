import pytest
from sqlalchemy import event

from app.core.config import ConfigurationError, load_settings
from app.core.database import create_db_engine

DB_URL = "postgresql+psycopg://user:pw@localhost:5432/asistenteia"


@pytest.fixture(autouse=True)
def clean_env(monkeypatch: pytest.MonkeyPatch) -> None:
    for name in ("APP_ENV", "DATABASE_URL", "CORS_ORIGINS", "DB_CONNECT_TIMEOUT_SECONDS"):
        monkeypatch.delenv(name, raising=False)


def test_connect_timeout_defaults_to_five_seconds(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("DATABASE_URL", DB_URL)

    assert load_settings(env_file=None).db_connect_timeout_seconds == 5


def test_connect_timeout_is_configurable(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("DATABASE_URL", DB_URL)
    monkeypatch.setenv("DB_CONNECT_TIMEOUT_SECONDS", "2")

    assert load_settings(env_file=None).db_connect_timeout_seconds == 2


@pytest.mark.parametrize("value", ["0", "-1", "61", "abc"])
def test_connect_timeout_rejects_out_of_range_values(
    monkeypatch: pytest.MonkeyPatch, value: str
) -> None:
    monkeypatch.setenv("DATABASE_URL", DB_URL)
    monkeypatch.setenv("DB_CONNECT_TIMEOUT_SECONDS", value)

    with pytest.raises(ConfigurationError) as exc:
        load_settings(env_file=None)

    assert "DB_CONNECT_TIMEOUT_SECONDS" in str(exc.value)


def test_engine_passes_connect_timeout_to_the_driver() -> None:
    engine = create_db_engine(DB_URL, connect_timeout_seconds=7)
    seen: dict[str, object] = {}

    @event.listens_for(engine, "do_connect")
    def capture(
        dialect: object, conn_rec: object, cargs: object, cparams: dict[str, object]
    ) -> None:
        seen.update(cparams)
        raise RuntimeError("stop before opening a connection")

    with pytest.raises(RuntimeError, match="stop before"), engine.connect():
        pass

    assert seen["connect_timeout"] == 7
    engine.dispose()
