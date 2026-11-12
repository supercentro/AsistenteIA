"""`db-bootstrap`: create the roles and close access (change `database-least-privilege`, 4.2).

Run by the administrator, from the `postgres` database for everything that is cluster-wide and
inside the application database only for the schema, the extension and the default privileges.
Idempotent: every run converges to the same state and rotates the passwords it is given.

Hardening (spike findings): the session uses `search_path = pg_catalog` and the statements are
qualified, so a function or operator planted in `public` cannot change what runs (B-01); passwords
are SCRAM verifiers computed here, never clear text (H9); `ALTER ROLE ... RESET ALL` removes any
persistent setting a role gave itself (B-05); `PUBLIC` is closed on every database, the templates
included, and on schema `public` (A-08, A-09); the default privileges use the global form because
the per-schema one has no effect (A-05). Ownership of an existing database is only reported.
"""

from collections.abc import Mapping, Sequence
from dataclasses import dataclass

from app.db_admin.connection import connect, run_steps
from app.db_admin.errors import DbAdminError
from app.db_admin.names import (
    CONNECTION_LIMITS,
    DEFAULT_NAMES,
    SEARCH_PATHS,
    RoleNames,
    RolePasswords,
)
from app.db_admin.sql import (
    VERIFIER_PATTERN,
    Step,
    quote_catalog_name,
    quote_ident,
    quote_literal,
    raw,
    scram_verifier,
)

_LOGICAL = ("migrator", "app", "worker", "cli")
_ATTRIBUTES = "LOGIN NOSUPERUSER NOCREATEDB NOCREATEROLE NOREPLICATION NOBYPASSRLS INHERIT"


@dataclass(frozen=True)
class BootstrapReport:
    created: tuple[str, ...]
    updated: tuple[str, ...]
    closed_databases: int
    ownership_drift: tuple[str, ...]

    def summary(self) -> list[str]:
        lines = [
            f"roles created: {', '.join(self.created) or 'none'}",
            f"roles updated: {', '.join(self.updated) or 'none'}",
            f"databases closed to PUBLIC: {self.closed_databases}",
        ]
        if self.ownership_drift:
            lines.append("ownership drift (not changed here; use db-adopt):")
            lines.extend(f"  {line}" for line in self.ownership_drift)
        else:
            lines.append("ownership: no drift")
        return lines


def role_steps(names: RoleNames, verifiers: Mapping[str, str], existing: set[str]) -> list[Step]:
    """Create or alter each role, reset its settings, set `search_path`, drop its memberships."""
    steps: list[Step] = []
    for logical in _LOGICAL:
        role = getattr(names, logical)
        quoted = quote_ident(role)
        verifier = verifiers[logical]
        if not _is_verifier(verifier):
            raise DbAdminError("a password verifier is not in SCRAM-SHA-256 format")
        verb = "ALTER" if role in existing else "CREATE"
        statement = (
            f"{verb} ROLE {quoted} {_ATTRIBUTES} CONNECTION LIMIT {CONNECTION_LIMITS[logical]} "
            f"PASSWORD {quote_literal(verifier)}"
        )
        steps.append(Step(f"{verb.lower()} role {role}", statement, sensitive=True))
        steps.append(Step(f"reset persistent settings of {role}", f"ALTER ROLE {quoted} RESET ALL"))
        steps.append(
            Step(
                f"set search_path of {role}",
                f"ALTER ROLE {quoted} SET search_path = {SEARCH_PATHS[logical]}",
            )
        )
    listed = ", ".join(quote_literal(name) for name in names.all())
    steps.append(
        Step(
            "revoke every membership of and in the four roles",
            "DO $do$ DECLARE r record; BEGIN "
            "FOR r IN SELECT g.rolname AS grp, m.rolname AS member "
            "FROM pg_catalog.pg_auth_members am "
            "JOIN pg_catalog.pg_roles g ON g.oid = am.roleid "
            "JOIN pg_catalog.pg_roles m ON m.oid = am.member "
            f"WHERE m.rolname IN ({listed}) OR g.rolname IN ({listed}) LOOP "
            "EXECUTE pg_catalog.format('REVOKE %I FROM %I', r.grp, r.member); "
            "END LOOP; END $do$",
        )
    )
    return steps


def _is_verifier(value: str) -> bool:
    import re

    return re.fullmatch(VERIFIER_PATTERN, value) is not None


def database_closing_steps(databases: Sequence[str]) -> list[Step]:
    return [
        Step(
            f"close database {name} to PUBLIC",
            f"REVOKE ALL ON DATABASE {quote_catalog_name(name)} FROM PUBLIC",
        )
        for name in databases
    ]


def database_role_setting_steps(names: RoleNames, databases: Sequence[str]) -> list[Step]:
    """A role can give itself settings for one database (`ALTER ROLE ... IN DATABASE`)."""
    return [
        Step(
            f"reset {role} settings in database {database}",
            f"ALTER ROLE {quote_ident(role)} IN DATABASE {quote_catalog_name(database)} RESET ALL",
        )
        for database in databases
        for role in names.all()
    ]


