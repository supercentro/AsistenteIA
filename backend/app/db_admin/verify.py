"""`db-verify`: compare the live catalog with the design (task 4.5).

Read-only (the session is opened with `default_transaction_read_only = on`) and run as the
migrator, who can read every catalog it needs. Each check answers with `Finding`s; an empty list
means the database is exactly what the design says. Findings are built from catalog names and
counts only: no password, verifier or URL ever reaches them. The login probe connects once per
role with the password it is given and reports only whether that worked.
"""

from dataclasses import dataclass
from typing import Any

import psycopg
from sqlalchemy.engine import make_url

from app.db_admin.connection import check_identity, connect, tls_parameters
from app.db_admin.names import (
    CONNECTION_LIMITS,
    DEFAULT_NAMES,
    SEARCH_PATHS,
    RoleNames,
    RolePasswords,
)
from app.db_admin.sql import raw
from app.db_privileges import MATRIX, TableGrant

CLOSED_TABLES = ("alembic_version",)
_LOGICAL = ("migrator", "app", "worker", "cli")
Conn = "psycopg.Connection[Any]"


@dataclass(frozen=True)
class Finding:
    check: str
    detail: str


def render_findings(findings: list[Finding]) -> str:
    if not findings:
        return "no findings: the database matches the design"
    return "\n".join(f"[{f.check}] {f.detail}" for f in findings)


def _rows(conn: "psycopg.Connection[Any]", sql: str, params: tuple[object, ...] = ()) -> list[Any]:
    return list(conn.execute(raw(sql), params).fetchall())


def _role_checks(conn: "psycopg.Connection[Any]", names: RoleNames) -> list[Finding]:
    findings: list[Finding] = []
    rows = {
        str(r[0]): r
        for r in _rows(
            conn,
            "SELECT rolname, rolcanlogin, rolsuper, rolcreatedb, rolcreaterole, rolreplication, "
            "rolbypassrls, rolinherit, rolconnlimit, rolconfig FROM pg_catalog.pg_roles "
            "WHERE rolname = ANY(%s)",
            (list(names.all()),),
        )
    }
    for logical in _LOGICAL:
        role = getattr(names, logical)
        row = rows.get(role)
        if row is None:
            findings.append(Finding("role-attributes", f"role {role} does not exist"))
            continue
        _, login, sup, createdb, createrole, replication, bypass, inherit, limit, config = row
        if not login or not inherit:
            findings.append(Finding("role-attributes", f"{role}: LOGIN/INHERIT is not as designed"))
        for flag, label in (
            (sup, "SUPERUSER"),
            (createdb, "CREATEDB"),
            (createrole, "CREATEROLE"),
            (replication, "REPLICATION"),
            (bypass, "BYPASSRLS"),
        ):
            if flag:
                findings.append(Finding("role-attributes", f"{role} has {label}"))
        if limit != CONNECTION_LIMITS[logical]:
            findings.append(
                Finding(
                    "role-attributes",
                    f"{role}: connection limit {limit}, expected {CONNECTION_LIMITS[logical]}",
                )
            )
        if config != [f"search_path={SEARCH_PATHS[logical]}"]:
            findings.append(
                Finding("role-settings", f"{role}: persistent settings differ from the design")
            )
    members = _rows(
        conn,
        "SELECT m.rolname, g.rolname FROM pg_catalog.pg_auth_members am "
        "JOIN pg_catalog.pg_roles m ON m.oid = am.member "
        "JOIN pg_catalog.pg_roles g ON g.oid = am.roleid "
        "WHERE m.rolname = ANY(%s) OR g.rolname = ANY(%s)",
        (list(names.all()), list(names.all())),
    )
    findings.extend(Finding("memberships", f"{m} is a member of {g}") for m, g in members)
    return findings


def _database_checks(conn: "psycopg.Connection[Any]", names: RoleNames) -> list[Finding]:
    findings: list[Finding] = []
    current = str(_rows(conn, "SELECT current_database()")[0][0])
    public = _rows(
        conn,
        "SELECT d.datname FROM pg_catalog.pg_database d, LATERAL pg_catalog.aclexplode("
        "coalesce(d.datacl, pg_catalog.acldefault('d', d.datdba))) a WHERE a.grantee = 0 "
        "GROUP BY d.datname ORDER BY d.datname",
    )
    findings.extend(
        Finding("databases", f"PUBLIC has privileges on database {n}") for (n,) in public
    )
    for role in names.all():
        for (name,) in _rows(
            conn,
            "SELECT datname FROM pg_catalog.pg_database "
            "WHERE pg_catalog.has_database_privilege(%s, datname, 'CONNECT') ORDER BY datname",
            (role,),
        ):
            if name != current:
                findings.append(Finding("databases", f"{role} can connect to database {name}"))
        if not _rows(
            conn,
            "SELECT pg_catalog.has_database_privilege(%s, current_database(), 'CONNECT')",
            (role,),
        )[0][0]:
            findings.append(Finding("databases", f"{role} cannot connect to {current}"))
    return findings


