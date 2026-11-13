"""`db-adopt`: explicit, one-time change of ownership of an existing database (task 4.3).

A database created before this change belongs to the administrator. Adoption makes the migrator
the owner of its tables and enum types (indexes and TOAST follow the tables) in one transaction
with a `lock_timeout`, after proving that no session of the four roles exists. It is a dry run
unless `apply=True`, it changes nothing when an object is unexpected, and it proves that the rows
and the catalog (blind to owners) are identical before it commits. The database and the extension
stay with the administrator.

The documented way back is `rollback_adoption`: `REASSIGN OWNED` first in every database,
verification that nothing is owned any more, and only then `DROP OWNED` and `DROP ROLE`. A
`DROP OWNED` before the reassignment would drop the tables themselves (spike A-02), so
`remove_roles` refuses while a role still owns anything.
"""

from collections.abc import Sequence
from dataclasses import dataclass
from typing import Any

import psycopg

from app.db_admin.connection import connect, refuse_system_database
from app.db_admin.errors import DbAdminError
from app.db_admin.names import DEFAULT_NAMES, RoleNames
from app.db_admin.sql import quote_catalog_name, quote_ident, quote_qualified, raw
from app.db_privileges import MATRIX

CLOSED_TABLES = ("alembic_version",)
_NOT_AN_EXTENSION_MEMBER = (
    "NOT EXISTS (SELECT 1 FROM pg_catalog.pg_depend d WHERE d.objid = {oid} AND d.deptype = 'e')"
)
Connection = "psycopg.Connection[Any]"


class AdoptRefusedError(DbAdminError):
    """The adoption or the rollback was refused; nothing was changed."""


@dataclass(frozen=True)
class AdoptReport:
    applied: bool
    planned: tuple[str, ...]

    def summary(self) -> list[str]:
        head = "applied" if self.applied else "dry run (nothing changed; use --apply)"
        lines = [f"adoption {head}: {len(self.planned)} object(s)"]
        lines.extend(f"  {line}" for line in self.planned)
        return lines


@dataclass(frozen=True)
class RollbackReport:
    statements: tuple[str, ...]
    first_removal_index: int
    owners_verified: bool
    other_databases: tuple[str, ...] = ()

    def summary(self) -> list[str]:
        lines = [
            f"rollback: {len(self.statements)} statement(s), owners verified: {self.owners_verified}"  # noqa: E501
        ]
        if self.other_databases:
            lines.append(
                "the migrator still owns objects in: "
                + ", ".join(self.other_databases)
                + "; roll those databases back too before removing the roles"
            )
        return lines


def _expected_tables() -> set[str]:
    return {table for per_role in MATRIX.values() for table in per_role} | set(CLOSED_TABLES)


def _runtime_sessions(conn: "psycopg.Connection[Any]", names: RoleNames) -> int:
    row = conn.execute(
        raw(
            "SELECT count(*) FROM pg_catalog.pg_stat_activity "
            "WHERE usename = ANY(%s) AND pid <> pg_catalog.pg_backend_pid()"
        ),
        (list(names.all()),),
    ).fetchone()
    return int(row[0]) if row else 0


def _blocking_sessions(
    conn: "psycopg.Connection[Any]", names: RoleNames, ignore: Sequence[str]
) -> list[str]:
    """Sessions that must be gone before adoption, described by user, application and count.

    Before adoption the API and the worker run as the administrator, so the sessions of the four
    new roles are not enough: any other session on this database counts too (spec: running
    services block adoption). `ignore` skips sessions by `application_name` (a test lock holder).
    """
    rows = conn.execute(
        raw(
            "SELECT coalesce(usename, '?'), coalesce(application_name, ''), count(*) "
            "FROM pg_catalog.pg_stat_activity "
            "WHERE pid <> pg_catalog.pg_backend_pid() AND backend_type = 'client backend' "
            "AND (datname = pg_catalog.current_database() OR usename = ANY(%s)) "
            "AND application_name <> ALL(%s) GROUP BY 1, 2 ORDER BY 1, 2"
        ),
        (list(names.all()), list(ignore) or [""]),
    ).fetchall()
    return [f"{user} [{app or 'no application name'}] x{count}" for user, app, count in rows]


