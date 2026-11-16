"""`db-migrate`, `db-downgrade` and `db-verify` check the migrator identity first (PG-02, 15.2).

A wrong URL (the administrator pasted by mistake, or another role) must stop the command before
Alembic runs any statement: no table owned by the administrator, no changed revision, no changed
privilege. Disposable cluster, real roles.
"""

import argparse
import secrets
from collections.abc import Callable

import pytest

from app.db_admin.bootstrap import bootstrap
from app.db_admin.commands import run_database_command
from app.db_admin.errors import DbAdminError
from app.db_admin.migrate import downgrade, migrate
from app.db_admin.verify import verify
from tests.db_admin_support import Cluster
from tests.db_admin_support import cluster as cluster  # noqa: F401  (fixture)
from tests.db_admin_support import scratch_database as scratch_database  # noqa: F401  (fixture)
from tests.db_roles_support import own_database as own_database


@pytest.fixture
def bootstrapped(cluster: Cluster, scratch_database: Callable[[], str]) -> str:
    """A database with the roles and the schema rules but NO tables yet."""
    database = scratch_database()
    bootstrap(cluster.admin("postgres"), cluster.passwords, database=database, names=cluster.names)
    return database


def tables(cluster: Cluster, database: str) -> list[str]:
    with cluster.admin_connection(database) as conn:
        rows = conn.execute(
            "SELECT tablename FROM pg_catalog.pg_tables WHERE schemaname = 'public' ORDER BY 1"
        ).fetchall()
    return [str(row[0]) for row in rows]


def revision(cluster: Cluster, database: str) -> str:
    with cluster.admin_connection(database) as conn:
        row = conn.execute("SELECT version_num FROM alembic_version").fetchone()
    assert row is not None
    return str(row[0])


def owners(cluster: Cluster, database: str) -> set[str]:
    with cluster.admin_connection(database) as conn:
        rows = conn.execute(
            "SELECT DISTINCT tableowner FROM pg_catalog.pg_tables WHERE schemaname = 'public'"
        ).fetchall()
    return {str(row[0]) for row in rows}


# --- migrate --------------------------------------------------------------------------------


def test_migrate_as_the_administrator_is_refused_before_any_ddl(
    cluster: Cluster, bootstrapped: str
) -> None:
    with pytest.raises(DbAdminError) as refused:
        migrate(cluster.admin(bootstrapped), names=cluster.names)

    assert cluster.names.migrator in str(refused.value)
    assert tables(cluster, bootstrapped) == []  # Alembic never ran: not even alembic_version


def test_migrate_as_another_role_is_refused_before_any_ddl(
    cluster: Cluster, bootstrapped: str
) -> None:
    with pytest.raises(DbAdminError):
        migrate(cluster.role_url("app", bootstrapped), names=cluster.names)

    assert tables(cluster, bootstrapped) == []


def test_migrate_as_the_migrator_still_works(cluster: Cluster, bootstrapped: str) -> None:
    migrate(cluster.migrator_url(bootstrapped), names=cluster.names)

    assert "users" in tables(cluster, bootstrapped)
    assert owners(cluster, bootstrapped) == {cluster.names.migrator}


# --- downgrade ------------------------------------------------------------------------------


def test_downgrade_as_the_administrator_changes_nothing(
    cluster: Cluster, own_database: str
) -> None:
    before = revision(cluster, own_database)

    with pytest.raises(DbAdminError):
        downgrade(cluster.admin(own_database), "0005", names=cluster.names)

    assert revision(cluster, own_database) == before
    assert owners(cluster, own_database) == {cluster.names.migrator}


def test_downgrade_as_another_role_changes_nothing(cluster: Cluster, own_database: str) -> None:
    before = revision(cluster, own_database)

    with pytest.raises(DbAdminError):
        downgrade(cluster.role_url("worker", own_database), "0005", names=cluster.names)

    assert revision(cluster, own_database) == before


def test_downgrade_as_the_migrator_still_works(cluster: Cluster, own_database: str) -> None:
    downgrade(cluster.migrator_url(own_database), "0005", names=cluster.names)

    assert revision(cluster, own_database) == "0005"


# --- verify ---------------------------------------------------------------------------------


def test_verify_as_the_administrator_is_refused(cluster: Cluster, own_database: str) -> None:
    with pytest.raises(DbAdminError) as refused:
        verify(cluster.admin(own_database), cluster.passwords, names=cluster.names)

    assert cluster.names.migrator in str(refused.value)


def test_verify_as_another_role_is_refused(cluster: Cluster, own_database: str) -> None:
    with pytest.raises(DbAdminError):
        verify(cluster.role_url("app", own_database), cluster.passwords, names=cluster.names)


# --- connection and permission failures -----------------------------------------------------


def test_an_unreachable_server_is_an_error_that_does_not_echo_the_password(
    cluster: Cluster,
) -> None:
    secret = secrets.token_urlsafe(18)
    url = cluster.url(cluster.names.migrator, secret, "nowhere").replace(":5432", ":1")
    for call in (
        lambda: migrate(url, names=cluster.names),
        lambda: downgrade(url, "0005", names=cluster.names),
        lambda: verify(url, cluster.passwords, names=cluster.names),
    ):
        with pytest.raises(DbAdminError) as refused:
            call()
        assert secret not in str(refused.value)


def test_a_wrong_password_is_refused_by_postgresql_before_any_change(
    cluster: Cluster, bootstrapped: str
) -> None:
    secret = secrets.token_urlsafe(18)
    url = cluster.url(cluster.names.migrator, secret, bootstrapped)

    with pytest.raises(DbAdminError) as refused:
        migrate(url, names=cluster.names)

    assert secret not in str(refused.value)
    assert tables(cluster, bootstrapped) == []


# --- the command line -----------------------------------------------------------------------


def run_command(
    monkeypatch: pytest.MonkeyPatch, url: str, **arguments: object
) -> tuple[int, list[str], list[str]]:
    out: list[str] = []
    err: list[str] = []
    monkeypatch.setenv("MIGRATION_DATABASE_URL", url)
    args = argparse.Namespace(**arguments)
    return run_database_command(args, out.append, err.append), out, err


def test_the_command_db_migrate_exits_non_zero_for_the_administrator_url(
    cluster: Cluster, bootstrapped: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    # The command line uses the default role names; the test roles carry a prefix, so the URL of the
    # real migrator name does not exist here. What matters: it is refused and nothing is created.
    code, out, err = run_command(
        monkeypatch, cluster.admin(bootstrapped), command="db-migrate", downgrade=None
    )

    assert code == 1
    assert out == []
    assert any("migrator" in line for line in err)
    assert tables(cluster, bootstrapped) == []