def _schema_checks(conn: "psycopg.Connection[Any]", names: RoleNames) -> list[Finding]:
    findings: list[Finding] = []
    if _rows(
        conn,
        "SELECT 1 FROM pg_catalog.pg_namespace n, LATERAL pg_catalog.aclexplode("
        "coalesce(n.nspacl, pg_catalog.acldefault('n', n.nspowner))) a "
        "WHERE n.nspname = 'public' AND a.grantee = 0",
    ):
        findings.append(Finding("schema", "PUBLIC has privileges on schema public"))
    for role in names.all():
        usage, create = _rows(
            conn,
            "SELECT pg_catalog.has_schema_privilege(%s, 'public', 'USAGE'), "
            "pg_catalog.has_schema_privilege(%s, 'public', 'CREATE')",
            (role, role),
        )[0]
        if not usage:
            findings.append(Finding("schema", f"{role} cannot use schema public"))
        if create != (role == names.migrator):
            findings.append(
                Finding("schema", f"{role}: CREATE on schema public is not as designed")
            )
    for (name,) in _rows(
        conn,
        "SELECT nspname FROM pg_catalog.pg_namespace WHERE nspname NOT LIKE 'pg\\_%%' "
        "AND nspname NOT IN ('public', 'information_schema') ORDER BY nspname",
    ):
        findings.append(Finding("schema", f"unexpected schema {name}"))
    return findings


def _ownership_checks(conn: "psycopg.Connection[Any]", names: RoleNames) -> list[Finding]:
    findings: list[Finding] = []
    rows = _rows(
        conn,
        "SELECT 'table ' || c.relname, r.rolname FROM pg_catalog.pg_class c "
        "JOIN pg_catalog.pg_roles r ON r.oid = c.relowner "
        "WHERE c.relnamespace = 'public'::pg_catalog.regnamespace AND c.relkind IN ('r', 'S') "
        "AND NOT EXISTS (SELECT 1 FROM pg_catalog.pg_depend d WHERE d.objid = c.oid "
        "AND d.deptype = 'e') "
        "UNION ALL SELECT 'type ' || t.typname, r.rolname FROM pg_catalog.pg_type t "
        "JOIN pg_catalog.pg_roles r ON r.oid = t.typowner "
        "WHERE t.typnamespace = 'public'::pg_catalog.regnamespace AND t.typtype = 'e'",
    )
    findings.extend(
        Finding("ownership", f"{what} is owned by {owner}, expected {names.migrator}")
        for what, owner in rows
        if owner != names.migrator
    )
    return findings


def _expected_sets(grant: TableGrant | None) -> dict[str, frozenset[str]]:
    if grant is None:
        return {"SELECT": frozenset(), "INSERT": frozenset(), "UPDATE": frozenset()}
    return {"SELECT": grant.select, "INSERT": grant.insert, "UPDATE": grant.update}


