"""db-migrate and db-grants against a disposable cluster (change `database-least-privilege`, 4.4)."""  # noqa: E501

import threading
from collections.abc import Callable

import psycopg
import pytest
from alembic import command
from alembic.config import Config

from app.db_admin.bootstrap import bootstrap
from app.db_admin.grants import apply_grants
from app.db_admin.migrate import migrate
from app.db_privileges import APP, CLI, KNOWN_COLUMNS, MATRIX, WORKER
from tests.db_admin_support import Cluster
from tests.db_admin_support import cluster as cluster  # noqa: F401  (fixture)
from tests.db_admin_support import scratch_database as scratch_database  # noqa: F401  (fixture)
from tests.db_support import BACKEND_DIR

LOGICAL = {APP: "app", WORKER: "worker", CLI: "cli"}


def migrated(cluster: Cluster, scratch_database: Callable[[], str]) -> str:
    database = scratch_database()
    bootstrap(cluster.admin("postgres"), cluster.passwords, database=database, names=cluster.names)
    migrate(cluster.migrator_url(database), names=cluster.names)
    return database


def effective(cluster: Cluster, database: str) -> dict[tuple[str, str, str, str], bool]:
    """Every (role, table, column, privilege) the catalog answers, for the matrix tables."""
    answers: dict[tuple[str, str, str, str], bool] = {}
    with cluster.admin_connection(database) as conn:
        for logical, role in ((k, cluster.names.for_logical(k)) for k in LOGICAL):
            for table, columns in KNOWN_COLUMNS.items():
                for column in sorted(columns):
                    for privilege in ("SELECT", "INSERT", "UPDATE"):
                        row = conn.execute(
                            "SELECT pg_catalog.has_column_privilege(%s, %s, %s, %s)",
                            (role, f"public.{table}", column, privilege),
                        ).fetchone()
                        assert row is not None
                        answers[(logical, table, column, privilege)] = bool(row[0])
                row = conn.execute(
                    "SELECT pg_catalog.has_table_privilege(%s, %s, 'DELETE')",
                    (role, f"public.{table}"),
                ).fetchone()
                assert row is not None
                answers[(logical, table, "*", "DELETE")] = bool(row[0])
    return answers


def expected() -> dict[tuple[str, str, str, str], bool]:
    answers: dict[tuple[str, str, str, str], bool] = {}
    for logical in LOGICAL:
        for table, columns in KNOWN_COLUMNS.items():
            grant = MATRIX[logical][table]
            for column in columns:
                answers[(logical, table, column, "SELECT")] = column in grant.select
                answers[(logical, table, column, "INSERT")] = column in grant.insert
                answers[(logical, table, column, "UPDATE")] = column in grant.update
            answers[(logical, table, "*", "DELETE")] = grant.delete
    return answers


def test_migrate_runs_alembic_as_the_migrator_and_applies_the_matrix_exactly(
    cluster: Cluster, scratch_database: Callable[[], str]
) -> None:
    database = migrated(cluster, scratch_database)

    with cluster.admin_connection(database) as conn:
        head = conn.execute("SELECT version_num FROM alembic_version").fetchone()
        owner = conn.execute(
            "SELECT r.rolname FROM pg_catalog.pg_class c JOIN pg_catalog.pg_roles r "
            "ON r.oid = c.relowner WHERE c.relname = 'users'"
        ).fetchone()
    assert head == ("0008",) and owner == (cluster.names.migrator,)
    assert effective(cluster, database) == expected()


def test_the_closed_tables_stay_closed(
    cluster: Cluster, scratch_database: Callable[[], str]
) -> None:
    database = migrated(cluster, scratch_database)

    with cluster.admin_connection(database) as conn:
        for role in (cluster.names.app, cluster.names.worker, cluster.names.cli):
            row = conn.execute(
                "SELECT pg_catalog.has_table_privilege(%s, 'public.alembic_version', "
                "'SELECT, INSERT, UPDATE, DELETE, TRUNCATE, REFERENCES, TRIGGER')",
                (role,),
            ).fetchone()
            assert row == (False,)
        public = conn.execute(
            "SELECT count(*) FROM pg_catalog.pg_class c, "
            "LATERAL pg_catalog.aclexplode(coalesce(c.relacl, pg_catalog.acldefault('r', "
            "c.relowner))) a WHERE c.relnamespace = 'public'::regnamespace AND c.relkind = 'r' "
            "AND a.grantee = 0"
        ).fetchone()
        assert public == (0,)