def _unexpected_objects(conn: "psycopg.Connection[Any]", admin: str, migrator: str) -> list[str]:
    """Everything adoption does not know how to move, described without values."""
    found: list[str] = []
    expected = _expected_tables()
    relations = conn.execute(
        raw(
            "SELECT c.relname, c.relkind, r.rolname, "
            "EXISTS (SELECT 1 FROM pg_catalog.pg_depend d WHERE d.objid = c.oid "
            "AND d.classid = 'pg_catalog.pg_class'::pg_catalog.regclass AND d.deptype IN ('a', 'i')) "  # noqa: E501
            "AS owned_sequence "
            "FROM pg_catalog.pg_class c JOIN pg_catalog.pg_roles r ON r.oid = c.relowner "
            "WHERE c.relnamespace = 'public'::pg_catalog.regnamespace AND "
            + _NOT_AN_EXTENSION_MEMBER.format(oid="c.oid")
        )
    ).fetchall()
    for name, kind, owner, owned_sequence in relations:
        if owner not in {admin, migrator}:
            found.append(f"relation {name} owned by an unexpected role")
        if kind == "r" and name not in expected:
            found.append(f"table {name} is not in the privilege matrix")
        elif kind == "S" and not owned_sequence:
            found.append(f"standalone sequence {name}")
        elif kind not in {"r", "i", "S"}:
            found.append(f"relation {name} of kind {kind}")
    types = conn.execute(
        raw(
            "SELECT t.typname, t.typtype, r.rolname FROM pg_catalog.pg_type t "
            "JOIN pg_catalog.pg_roles r ON r.oid = t.typowner "
            "WHERE t.typnamespace = 'public'::pg_catalog.regnamespace AND t.typelem = 0 "
            "AND t.typrelid = 0 AND " + _NOT_AN_EXTENSION_MEMBER.format(oid="t.oid")
        )
    ).fetchall()
    for name, kind, owner in types:
        if kind != "e":
            found.append(f"type {name} of kind {kind}")
        elif owner not in {admin, migrator}:
            found.append(f"type {name} owned by an unexpected role")
    functions = conn.execute(
        raw(
            "SELECT p.proname FROM pg_catalog.pg_proc p WHERE p.pronamespace = "
            "'public'::pg_catalog.regnamespace AND " + _NOT_AN_EXTENSION_MEMBER.format(oid="p.oid")
        )
    ).fetchall()
    found.extend(f"function {name}" for (name,) in functions)
    schemas = conn.execute(
        raw(
            "SELECT nspname FROM pg_catalog.pg_namespace WHERE nspname NOT LIKE 'pg\\_%%' "
            "AND nspname NOT IN ('public', 'information_schema')"
        )
    ).fetchall()
    found.extend(f"schema {name}" for (name,) in schemas)
    return found


def _plan(conn: "psycopg.Connection[Any]", admin: str, migrator: str) -> list[tuple[str, str]]:
    """(description, statement) for each table and enum type not yet owned by the migrator."""
    quoted_migrator = quote_ident(migrator)
    plan: list[tuple[str, str]] = []
    tables = conn.execute(
        raw(
            "SELECT c.relname, r.rolname FROM pg_catalog.pg_class c "
            "JOIN pg_catalog.pg_roles r ON r.oid = c.relowner "
            "WHERE c.relnamespace = 'public'::pg_catalog.regnamespace AND c.relkind = 'r' "
            "ORDER BY c.relname"
        )
    ).fetchall()
    for name, owner in tables:
        if owner != migrator:
            plan.append(
                (
                    f"table {name}: {owner} -> {migrator}",
                    f"ALTER TABLE {quote_qualified('public', str(name))} OWNER TO {quoted_migrator}",  # noqa: E501
                )
            )
    enums = conn.execute(
        raw(
            "SELECT t.typname, r.rolname FROM pg_catalog.pg_type t "
            "JOIN pg_catalog.pg_roles r ON r.oid = t.typowner "
            "WHERE t.typnamespace = 'public'::pg_catalog.regnamespace AND t.typtype = 'e' "
            "ORDER BY t.typname"
        )
    ).fetchall()
    for name, owner in enums:
        if owner != migrator:
            plan.append(
                (
                    f"type {name}: {owner} -> {migrator}",
                    f"ALTER TYPE {quote_qualified('public', str(name))} OWNER TO {quoted_migrator}",
                )
            )
    return plan


def _counts(conn: "psycopg.Connection[Any]") -> dict[str, int]:
    names = conn.execute(
        raw(
            "SELECT c.relname FROM pg_catalog.pg_class c "
            "WHERE c.relnamespace = 'public'::pg_catalog.regnamespace AND c.relkind = 'r' "
            "ORDER BY c.relname"
        )
    ).fetchall()
    counts: dict[str, int] = {}
    for (name,) in names:
        row = conn.execute(
            raw(f"SELECT count(*) FROM {quote_qualified('public', str(name))}")
        ).fetchone()
        counts[str(name)] = int(row[0]) if row else -1
    return counts


