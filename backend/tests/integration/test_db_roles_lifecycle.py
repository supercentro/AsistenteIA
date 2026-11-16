"""Connection limits, migration round trips and self-tampering (change `database-least-privilege`).

Tasks 5.1 (limits at the limit), 5.6 (downgrade and upgrade round trip, `downgrade base` is an
administrator operation) and 5.10 (a role changes its own password and settings; the next bootstrap
undoes it and `db-verify` sees it). All of it on a disposable cluster.
"""

from typing import Any

import psycopg
import pytest
from sqlalchemy import create_engine

from app.core.database import create_db_engine
from app.db_admin.bootstrap import bootstrap
from app.db_admin.migrate import downgrade, migrate
from app.db_admin.names import CONNECTION_LIMITS
from app.db_admin.verify import verify
from tests.db_admin_support import Cluster
from tests.db_admin_support import cluster as cluster  # noqa: F401  (fixture)
from tests.db_admin_support import scratch_database as scratch_database  # noqa: F401  (fixture)
from tests.db_roles_support import (
    as_role,
)
from tests.db_roles_support import (
    own_database as own_database,
)

LOGICAL = ["migrator", "app", "worker", "cli"]


def findings(cluster: Cluster, database: str) -> list[Any]:
    return verify(cluster.migrator_url(database), cluster.passwords, names=cluster.names)


# --- 5.1 connection limits ---------------------------------------------------------------


def test_the_application_limit_covers_the_real_pool_of_the_api_engine() -> None:
    engine = create_db_engine("postgresql+psycopg://u:p@localhost/db")
    pool_size, overflow = engine.pool.size(), engine.pool._max_overflow  # type: ignore[attr-defined]  # noqa: SLF001

    assert (
        CONNECTION_LIMITS["app"] >= pool_size + overflow + 3
    )  # the pool plus maintenance sessions
    assert CONNECTION_LIMITS["worker"] >= 4  # job session, heartbeat, sweep and the health probe
    assert CONNECTION_LIMITS["cli"] >= 1 and CONNECTION_LIMITS["migrator"] >= 2
    engine.dispose()


@pytest.mark.parametrize("logical", LOGICAL)
def test_a_role_is_refused_beyond_its_limit_and_recovers_when_a_session_is_released(
    cluster: Cluster, own_database: str, logical: str
) -> None:
    limit = CONNECTION_LIMITS[logical]
    opened: list[psycopg.Connection[Any]] = []
    try:
        for _ in range(limit):
            opened.append(as_role(cluster, logical, own_database))
        with pytest.raises(psycopg.OperationalError) as caught:
            as_role(cluster, logical, own_database)
        assert "too many connections for role" in str(caught.value)

        # Exhaustion does not hurt the sessions that already exist.
        assert all(c.execute("SELECT 1").fetchone() == (1,) for c in opened)
        # Other roles are not affected by this role being at its limit.
        other = next(r for r in LOGICAL if r != logical)
        with as_role(cluster, other, own_database) as conn:
            assert conn.execute("SELECT 1").fetchone() == (1,)

        opened.pop().close()  # release one session
        with as_role(cluster, logical, own_database) as conn:
            assert conn.execute("SELECT 1").fetchone() == (1,)
    finally:
        for conn in opened:
            conn.close()


def test_an_exhausted_pool_of_the_api_waits_instead_of_opening_more_than_the_limit(
    cluster: Cluster, own_database: str
) -> None:
    # The real engine of the API, at its real size, stays inside the role limit.
    engine = create_engine(
        cluster.role_url("app", own_database),
        pool_size=5,
        max_overflow=10,
        pool_timeout=2,
    )
    held: list[Any] = [engine.raw_connection() for _ in range(15)]
    try:
        with pytest.raises(Exception, match="timeout|QueuePool"):
            engine.raw_connection()  # the sixteenth request waits and times out: no 16th session
        with cluster.admin_connection() as conn:
            sessions = conn.execute(
                "SELECT count(*) FROM pg_catalog.pg_stat_activity WHERE usename = %s",
                (cluster.names.app,),
            ).fetchone()
        assert sessions is not None and sessions[0] <= CONNECTION_LIMITS["app"]
    finally:
        for conn in held:
            conn.close()
        engine.dispose()