def _privilege_checks(conn: "psycopg.Connection[Any]", names: RoleNames) -> list[Finding]:
    findings: list[Finding] = []
    tables = {
        str(n): int(o)
        for n, o in _rows(
            conn,
            "SELECT c.relname, c.oid FROM pg_catalog.pg_class c "
            "WHERE c.relnamespace = 'public'::pg_catalog.regnamespace AND c.relkind = 'r' "
            "AND NOT EXISTS (SELECT 1 FROM pg_catalog.pg_depend d WHERE d.objid = c.oid "
            "AND d.deptype = 'e')",
        )
    }
    decided = {t for per_role in MATRIX.values() for t in per_role}
    for table in sorted(decided - set(tables)):
        findings.append(
            Finding("tables", f"table {table} is in the matrix but not in the database")
        )
    for table in sorted(set(tables) - decided - set(CLOSED_TABLES)):
        findings.append(Finding("tables", f"table {table} has no decision in the matrix"))
    for (table,) in _rows(
        conn,
        "SELECT DISTINCT c.relname FROM pg_catalog.pg_class c, LATERAL pg_catalog.aclexplode("
        "coalesce(c.relacl, pg_catalog.acldefault('r', c.relowner))) a "
        "WHERE c.relnamespace = 'public'::pg_catalog.regnamespace AND c.relkind = 'r' "
        "AND a.grantee = 0 ORDER BY 1",
    ):
        findings.append(Finding("privileges", f"PUBLIC has privileges on table {table}"))

    for logical, per_role in MATRIX.items():
        role = names.for_logical(logical)
        for table, oid in sorted(tables.items()):
            expected = _expected_sets(per_role.get(table))
            actual: dict[str, set[str]] = {"SELECT": set(), "INSERT": set(), "UPDATE": set()}
            for column, attnum in _rows(
                conn,
                "SELECT attname, attnum FROM pg_catalog.pg_attribute "
                "WHERE attrelid = %s::pg_catalog.oid AND attnum > 0 AND NOT attisdropped",
                (oid,),
            ):
                for privilege in actual:
                    if _rows(
                        conn,
                        "SELECT pg_catalog.has_column_privilege(%s, %s::pg_catalog.oid, %s::smallint, %s)",  # noqa: E501
                        (role, oid, attnum, privilege),
                    )[0][0]:
                        actual[privilege].add(str(column))
            for privilege, wanted in expected.items():
                extra = actual[privilege] - wanted
                missing = set(wanted) - actual[privilege]
                if extra:
                    findings.append(
                        Finding(
                            "privileges",
                            f"{role} has {privilege} ({', '.join(sorted(extra))}) on {table} "
                            "that the matrix does not grant",
                        )
                    )
                if missing:
                    findings.append(
                        Finding(
                            "privileges",
                            f"{role} lacks {privilege} ({', '.join(sorted(missing))}) on {table}",
                        )
                    )
            wants_delete = per_role.get(table, TableGrant()).delete
            has_delete = _rows(
                conn,
                "SELECT pg_catalog.has_table_privilege(%s, %s::pg_catalog.oid, 'DELETE')",
                (role, oid),
            )[0][0]
            if bool(has_delete) != wants_delete:
                findings.append(
                    Finding("privileges", f"{role} DELETE on {table} differs from the matrix")
                )
            for other in ("TRUNCATE", "REFERENCES", "TRIGGER"):
                if _rows(
                    conn,
                    "SELECT pg_catalog.has_table_privilege(%s, %s::pg_catalog.oid, %s)",
                    (role, oid, other),
                )[0][0]:
                    findings.append(Finding("privileges", f"{role} has {other} on {table}"))
    return findings


