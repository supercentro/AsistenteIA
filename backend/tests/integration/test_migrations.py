from pathlib import Path

from alembic import command
from alembic.config import Config
from sqlalchemy import text

from tests.db_support import drop_everything, guarded_engine

BACKEND_DIR = Path(__file__).resolve().parents[2]


def alembic_config(url: str) -> Config:
    config = Config(str(BACKEND_DIR / "alembic.ini"))
    config.set_main_option("script_location", str(BACKEND_DIR / "alembic"))
    config.set_main_option("sqlalchemy.url", url.replace("%", "%%"))
    return config


def vector_installed(url: str) -> bool:
    with guarded_engine(url) as engine, engine.connect() as conn:
        found = conn.execute(text("SELECT 1 FROM pg_extension WHERE extname = 'vector'")).first()
    return found is not None


def test_upgrade_head_enables_vector_and_downgrade_base_removes_it(test_db_url: str) -> None:
    drop_everything(test_db_url)
    config = alembic_config(test_db_url)

    command.upgrade(config, "head")
    assert vector_installed(test_db_url)

    command.downgrade(config, "base")
    assert not vector_installed(test_db_url)

    command.upgrade(config, "head")
    assert vector_installed(test_db_url)

    drop_everything(test_db_url)