# --- 5.6 migrations ----------------------------------------------------------------------


def test_a_downgrade_and_upgrade_round_trip_leaves_the_database_verified(
    cluster: Cluster, own_database: str
) -> None:
    assert findings(cluster, own_database) == []

    downgrade(cluster.migrator_url(own_database), "0004", names=cluster.names)
    migrate(cluster.migrator_url(own_database), names=cluster.names)

    assert findings(cluster, own_database) == []


def test_downgrade_to_base_is_an_administrator_operation_and_changes_nothing_for_the_migrator(
    cluster: Cluster, own_database: str
) -> None:
    with pytest.raises(Exception) as caught:
        downgrade(cluster.migrator_url(own_database), "base", names=cluster.names)
    assert (
        "42501" in repr(getattr(caught.value, "orig", caught.value))
        or "permission" in str(caught.value).lower()
        or "owner" in str(caught.value).lower()
    )

    with cluster.admin_connection(own_database) as conn:
        head = conn.execute("SELECT version_num FROM alembic_version").fetchone()
        users = conn.execute("SELECT count(*) FROM users").fetchone()
    assert head == ("0006",) and users == (2,)  # the failed downgrade was rolled back entirely


# --- 5.10 self-tampering ---------------------------------------------------------------


def test_a_role_that_changes_its_own_settings_is_detected_and_healed(
    cluster: Cluster, own_database: str
) -> None:
    with as_role(cluster, "app", own_database) as conn:
        conn.execute(f"ALTER ROLE \"{cluster.names.app}\" SET statement_timeout = '5ms'")  # allowed
        conn.execute(f'ALTER ROLE "{cluster.names.app}" SET search_path = public')

    assert {f.check for f in findings(cluster, own_database)} >= {"role-settings"}

    bootstrap(
        cluster.admin("postgres"), cluster.passwords, database=own_database, names=cluster.names
    )
    assert findings(cluster, own_database) == []


def test_a_role_that_changes_its_own_password_is_detected_and_healed(
    cluster: Cluster, own_database: str
) -> None:
    with as_role(cluster, "worker", own_database) as conn:
        conn.execute(f"ALTER ROLE \"{cluster.names.worker}\" PASSWORD 'Another-0123456789-secret'")

    detected = findings(cluster, own_database)
    assert any(f.check == "login-probe" and cluster.names.worker in f.detail for f in detected)
    assert "Another-0123456789-secret" not in "".join(f.detail for f in detected)

    bootstrap(
        cluster.admin("postgres"), cluster.passwords, database=own_database, names=cluster.names
    )
    assert findings(cluster, own_database) == []
    with as_role(cluster, "worker", own_database) as conn:  # the configured password works again
        assert conn.execute("SELECT 1").fetchone() == (1,)


def test_lock_table_is_possible_only_where_the_role_may_delete_a_documented_residual(
    cluster: Cluster, own_database: str
) -> None:
    with cluster.connect(cluster.role_url("app", own_database), autocommit=False) as conn:
        conn.execute("LOCK TABLE public.subjects IN ACCESS EXCLUSIVE MODE")  # DELETE is granted
        conn.rollback()
        with pytest.raises(psycopg.errors.InsufficientPrivilege):
            conn.execute("LOCK TABLE public.alembic_version IN ACCESS EXCLUSIVE MODE")
        conn.rollback()
        with pytest.raises(psycopg.errors.InsufficientPrivilege):
            conn.execute("LOCK TABLE public.ingestion_jobs IN ACCESS EXCLUSIVE MODE")
        conn.rollback()
    with cluster.connect(cluster.role_url("worker", own_database), autocommit=False) as conn:
        with pytest.raises(psycopg.errors.InsufficientPrivilege):
            conn.execute("LOCK TABLE public.users IN ACCESS EXCLUSIVE MODE")
        conn.rollback()
