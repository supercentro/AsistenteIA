"""`db-grants`: the privilege matrix rendered as SQL and applied atomically (task 4.4).

For every table of the matrix the statements first revoke everything from `PUBLIC` and from each
runtime role at table level (a column-level `REVOKE` does not remove a table-level grant, H12) and
then grant exactly the matrix. All of it runs in one transaction as the migrator, who owns the
tables: a concurrent reader never sees the gap between the revoke and the grant (B-03), and a
failure leaves the previous grants untouched. Tables the matrix does not mention keep the
owner-only default; `alembic_version` is closed to every role.
"""

from collections.abc import Mapping, Sequence
from typing import Final

import psycopg

from app.db_admin.connection import connect, run_steps
from app.db_admin.errors import DbAdminError
from app.db_admin.names import DEFAULT_NAMES, RoleNames
from app.db_admin.sql import Step, quote_ident, quote_qualified, raw
from app.db_privileges import MATRIX, TableGrant

CLOSED_TABLES: Final = ("alembic_version",)


def _columns(grant_columns: frozenset[str], table: str, all_columns: Sequence[str]) -> str | None:
    """`None` for a table-level grant (every column), else the quoted column list."""
    unknown = grant_columns - set(all_columns)
    if unknown:
        raise DbAdminError(f"the matrix names {len(unknown)} column(s) that {table} does not have")
    if grant_columns == set(all_columns):
        return None
    return ", ".join(quote_ident(column) for column in sorted(grant_columns))


def grant_statements(
    matrix: Mapping[str, Mapping[str, TableGrant]],
    names: RoleNames,
    columns: Mapping[str, Sequence[str]],
) -> list[str]:
    """Revokes first, then grants; deterministic and free of duplicates."""
    roles = {logical: names.for_logical(logical) for logical in matrix}
    quoted_roles = {logical: quote_ident(role) for logical, role in roles.items()}
    tables = sorted({table for per_role in matrix.values() for table in per_role})
    for table in tables:
        if table not in columns:
            raise DbAdminError(
                f"the matrix decides table {table} but the database has no such table"
            )

    statements: list[str] = []
    for table in [*tables, *CLOSED_TABLES]:
        quoted_table = quote_qualified("public", table)
        statements.append(f"REVOKE ALL ON TABLE {quoted_table} FROM PUBLIC")
        for logical in roles:
            statements.append(f"REVOKE ALL ON TABLE {quoted_table} FROM {quoted_roles[logical]}")
    for table in tables:
        quoted_table = quote_qualified("public", table)
        for logical, per_role in matrix.items():
            grant = per_role.get(table)
            if grant is None:
                continue
            target = quoted_roles[logical]
            for privilege, selected in (
                ("SELECT", grant.select),
                ("INSERT", grant.insert),
                ("UPDATE", grant.update),
            ):
                if not selected:
                    continue
                listed = _columns(selected, table, columns[table])
                if listed is None:
                    statements.append(f"GRANT {privilege} ON TABLE {quoted_table} TO {target}")
                else:
                    statements.append(
                        f"GRANT {privilege} ({listed}) ON TABLE {quoted_table} TO {target}"
                    )
            if grant.delete:
                statements.append(f"GRANT DELETE ON TABLE {quoted_table} TO {target}")
    return statements


def apply_grants(
    migrator_url: str,
    *,
    names: RoleNames = DEFAULT_NAMES,
    matrix: Mapping[str, Mapping[str, TableGrant]] = MATRIX,
) -> int:
    """Apply the matrix in one transaction as the migrator; return the number of statements."""
    with connect(migrator_url, autocommit=False, lock_timeout_ms=10_000) as conn:
        who = conn.execute(raw("SELECT current_user")).fetchone()
        if who is None or who[0] != names.migrator:
            raise DbAdminError("the grants must run as the migrator role (check the URL)")
        rows = conn.execute(
            raw(
                "SELECT table_name, column_name FROM information_schema.columns "
                "WHERE table_schema = 'public' ORDER BY table_name, ordinal_position"
            )
        ).fetchall()
        columns: dict[str, list[str]] = {}
        for table, column in rows:
            columns.setdefault(str(table), []).append(str(column))
        decided = {t for per_role in matrix.values() for t in per_role}
        relevant = {t: c for t, c in columns.items() if t in decided}
        statements = grant_statements(matrix, names, relevant)
        steps = [Step(_describe(sql), sql) for sql in statements]
        try:
            count = run_steps(conn, steps)
        except DbAdminError as exc:
            conn.rollback()
            raise DbAdminError(f"grants failed and were rolled back: {exc}") from None
        except psycopg.Error:  # pragma: no cover - run_steps wraps driver errors
            conn.rollback()
            raise
        conn.commit()
        return count


def _describe(sql: str) -> str:
    return " ".join(sql.split()[:6]) + " ..."