def test_the_grants_are_idempotent(cluster: Cluster, scratch_database: Callable[[], str]) -> None:
    database = migrated(cluster, scratch_database)
    first = effective(cluster, database)

    count = apply_grants(cluster.migrator_url(database), names=cluster.names)
    apply_grants(cluster.migrator_url(database), names=cluster.names)

    assert count > 0 and effective(cluster, database) == first == expected()


def test_a_recreated_table_regains_its_privileges(
    cluster: Cluster, scratch_database: Callable[[], str]
) -> None:
    database = migrated(cluster, scratch_database)
    config = Config(str(BACKEND_DIR / "alembic.ini"))
    config.set_main_option("script_location", str(BACKEND_DIR / "alembic"))
    config.set_main_option("sqlalchemy.url", cluster.migrator_url(database).replace("%", "%%"))
    command.downgrade(config, "0004")  # drops ingestion_jobs: its privileges vanish with it
    with cluster.admin_connection(database) as conn:
        gone = conn.execute("SELECT to_regclass('public.ingestion_jobs')").fetchone()
    assert gone == (None,)

    migrate(cluster.migrator_url(database), names=cluster.names)

    assert effective(cluster, database) == expected()


def test_a_table_without_a_decision_stays_owner_only(
    cluster: Cluster, scratch_database: Callable[[], str]
) -> None:
    database = migrated(cluster, scratch_database)
    with cluster.connect(cluster.migrator_url(database)) as conn:
        conn.execute("CREATE TABLE public.tst_new (x integer)")

    apply_grants(cluster.migrator_url(database), names=cluster.names)

    with cluster.admin_connection(database) as conn:
        for role in (cluster.names.app, cluster.names.worker, cluster.names.cli):
            row = conn.execute(
                "SELECT pg_catalog.has_table_privilege(%s, 'public.tst_new', 'SELECT')", (role,)
            ).fetchone()
            assert row == (False,)


def test_grants_are_atomic_for_a_concurrent_reader(
    cluster: Cluster, scratch_database: Callable[[], str]
) -> None:
    database = migrated(cluster, scratch_database)
    failures: list[str] = []
    stop = threading.Event()

    def reader() -> None:
        with cluster.connect(cluster.role_url("worker", database)) as conn:
            while not stop.is_set():
                try:
                    conn.execute("SELECT id FROM document_chunks LIMIT 1").fetchall()
                except psycopg.errors.InsufficientPrivilege as exc:
                    failures.append(str(exc)[:80])

    thread = threading.Thread(target=reader)
    thread.start()
    try:
        for _ in range(40):
            apply_grants(cluster.migrator_url(database), names=cluster.names)
    finally:
        stop.set()
        thread.join()

    assert failures == []


def test_a_direct_alembic_run_with_the_settings_url_is_refused(
    cluster: Cluster,
    scratch_database: Callable[[], str],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    database = migrated(cluster, scratch_database)
    monkeypatch.setenv("MIGRATION_DATABASE_URL", cluster.migrator_url(database))
    config = Config(str(BACKEND_DIR / "alembic.ini"))
    config.set_main_option("script_location", str(BACKEND_DIR / "alembic"))

    with pytest.raises(RuntimeError, match="db-migrate"):
        command.upgrade(config, "head")


@pytest.mark.parametrize("who", ["admin", "app"])
def test_the_grants_refuse_to_run_as_anyone_but_the_migrator(
    cluster: Cluster, scratch_database: Callable[[], str], who: str
) -> None:
    from app.db_admin.errors import DbAdminError

    database = migrated(cluster, scratch_database)
    url = cluster.admin(database) if who == "admin" else cluster.role_url("app", database)
    before = effective(cluster, database)

    with pytest.raises(DbAdminError, match="migrator"):
        apply_grants(url, names=cluster.names)

    assert effective(cluster, database) == before


def test_a_failure_in_the_grants_rolls_back_every_statement(
    cluster: Cluster, scratch_database: Callable[[], str]
) -> None:
    database = migrated(cluster, scratch_database)
    before = effective(cluster, database)
    broken = cluster.names.__class__(
        migrator=cluster.names.migrator,
        app=cluster.names.app,
        worker="tstrole_missing_role",  # does not exist: the statement for it fails mid-way
        cli=cluster.names.cli,
    )

    with pytest.raises(Exception, match="grant"):
        apply_grants(cluster.migrator_url(database), names=broken)

    assert effective(cluster, database) == before  # the revoke before the failure was undone
