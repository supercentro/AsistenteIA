"""The denied-operation suite of the four roles (change `database-least-privilege`, task 5.5).

Everything here runs under a role against a disposable cluster. Each statement must fail with the
SQLSTATE PostgreSQL gives for a missing privilege (42501) and, when it could have changed
something, the test then checks with the administrator that nothing changed. Statements that are
dangerous on a real server (program execution, file reads, `ALTER SYSTEM`) are refused before they
do anything, and they only ever run in the throwaway container.
"""

from collections.abc import Callable
from typing import Any

import psycopg
import pytest

from tests.db_admin_support import Cluster
from tests.db_admin_support import cluster as cluster  # noqa: F401  (fixture)
from tests.db_admin_support import scratch_database as scratch_database  # noqa: F401  (fixture)
from tests.db_roles_support import (
    as_role,
    sqlstate_of,
)
from tests.db_roles_support import (
    prepared_database as prepared_database,
)

DENIED = "42501"

# Denied to every role, the migrator included: cluster-level and server-level power.
EVERYONE = {
    "create-role": "CREATE ROLE tstrole_evil",
    "create-database": "CREATE DATABASE tstdb_evil_test",
    "alter-system": "ALTER SYSTEM SET work_mem = '4MB'",
    "copy-to-program": "COPY (SELECT 1) TO PROGRAM 'true'",
    "copy-from-program": "COPY public.users FROM PROGRAM 'true'",
    "copy-to-file": "COPY (SELECT 1) TO '/tmp/tst_out'",
    "pg-read-binary-file": "SELECT pg_read_binary_file('/etc/passwd')",
    "pg-stat-file": "SELECT pg_stat_file('/etc/passwd')",
    "lo-export": "SELECT lo_export(1, '/tmp/tst_lo')",
    "load-library": "LOAD 'tst_library'",
    "switch-wal": "SELECT pg_switch_wal()",
    "event-trigger": (
        "CREATE EVENT TRIGGER tst_ev ON ddl_command_start EXECUTE FUNCTION public.tst_f()"
    ),
    "tablespace": "CREATE TABLESPACE tst_ts LOCATION '/tmp'",
    "publication": "CREATE PUBLICATION tst_pub FOR ALL TABLES",
    "alter-other-role-password": "ALTER ROLE {other} PASSWORD 'Hijacked-0123456789-x'",
    "alter-other-role-setting": "ALTER ROLE {other} SET search_path = public",
    "alter-other-role-in-database": (
        "ALTER ROLE {other} IN DATABASE {database} SET statement_timeout = '1ms'"
    ),
    "alter-all-roles": "ALTER ROLE ALL SET statement_timeout = '1ms'",
    "alter-own-connection-limit": "ALTER ROLE {self} CONNECTION LIMIT 0",
    "drop-other-role": "DROP ROLE {other}",
    "copy-from-file": "COPY public.users FROM '/etc/passwd'",
    "pg-read-file": "SELECT pg_read_file('/etc/passwd')",
    "pg-ls-dir": "SELECT pg_ls_dir('/')",
    "large-object-import": "SELECT lo_import('/etc/passwd')",
    "set-role-admin": "SET ROLE {admin}",
    "pg-authid": "SELECT rolpassword FROM pg_authid",
    "pg-shadow": "SELECT passwd FROM pg_shadow",
    "reload-conf": "SELECT pg_reload_conf()",
    "checkpoint": "CHECKPOINT",
    "terminate-other-session": "SELECT pg_terminate_backend({pid})",
    "cancel-other-session": "SELECT pg_cancel_backend({pid})",
    "create-extension": "CREATE EXTENSION hstore",
    "drop-extension": "DROP EXTENSION vector CASCADE",
    "temporary-table": "CREATE TEMP TABLE tst_t (x integer)",
    "create-schema": "CREATE SCHEMA tst_s",
    "alter-role-admin": "ALTER ROLE {admin} PASSWORD 'x'",
    "alter-role-superuser": "ALTER ROLE {self} SUPERUSER",
    "alter-role-bypassrls": "ALTER ROLE {self} BYPASSRLS",
    "default-privileges-of-the-admin": (
        "ALTER DEFAULT PRIVILEGES FOR ROLE {admin} GRANT SELECT ON TABLES TO PUBLIC"
    ),
    "drop-database": "DROP DATABASE {database}",
    "alter-database": "ALTER DATABASE {database} SET search_path = public",
    "grant-pg-read-all-data": "GRANT pg_read_all_data TO {self}",
}
# Denied to the runtime roles; the migrator owns the schema and may do these.
RUNTIME_ONLY = {
    "create-table": "CREATE TABLE public.tst_t (x integer)",
    "create-function": (
        "CREATE FUNCTION public.tst_f() RETURNS integer LANGUAGE sql AS 'SELECT 1'"
    ),
    "create-index": "CREATE INDEX tst_i ON public.users (name)",
    "alter-table": "ALTER TABLE public.users ADD COLUMN tst_x integer",
    "alter-owner": "ALTER TABLE public.users OWNER TO {self}",
    "drop-table": "DROP TABLE public.users CASCADE",
    "drop-schema": "DROP SCHEMA public CASCADE",
    "comment": "COMMENT ON TABLE public.users IS 'x'",
    "truncate-users": "TRUNCATE public.users",
    "truncate-alembic": "TRUNCATE public.alembic_version",
    "read-alembic-version": "SELECT version_num FROM public.alembic_version",
    "delete-alembic-version": "DELETE FROM public.alembic_version",
    "default-privileges-of-the-migrator": (
        "ALTER DEFAULT PRIVILEGES FOR ROLE {migrator} GRANT SELECT ON TABLES TO PUBLIC"
    ),
}
CASES = [(role, name) for role in ("app", "worker", "cli", "migrator") for name in EVERYONE] + [
    (role, name) for role in ("app", "worker", "cli") for name in RUNTIME_ONLY
]


