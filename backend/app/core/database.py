"""Synchronous SQLAlchemy engine, session factory and declarative base."""

from sqlalchemy import MetaData, create_engine
from sqlalchemy.engine import Engine
from sqlalchemy.orm import DeclarativeBase, Session, sessionmaker

NAMING_CONVENTION = {
    "ix": "ix_%(column_0_label)s",
    "uq": "uq_%(table_name)s_%(column_0_name)s",
    "ck": "ck_%(table_name)s_%(constraint_name)s",
    "fk": "fk_%(table_name)s_%(column_0_name)s_%(referred_table_name)s",
    "pk": "pk_%(table_name)s",
}


class Base(DeclarativeBase):
    metadata = MetaData(naming_convention=NAMING_CONVENTION)


def create_db_engine(database_url: str, connect_timeout_seconds: int = 5) -> Engine:
    """Create the engine lazily: no connection is opened until first use.

    `connect_timeout` bounds every connection attempt so an unreachable database fails fast
    instead of blocking requests (including the health check).
    """
    return create_engine(
        database_url,
        pool_pre_ping=True,
        hide_parameters=True,  # never render bound parameters (emails, hashes) in error text
        connect_args={"connect_timeout": connect_timeout_seconds},
    )


def create_session_factory(engine: Engine) -> sessionmaker[Session]:
    return sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)