def _extra_checks(conn: "psycopg.Connection[Any]", names: RoleNames) -> list[Finding]:
    """Drift kinds beyond the matrix: grant options, strangers in the ACLs, per-database role
    settings, database-level rights, row-level security, other types, statement logging."""
    findings: list[Finding] = []
    roles = list(names.all())
    for table, grantee in _rows(
        conn,
        "SELECT DISTINCT c.relname, a.grantee::pg_catalog.regrole::pg_catalog.text "
        "FROM pg_catalog.pg_class c, LATERAL pg_catalog.aclexplode("
        "coalesce(c.relacl, pg_catalog.acldefault('r', c.relowner))) a "
        "WHERE c.relnamespace = 'public'::pg_catalog.regnamespace AND c.relkind = 'r' "
        "AND a.grantee <> 0 AND a.grantee <> c.relowner "
        "AND NOT (a.grantee::pg_catalog.regrole::pg_catalog.text = ANY(%s)) ORDER BY 1, 2",
        (roles,),
    ):
        findings.append(
            Finding("privileges", f"{grantee}, outside the four roles, has privileges on {table}")
        )
    for table, role in _rows(
        conn,
        "SELECT c.relname, r.rolname FROM pg_catalog.pg_class c, pg_catalog.pg_roles r "
        "WHERE c.relnamespace = 'public'::pg_catalog.regnamespace AND c.relkind = 'r' "
        "AND r.rolname = ANY(%s) AND r.oid <> c.relowner AND pg_catalog.has_table_privilege(r.oid, c.oid, "  # noqa: E501
        "'SELECT WITH GRANT OPTION, INSERT WITH GRANT OPTION, UPDATE WITH GRANT OPTION, "
        "DELETE WITH GRANT OPTION') ORDER BY 1, 2",
        (roles,),
    ):
        findings.append(Finding("privileges", f"{role} holds a grant option on {table}"))
    for role in roles:
        if _rows(
            conn,
            "SELECT pg_catalog.has_database_privilege(%s, pg_catalog.current_database(), "
            "'TEMPORARY, CREATE')",
            (role,),
        )[0][0]:
            findings.append(Finding("databases", f"{role} has TEMPORARY or CREATE on the database"))
    for database, role in _rows(
        conn,
        "SELECT coalesce(d.datname, '(all)'), r.rolname FROM pg_catalog.pg_db_role_setting s "
        "JOIN pg_catalog.pg_roles r ON r.oid = s.setrole "
        "LEFT JOIN pg_catalog.pg_database d ON d.oid = s.setdatabase "
        "WHERE r.rolname = ANY(%s) AND s.setdatabase <> 0 ORDER BY 1, 2",
        (roles,),
    ):
        findings.append(Finding("role-settings", f"{role} has settings for database {database}"))
    for (table,) in _rows(
        conn,
        "SELECT c.relname FROM pg_catalog.pg_class c "
        "WHERE c.relnamespace = 'public'::pg_catalog.regnamespace AND c.relkind = 'r' "
        "AND (c.relrowsecurity OR c.relforcerowsecurity) ORDER BY 1",
    ):
        findings.append(Finding("row-level-security", f"row-level security is enabled on {table}"))
    for (name,) in _rows(
        conn,
        "SELECT p.polname FROM pg_catalog.pg_policy p JOIN pg_catalog.pg_class c ON c.oid = p.polrelid "  # noqa: E501
        "WHERE c.relnamespace = 'public'::pg_catalog.regnamespace ORDER BY 1",
    ):
        findings.append(Finding("row-level-security", f"policy {name} exists on a table of public"))
    for name, kind in _rows(
        conn,
        "SELECT t.typname, t.typtype FROM pg_catalog.pg_type t "
        "WHERE t.typnamespace = 'public'::pg_catalog.regnamespace AND t.typelem = 0 "
        "AND t.typrelid = 0 AND t.typtype <> 'e' AND NOT EXISTS (SELECT 1 FROM pg_catalog.pg_depend d "  # noqa: E501
        "WHERE d.objid = t.oid AND d.deptype = 'e') ORDER BY 1",
    ):
        findings.append(Finding("foreign-objects", f"type {name} of kind {kind} in schema public"))
    if _rows(conn, "SELECT pg_catalog.current_setting('log_statement')")[0][0] != "none":
        findings.append(
            Finding("server-settings", "log_statement is not none: statements are logged")
        )
    return findings


def _sequence_checks(conn: "psycopg.Connection[Any]", names: RoleNames) -> list[Finding]:
    findings: list[Finding] = []
    for name, oid in _rows(
        conn,
        "SELECT relname, oid FROM pg_catalog.pg_class "
        "WHERE relnamespace = 'public'::pg_catalog.regnamespace AND relkind = 'S'",
    ):
        for role in names.runtime():
            if _rows(
                conn,
                "SELECT pg_catalog.has_sequence_privilege(%s, %s::pg_catalog.oid, 'USAGE,SELECT,UPDATE')",  # noqa: E501
                (role, oid),
            )[0][0]:
                findings.append(Finding("sequences", f"{role} has privileges on sequence {name}"))
    return findings