def admin_name(cluster: Cluster) -> str:
    from sqlalchemy.engine import make_url

    name = make_url(cluster.admin_url).username
    assert name
    return name


@pytest.fixture(scope="module")
def foreign_pid(cluster: Cluster) -> list[psycopg.Connection[Any]]:
    """An administrator session that the roles try to terminate; kept open for the module."""
    conn = cluster.connect(cluster.admin(), application_name="tst-victim")
    return [conn]


@pytest.mark.parametrize(("logical", "name"), CASES, ids=[f"{r}-{n}" for r, n in CASES])
def test_the_statement_is_refused(
    cluster: Cluster,
    prepared_database: str,
    foreign_pid: list[psycopg.Connection[Any]],
    logical: str,
    name: str,
) -> None:
    sql = {**EVERYONE, **RUNTIME_ONLY}[name]
    pid_row = foreign_pid[0].execute("SELECT pg_backend_pid()").fetchone()
    assert pid_row is not None
    sql = sql.format(
        admin=f'"{admin_name(cluster)}"',
        self=f'"{getattr(cluster.names, logical)}"',
        migrator=f'"{cluster.names.migrator}"',
        other=f'"{next(n for n in cluster.names.all() if n != getattr(cluster.names, logical))}"',
        database=f'"{prepared_database}"',
        pid=pid_row[0],
    )

    with as_role(cluster, logical, prepared_database) as conn:
        assert sqlstate_of(conn, sql) == DENIED, (logical, name)

    assert foreign_pid[0].execute("SELECT 1").fetchone() == (1,)  # the victim session survived


@pytest.mark.parametrize("logical", ["app", "worker", "cli", "migrator"])
@pytest.mark.parametrize("target", ["postgres", "template1", "template0"])
def test_a_role_cannot_connect_to_another_database(
    cluster: Cluster, prepared_database: str, logical: str, target: str
) -> None:
    url = cluster.role_url(logical, target)

    with pytest.raises(psycopg.OperationalError) as caught:
        cluster.connect(url)

    message = str(caught.value)
    assert "permission denied" in message or "not currently accepting" in message


def test_a_database_created_after_the_bootstrap_is_open_until_the_next_run_and_verify_says_so(
    cluster: Cluster, prepared_database: str, scratch_database: Callable[[], str]
) -> None:
    # Documented residual: PUBLIC can connect to any database created after the bootstrap, because
    # a new database starts with the default ACL. `db-verify` reports it; the next run closes it.
    from app.db_admin.bootstrap import bootstrap
    from app.db_admin.verify import verify

    other = scratch_database()
    findings = verify(
        cluster.migrator_url(prepared_database), cluster.passwords, names=cluster.names
    )
    assert any(f.check == "databases" and other in f.detail for f in findings)

    bootstrap(
        cluster.admin("postgres"),
        cluster.passwords,
        database=prepared_database,
        names=cluster.names,
    )

    with pytest.raises(psycopg.OperationalError):
        cluster.connect(cluster.role_url("app", other))
    assert (
        verify(cluster.migrator_url(prepared_database), cluster.passwords, names=cluster.names)
        == []
    )