def _fingerprint(conn: "psycopg.Connection[Any]") -> str:
    row = conn.execute(
        raw(
            "SELECT md5(string_agg(x, '|' ORDER BY x)) FROM ("
            "SELECT 'c:' || c.relname || '.' || a.attname || ':' || "
            "pg_catalog.format_type(a.atttypid, a.atttypmod) AS x "
            "FROM pg_catalog.pg_class c JOIN pg_catalog.pg_attribute a ON a.attrelid = c.oid "
            "WHERE c.relnamespace = 'public'::pg_catalog.regnamespace AND c.relkind = 'r' "
            "AND a.attnum > 0 AND NOT a.attisdropped "
            "UNION ALL SELECT 'i:' || indexname || ':' || indexdef FROM pg_catalog.pg_indexes "
            "WHERE schemaname = 'public' "
            "UNION ALL SELECT 'k:' || conname || ':' || pg_catalog.pg_get_constraintdef(oid) "
            "FROM pg_catalog.pg_constraint "
            "WHERE connamespace = 'public'::pg_catalog.regnamespace) s"
        )
    ).fetchone()
    return str(row[0]) if row else ""


def adopt(
    admin_url: str,
    *,
    database: str,
    names: RoleNames = DEFAULT_NAMES,
    apply: bool = False,
    lock_timeout_ms: int = 5000,
    ignore_application_names: Sequence[str] = (),
) -> AdoptReport:
    refuse_system_database(database, "db-adopt")
    quote_ident(database)
    for role in names.all():
        quote_ident(role)
    with connect(
        admin_url, database=database, autocommit=False, lock_timeout_ms=lock_timeout_ms
    ) as conn:
        try:
            admin_row = conn.execute(raw("SELECT current_user")).fetchone()
            admin = str(admin_row[0]) if admin_row else ""
            exists = conn.execute(
                raw("SELECT 1 FROM pg_catalog.pg_roles WHERE rolname = %s"), (names.migrator,)
            ).fetchone()
            if exists is None:
                raise AdoptRefusedError("the migrator role does not exist; run db-bootstrap first")
            sessions = _blocking_sessions(conn, names, ignore_application_names)
            if sessions:
                raise AdoptRefusedError(
                    "session(s) hold this database; stop the API, the worker and the CLI before "
                    "adopting: " + "; ".join(sessions)
                )
            unexpected = _unexpected_objects(conn, admin, names.migrator)
            if unexpected:
                raise AdoptRefusedError(
                    "unexpected objects, nothing changed: " + "; ".join(unexpected[:10])
                )
            plan = _plan(conn, admin, names.migrator)
            planned = tuple(description for description, _ in plan)
            if not apply or not plan:
                conn.rollback()
                return AdoptReport(applied=apply and bool(plan), planned=planned)
            counts, fingerprint = _counts(conn), _fingerprint(conn)
            for description, statement in plan:
                try:
                    conn.execute(raw(statement))
                except psycopg.errors.LockNotAvailable:
                    raise
                except psycopg.Error as exc:
                    raise AdoptRefusedError(
                        f"step failed: {description} (SQLSTATE {exc.sqlstate or 'none'}); "
                        "nothing was changed"
                    ) from None
            if _counts(conn) != counts or _fingerprint(conn) != fingerprint:
                raise AdoptRefusedError("rows or catalog differ after the change; rolled back")
            if _plan(conn, admin, names.migrator):
                raise AdoptRefusedError("objects remain with the old owner; rolled back")
            conn.commit()
            return AdoptReport(applied=True, planned=planned)
        except psycopg.errors.LockNotAvailable:
            conn.rollback()
            raise AdoptRefusedError(
                "could not get a lock within lock_timeout; nothing was changed"
            ) from None
        except BaseException:
            conn.rollback()
            raise


def _owned_count(conn: "psycopg.Connection[Any]", role: str) -> int:
    row = conn.execute(
        raw(
            "SELECT count(*) FROM pg_catalog.pg_shdepend s WHERE s.deptype = 'o' "
            # Default-privilege entries depend on their role as an owner but REASSIGN OWNED does
            # not move them (DROP OWNED removes them), so they do not count as owned objects.
            "AND s.classid <> 'pg_catalog.pg_default_acl'::pg_catalog.regclass "
            "AND s.refclassid = 'pg_catalog.pg_authid'::pg_catalog.regclass "
            "AND s.refobjid = (SELECT oid FROM pg_catalog.pg_roles WHERE rolname = %s)"
        ),
        (role,),
    ).fetchone()
    return int(row[0]) if row else 0


def _connectable_databases(conn: "psycopg.Connection[Any]") -> list[str]:
    return [
        str(row[0])
        for row in conn.execute(
            raw("SELECT datname FROM pg_catalog.pg_database WHERE datallowconn ORDER BY datname")
        ).fetchall()
    ]


def remove_roles(admin_url: str, *, names: RoleNames = DEFAULT_NAMES) -> list[str]:
    """Drop what the roles hold and then the roles, but only when they own nothing any more."""
    return _drop_roles(admin_url, names)


