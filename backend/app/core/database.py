"""Synchronous SQLAlchemy engine, session factory and declarative base."""

from sqlalchemy import MetaData, create_engine, text
from sqlalchemy.engine import Engine, make_url
from sqlalchemy.exc import ArgumentError, SQLAlchemyError
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


def create_db_engine(
    database_url: str,
    connect_timeout_seconds: int = 5,
    *,
    statement_timeout_seconds: int | None = None,
    idle_in_transaction_timeout_seconds: int | None = None,
) -> Engine:
    """Create the engine lazily: no connection is opened until first use.

    `connect_timeout` bounds every connection attempt so an unreachable database fails fast
    instead of blocking requests (including the health check). The optional timeouts become
    connection options of the server session (`statement_timeout` and
    `idle_in_transaction_session_timeout`); they are not applied unless given (design A10).
    """
    connect_args: dict[str, object] = {"connect_timeout": connect_timeout_seconds}
    options = []
    if statement_timeout_seconds is not None:
        options.append(f"-c statement_timeout={int(statement_timeout_seconds) * 1000}")
    if idle_in_transaction_timeout_seconds is not None:
        options.append(
            "-c idle_in_transaction_session_timeout="
            f"{int(idle_in_transaction_timeout_seconds) * 1000}"
        )
    if options:
        connect_args["options"] = " ".join(options)
    try:
        url = make_url(database_url)
    except (ArgumentError, ValueError):
        # The parser's own message can carry a part of the value (a password with an unescaped
        # "@" leaves a segment read as the port), and a traceback would print it at start-up.
        raise ValueError("the database URL is not valid") from None
    return create_engine(
        url,
        pool_pre_ping=True,
        hide_parameters=True,  # never render bound parameters (emails, hashes) in error text
        connect_args=connect_args,
    )


def create_session_factory(engine: Engine) -> sessionmaker[Session]:
    return sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)


_SUPERUSER_MESSAGE = (
    "the database connection uses a PostgreSQL superuser: refusing to start "
    "(give the service its restricted role)"
)
_UNVERIFIED_MESSAGE = (
    "the identity of the database connection could not be verified: refusing to start"
)
# The effective identity as the server sees it: the `is_superuser` setting of the session and the
# superuser attribute of both the session user and the current role. `pg_catalog` is named so
# nothing planted in another schema can answer; the user name in the URL is never consulted.
_IDENTITY_SQL = (
    "SELECT pg_catalog.current_setting('is_superuser') = 'on', "
    "(SELECT pg_catalog.bool_or(rolsuper) FROM pg_catalog.pg_roles "
    "WHERE rolname IN (current_user, session_user))"
)


class SuperuserConnectionError(RuntimeError):
    """The connection is a superuser, or its identity could not be proved restricted."""

    def __init__(self, message: str = _SUPERUSER_MESSAGE) -> None:
        super().__init__(message)


def assert_restricted_database_role(engine: Engine) -> None:
    """Refuse a superuser connection (finding PG-01, DD-16); fail closed when it cannot be asked.

    The text of a driver error can carry hosts or credentials, so it is dropped.
    """
    try:
        with engine.connect() as connection:
            is_superuser_setting, role_is_superuser = connection.execute(text(_IDENTITY_SQL)).one()
    except SQLAlchemyError:
        raise SuperuserConnectionError(_UNVERIFIED_MESSAGE) from None
    if is_superuser_setting is not False or role_is_superuser is not False:
        raise SuperuserConnectionError(_SUPERUSER_MESSAGE)