def application_database_steps(names: RoleNames, database: str) -> list[Step]:
    """Connection rights (cluster scope) and schema, extension, defaults (database scope)."""
    db = quote_ident(database)
    steps = [Step(f"close {database} to PUBLIC", f"REVOKE ALL ON DATABASE {db} FROM PUBLIC")]
    for role in names.all():
        steps.append(
            Step(
                f"allow {role} to connect", f"GRANT CONNECT ON DATABASE {db} TO {quote_ident(role)}"
            )
        )
    schema = '"public"'
    steps.append(
        Step(
            "close schema public to PUBLIC",
            f"REVOKE ALL ON SCHEMA {schema} FROM PUBLIC",
            scope="database",
        )
    )
    steps.append(
        Step(
            "let the migrator create in public",
            f"GRANT CREATE, USAGE ON SCHEMA {schema} TO {quote_ident(names.migrator)}",
            scope="database",
        )
    )
    for role in names.runtime():
        quoted = quote_ident(role)
        steps.append(
            Step(
                f"let {role} use public",
                f"GRANT USAGE ON SCHEMA {schema} TO {quoted}",
                scope="database",
            )
        )
        steps.append(
            Step(
                f"keep {role} from creating in public",
                f"REVOKE CREATE ON SCHEMA {schema} FROM {quoted}",
                scope="database",
            )
        )
    steps.append(
        Step(
            "create the vector extension",
            "CREATE EXTENSION IF NOT EXISTS vector WITH SCHEMA public",
            scope="database",
        )
    )
    steps.append(
        Step(
            "functions of the migrator are not executable by PUBLIC",
            f"ALTER DEFAULT PRIVILEGES FOR ROLE {quote_ident(names.migrator)} "
            "REVOKE EXECUTE ON FUNCTIONS FROM PUBLIC",
            scope="database",
        )
    )
    return steps


def _ownership_drift(conn: "object", migrator: str) -> tuple[str, ...]:
    from typing import Any, cast

    import psycopg

    connection = cast("psycopg.Connection[Any]", conn)
    rows = connection.execute(
        raw(
            "SELECT 'table ' || c.relname, r.rolname FROM pg_catalog.pg_class c "
            "JOIN pg_catalog.pg_roles r ON r.oid = c.relowner "
            "WHERE c.relnamespace = 'public'::pg_catalog.regnamespace AND c.relkind = 'r' "
            "UNION ALL SELECT 'type ' || t.typname, r.rolname FROM pg_catalog.pg_type t "
            "JOIN pg_catalog.pg_roles r ON r.oid = t.typowner "
            "WHERE t.typnamespace = 'public'::pg_catalog.regnamespace AND t.typtype = 'e' "
            "ORDER BY 1"
        )
    ).fetchall()
    return tuple(f"{what} owned by {owner}" for what, owner in rows if owner != migrator)


def bootstrap(
    admin_url: str,
    passwords: RolePasswords,
    *,
    database: str,
    names: RoleNames = DEFAULT_NAMES,
) -> BootstrapReport:
    """Converge the cluster to the role and access state of the design (idempotent)."""
    quote_ident(database)  # refuse before any connection
    for role in names.all():
        quote_ident(role)
    verifiers = {logical: scram_verifier(getattr(passwords, logical)) for logical in _LOGICAL}

    with connect(admin_url, database="postgres", quiet_logs=True) as conn:
        all_databases = [
            str(row[0])
            for row in conn.execute(
                raw("SELECT datname FROM pg_catalog.pg_database ORDER BY datname")
            ).fetchall()
        ]
        closing = database_closing_steps(all_databases)  # every name is validated before any step
        existing = {
            str(row[0])
            for row in conn.execute(
                raw("SELECT rolname FROM pg_catalog.pg_roles WHERE rolname = ANY(%s)"),
                (list(names.all()),),
            ).fetchall()
        }
        has_database = conn.execute(
            raw("SELECT 1 FROM pg_catalog.pg_database WHERE datname = %s"), (database,)
        ).fetchone()
        if has_database is None:
            run_steps(
                conn,
                [Step(f"create database {database}", f"CREATE DATABASE {quote_ident(database)}")],
            )
        run_steps(conn, role_steps(names, verifiers, existing))
        run_steps(conn, closing)
        if has_database is None:
            run_steps(conn, application_database_steps(names, database)[:1])  # close it at once
        configurable = [
            str(row[0])
            for row in conn.execute(
                raw(
                    "SELECT datname FROM pg_catalog.pg_database "
                    "WHERE NOT datistemplate AND datallowconn ORDER BY datname"
                )
            ).fetchall()
        ]
        run_steps(conn, database_role_setting_steps(names, configurable))
        cluster_steps = [
            s for s in application_database_steps(names, database) if s.scope == "cluster"
        ]
        run_steps(conn, cluster_steps)

    with connect(admin_url, database=database, quiet_logs=True) as conn:
        database_steps = [
            s for s in application_database_steps(names, database) if s.scope == "database"
        ]
        run_steps(conn, database_steps)
        drift = _ownership_drift(conn, names.migrator)

    created = tuple(role for role in names.all() if role not in existing)
    updated = tuple(role for role in names.all() if role in existing)
    return BootstrapReport(created, updated, len(all_databases), drift)
