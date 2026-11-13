"""Connections of the administration commands: hardened, bounded, and silent about secrets."""

from collections.abc import Iterable
from typing import Any

import psycopg
from sqlalchemy.engine import URL, make_url
from sqlalchemy.exc import ArgumentError

from app.db_admin.errors import DbAdminError
from app.db_admin.sql import Step, raw

APPLICATION_NAME = "asistenteia-db-admin"
# Databases the cluster itself depends on: no application command may be pointed at them.
SYSTEM_DATABASES = frozenset({"postgres", "template0", "template1"})
# The only URL query parameters that are passed on: the ones that decide whether TLS is used.
TLS_PARAMETERS = ("sslmode", "sslrootcert", "sslcert", "sslkey")


def tls_parameters(parts: URL) -> dict[str, Any]:
    """The TLS-related query parameters of a URL, the only ones passed on to the driver."""
    return {k: v for k, v in parts.query.items() if k in TLS_PARAMETERS and isinstance(v, str)}


def connect(
    url: str,
    *,
    database: str | None = None,
    autocommit: bool = True,
    read_only: bool = False,
    lock_timeout_ms: int | None = None,
    quiet_logs: bool = False,
) -> "psycopg.Connection[Any]":
    """Open a session with `search_path = pg_catalog`, so nothing planted in `public` can win.

    Errors name the host, port, user and SQLSTATE; they never include the server message or the URL.
    """
    try:
        parts = make_url(url)
    except ArgumentError:
        raise DbAdminError("the database URL is not valid") from None
    options = ["-c search_path=pg_catalog"]
    if read_only:
        options.append("-c default_transaction_read_only=on")
    if lock_timeout_ms is not None:
        options.append(f"-c lock_timeout={int(lock_timeout_ms)}")
    if quiet_logs:  # superuser only: a statement with a verifier must not reach the server log
        options.append("-c log_statement=none")
        options.append("-c log_min_error_statement=panic")
        options.append("-c log_min_duration_statement=-1")
    try:
        return psycopg.connect(
            host=parts.host,
            port=parts.port,
            user=parts.username,
            password=parts.password,
            dbname=database or parts.database,
            autocommit=autocommit,
            connect_timeout=10,
            application_name=APPLICATION_NAME,
            options=" ".join(options),
            **tls_parameters(parts),
        )
    except psycopg.Error as exc:
        raise DbAdminError(
            f"cannot connect to {parts.host}:{parts.port} as {parts.username} "
            f"(SQLSTATE {exc.sqlstate or 'none'}, {type(exc).__name__})"
        ) from None


def run_steps(conn: "psycopg.Connection[Any]", steps: Iterable[Step]) -> int:
    """Execute the steps in order; a failure names the step and the SQLSTATE only."""
    count = 0
    for step in steps:
        try:
            conn.execute(raw(step.sql))
        except psycopg.Error as exc:
            raise DbAdminError(
                f"step failed: {step.description} (SQLSTATE {exc.sqlstate or 'none'})"
            ) from None
        count += 1
    return count


def check_identity(conn: "psycopg.Connection[Any]", expected: str, command: str) -> None:
    """Stop unless the session AND the current role are `expected` (finding PG-02, DD-16).

    Run it on the first connection of a command, before any statement that changes something: an
    administrator URL pasted by mistake would otherwise create objects it owns.
    """
    row = conn.execute(raw("SELECT current_user, session_user")).fetchone()
    if row is None or row[0] != expected or row[1] != expected:
        raise DbAdminError(
            f"{command} must connect as the migrator role {expected}; "
            "check the URL (nothing was changed)"
        )


def require_identity(url: str, expected: str, command: str) -> None:
    """Open a short read-only session, check the identity and close it."""
    with connect(url, read_only=True) as conn:
        check_identity(conn, expected, command)


def refuse_system_database(database: str, command: str) -> None:
    """Stop before any connection when the target is a system database (PG-07, DD-16).

    The comparison ignores case and surrounding blanks, so a near miss of a system name is refused
    too instead of being taken for an application database.
    """
    if database.strip().lower() in SYSTEM_DATABASES:
        raise DbAdminError(
            f"{command} cannot target a system database ({', '.join(sorted(SYSTEM_DATABASES))}); "
            "name the application database"
        )