def _drop_roles(admin_url: str, names: RoleNames) -> list[str]:
    statements: list[str] = []
    with connect(admin_url, database="postgres") as conn:
        present = [
            str(row[0])
            for row in conn.execute(
                raw("SELECT rolname FROM pg_catalog.pg_roles WHERE rolname = ANY(%s)"),
                (list(names.all()),),
            ).fetchall()
        ]
        for role in present:
            owned = _owned_count(conn, role)
            if owned:
                raise AdoptRefusedError(
                    f"role {role} still owns {owned} object(s); reassign ownership first "
                    "(db-adopt --rollback)"
                )
        sessions = _runtime_sessions(conn, names)
        if sessions:
            raise AdoptRefusedError(f"{sessions} session(s) of the roles exist; stop them first")
        databases = _connectable_databases(conn)
    for database in databases:
        with connect(admin_url, database=database) as scoped:
            for role in present:
                statement = f"DROP OWNED BY {quote_ident(role)}"
                scoped.execute(raw(statement))
                statements.append(f"{statement} (database {database})")
    with connect(admin_url, database="postgres") as conn:
        for role in present:
            statement = f"DROP ROLE {quote_ident(role)}"
            conn.execute(raw(statement))
            statements.append(statement)
    return statements


def _owned_by_database(conn: "psycopg.Connection[Any]", role: str) -> dict[str, int]:
    """Objects a role owns, per database (`pg_shdepend` is a cluster-wide catalogue)."""
    rows = conn.execute(
        raw(
            "SELECT d.datname, count(*) FROM pg_catalog.pg_shdepend s "
            "JOIN pg_catalog.pg_database d ON d.oid = s.dbid "
            "WHERE s.deptype = 'o' "
            "AND s.classid <> 'pg_catalog.pg_default_acl'::pg_catalog.regclass "
            "AND s.refclassid = 'pg_catalog.pg_authid'::pg_catalog.regclass "
            "AND s.refobjid = (SELECT oid FROM pg_catalog.pg_roles WHERE rolname = %s) "
            "GROUP BY d.datname ORDER BY d.datname"
        ),
        (role,),
    ).fetchall()
    return {str(name): int(count) for name, count in rows}


def rollback_adoption(
    admin_url: str,
    *,
    database: str,
    names: RoleNames = DEFAULT_NAMES,
    remove_roles: bool = False,
) -> RollbackReport:
    """Give the objects of ONE database back to the administrator; optionally remove the roles.

    Only the named database is touched (PG-07). Objects the migrator owns in other databases are
    reported and left alone, and removing the roles stays refused until none is left.
    """
    refuse_system_database(database, "db-adopt --rollback")
    quote_ident(database)
    statements: list[str] = []
    with connect(admin_url, database="postgres") as conn:
        admin_row = conn.execute(raw("SELECT current_user")).fetchone()
        admin = str(admin_row[0]) if admin_row else ""
        exists = conn.execute(
            raw("SELECT 1 FROM pg_catalog.pg_roles WHERE rolname = %s"), (names.migrator,)
        ).fetchone()
        sessions = _runtime_sessions(conn, names)
        databases = _connectable_databases(conn)
        owned_elsewhere = (
            tuple(name for name in _owned_by_database(conn, names.migrator) if name != database)
            if exists is not None
            else ()
        )
    if database not in databases:
        raise AdoptRefusedError(
            f"database {database} does not exist or does not accept connections"
        )
    if sessions:
        raise AdoptRefusedError(f"{sessions} session(s) of the roles exist; stop them first")
    if remove_roles and owned_elsewhere:
        # Refuse BEFORE the first change: removing the roles cannot succeed, so do not half-do it.
        raise AdoptRefusedError(
            f"role {names.migrator} still owns objects in: {', '.join(owned_elsewhere)}; "
            "run db-adopt --rollback --database <name> for each of them first, "
            "then remove the roles with the last one (nothing was changed)"
        )
    if exists is not None:
        target = quote_catalog_name(admin)
        with connect(admin_url, database=database) as scoped:
            statement = f"REASSIGN OWNED BY {quote_ident(names.migrator)} TO {target}"
            scoped.execute(raw(statement))
            statements.append(f"{statement} (database {database})")
        with connect(admin_url, database="postgres") as conn:
            if _owned_by_database(conn, names.migrator).get(database):
                raise AdoptRefusedError(
                    f"the migrator still owns objects in {database} after the reassignment"
                )
    first_removal = len(statements)
    if remove_roles:
        statements.extend(_drop_roles(admin_url, names))
    return RollbackReport(
        tuple(statements),
        first_removal,
        owners_verified=exists is not None,
        other_databases=owned_elsewhere,
    )