@pytest.mark.parametrize("logical", ["app", "worker", "cli"])
def test_a_role_cannot_become_another_role(
    cluster: Cluster, prepared_database: str, logical: str
) -> None:
    others = [n for n in cluster.names.all() if n != cluster.names.for_logical(logical)]
    with as_role(cluster, logical, prepared_database) as conn:
        for other in others:
            assert sqlstate_of(conn, f'SET ROLE "{other}"') == DENIED
            assert sqlstate_of(conn, f'SET SESSION AUTHORIZATION "{other}"') == DENIED


@pytest.mark.parametrize(("logical", "outcome"), [("app", None), ("cli", None), ("worker", DENIED)])
def test_granting_privileges_to_public_changes_nothing_for_a_role_that_does_not_own_the_table(
    cluster: Cluster, prepared_database: str, logical: str, outcome: str | None
) -> None:
    # A role holding some privilege but no grant option only gets a warning; one holding none is
    # refused. Either way nothing is granted (checked below with the administrator).
    with as_role(cluster, logical, prepared_database) as conn:
        assert sqlstate_of(conn, "GRANT SELECT ON public.users TO PUBLIC") == outcome

    with cluster.admin_connection(prepared_database) as conn:
        public = conn.execute(
            "SELECT count(*) FROM pg_catalog.pg_class c, LATERAL pg_catalog.aclexplode("
            "coalesce(c.relacl, pg_catalog.acldefault('r', c.relowner))) a "
            "WHERE c.relname = 'users' AND a.grantee = 0"
        ).fetchone()
    assert public == (0,)


@pytest.mark.parametrize("logical", ["app", "worker", "cli", "migrator"])
def test_session_settings_do_not_outlive_the_session(
    cluster: Cluster, prepared_database: str, logical: str
) -> None:
    with as_role(cluster, logical, prepared_database) as conn:
        conn.execute("SET statement_timeout = '1ms'")
        conn.execute("SET search_path = public")
    with as_role(cluster, logical, prepared_database) as conn:
        timeout = conn.execute("SHOW statement_timeout").fetchone()
        path = conn.execute("SHOW search_path").fetchone()
    assert timeout == ("0",)
    assert path is not None and path[0] in {"public", "pg_catalog, public"}
    if logical != "migrator":
        assert path == ("pg_catalog, public",)


@pytest.mark.parametrize(
    ("killer", "victim"), [("app", "worker"), ("worker", "app"), ("cli", "app")]
)
def test_a_runtime_role_cannot_terminate_a_session_of_another_runtime_role(
    cluster: Cluster, prepared_database: str, killer: str, victim: str
) -> None:
    with as_role(cluster, victim, prepared_database) as target:
        row = target.execute("SELECT pg_backend_pid()").fetchone()
        assert row is not None
        with as_role(cluster, killer, prepared_database) as conn:
            assert sqlstate_of(conn, f"SELECT pg_terminate_backend({row[0]})") == DENIED
            assert sqlstate_of(conn, f"SELECT pg_cancel_backend({row[0]})") == DENIED
        assert target.execute("SELECT 1").fetchone() == (1,)


def test_prepared_transactions_are_disabled_so_no_session_state_outlives_a_connection(
    cluster: Cluster, prepared_database: str
) -> None:
    with as_role(cluster, "app", prepared_database) as conn:
        assert conn.execute("SHOW max_prepared_transactions").fetchone() == ("0",)
    with cluster.connect(cluster.role_url("app", prepared_database), autocommit=False) as conn:
        conn.execute("SELECT 1")
        with pytest.raises(psycopg.Error) as caught:
            conn.execute("PREPARE TRANSACTION 'tst_tx'")
        assert caught.value.sqlstate == "55000"  # prepared transactions are disabled


def test_the_runtime_roles_cannot_use_the_catalog_to_see_other_sessions_queries(
    cluster: Cluster, prepared_database: str, foreign_pid: list[psycopg.Connection[Any]]
) -> None:
    foreign_pid[0].execute("SELECT 'tst-visible-secret-query'")
    with as_role(cluster, "app", prepared_database) as conn:
        rows = conn.execute(
            "SELECT query FROM pg_stat_activity WHERE application_name = 'tst-victim'"
        ).fetchall()
    assert rows, "the victim session must be listed"
    assert all(r[0] == "<insufficient privilege>" for r in rows)