def _foreign_object_checks(conn: "psycopg.Connection[Any]") -> list[Finding]:
    findings: list[Finding] = []
    not_extension = "NOT EXISTS (SELECT 1 FROM pg_catalog.pg_depend d WHERE d.objid = {oid} AND d.deptype = 'e')"  # noqa: E501
    for (signature,) in _rows(
        conn,
        "SELECT p.proname || '(' || pg_catalog.pg_get_function_identity_arguments(p.oid) || ')' "
        "FROM pg_catalog.pg_proc p WHERE p.pronamespace = 'public'::pg_catalog.regnamespace AND "
        + not_extension.format(oid="p.oid")
        + " ORDER BY 1",
    ):
        findings.append(Finding("foreign-objects", f"function {signature} in schema public"))
    for (name,) in _rows(
        conn,
        "SELECT o.oprname || '(' || o.oprleft::pg_catalog.regtype::text || ', ' || "
        "o.oprright::pg_catalog.regtype::text || ')' FROM pg_catalog.pg_operator o "
        "WHERE o.oprnamespace = 'public'::pg_catalog.regnamespace AND "
        + not_extension.format(oid="o.oid"),
    ):
        findings.append(Finding("foreign-objects", f"operator {name} in schema public"))
    for name, kind in _rows(
        conn,
        "SELECT c.relname, c.relkind FROM pg_catalog.pg_class c "
        "WHERE c.relnamespace = 'public'::pg_catalog.regnamespace AND c.relkind IN ('v', 'm', 'f', 'p', 'c') "  # noqa: E501
        "AND " + not_extension.format(oid="c.oid"),
    ):
        findings.append(
            Finding("foreign-objects", f"relation {name} of kind {kind} in schema public")
        )
    for (name,) in _rows(
        conn,
        "SELECT tgname FROM pg_catalog.pg_trigger t JOIN pg_catalog.pg_class c ON c.oid = t.tgrelid "  # noqa: E501
        "WHERE NOT t.tgisinternal AND c.relnamespace = 'public'::pg_catalog.regnamespace",
    ):
        findings.append(Finding("foreign-objects", f"trigger {name} on a table of schema public"))
    return findings


def _default_privilege_and_extension_checks(
    conn: "psycopg.Connection[Any]", names: RoleNames
) -> list[Finding]:
    findings: list[Finding] = []
    rows = _rows(
        conn,
        "SELECT d.defaclobjtype, "
        "EXISTS (SELECT 1 FROM pg_catalog.aclexplode(d.defaclacl) a WHERE a.grantee <> d.defaclrole) "  # noqa: E501
        "FROM pg_catalog.pg_default_acl d JOIN pg_catalog.pg_roles r ON r.oid = d.defaclrole "
        "WHERE r.rolname = %s",
        (names.migrator,),
    )
    functions = [granted for kind, granted in rows if kind == "f"]
    if not functions:
        findings.append(
            Finding("default-privileges", "functions of the migrator are executable by PUBLIC")
        )
    elif any(functions):
        findings.append(
            Finding("default-privileges", "new functions are executable by PUBLIC or another role")
        )
    others = [kind for kind, _ in rows if kind != "f"]
    if others:
        findings.append(Finding("default-privileges", "unexpected default privileges exist"))
    if not _rows(
        conn,
        "SELECT 1 FROM pg_catalog.pg_extension e JOIN pg_catalog.pg_namespace n "
        "ON n.oid = e.extnamespace WHERE e.extname = 'vector' AND n.nspname = 'public'",
    ):
        findings.append(Finding("extensions", "the vector extension is not installed in public"))
    return findings


def _login_probe(migrator_url: str, passwords: RolePasswords, names: RoleNames) -> list[Finding]:
    findings: list[Finding] = []
    parts = make_url(migrator_url)
    for logical in _LOGICAL:
        role = getattr(names, logical)
        try:
            with psycopg.connect(
                host=parts.host,
                port=parts.port,
                user=role,
                password=getattr(passwords, logical),
                dbname=parts.database,
                connect_timeout=10,
                application_name="asistenteia-db-verify",
                **tls_parameters(parts),
            ) as probe:
                row = probe.execute(
                    raw("SELECT current_setting('is_superuser'), current_setting('search_path')")
                ).fetchone()
        except psycopg.Error as exc:
            findings.append(
                Finding("login-probe", f"{role} cannot log in (SQLSTATE {exc.sqlstate or 'none'})")
            )
            continue
        if row is None or row[0] != "off" or row[1] != SEARCH_PATHS[logical]:
            findings.append(
                Finding("login-probe", f"{role}: session settings differ from the design")
            )
    return findings


def verify(
    migrator_url: str,
    passwords: RolePasswords,
    *,
    names: RoleNames = DEFAULT_NAMES,
) -> list[Finding]:
    """Return every difference between the live database and the design (empty = identical)."""
    findings: list[Finding] = []
    with connect(migrator_url, read_only=True) as conn:
        check_identity(conn, names.migrator, "db-verify")
        for check in (
            _role_checks,
            _database_checks,
            _schema_checks,
            _ownership_checks,
            _privilege_checks,
            _sequence_checks,
            _default_privilege_and_extension_checks,
            _extra_checks,
        ):
            findings.extend(check(conn, names))
        findings.extend(_foreign_object_checks(conn))
    findings.extend(_login_probe(migrator_url, passwords, names))
    return findings
