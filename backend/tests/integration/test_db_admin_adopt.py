"""db-adopt and its rollback against a disposable cluster (change `database-least-privilege`, 4.3).

These tests reproduce the evidence that the spike observed but did not keep: adoption of a
database with data, ownership recovery and rollback.
"""

from collections.abc import Callable

import pytest

from app.db_admin.adopt import AdoptRefusedError, adopt, remove_roles, rollback_adoption
from app.db_admin.bootstrap import bootstrap
from tests.db_admin_support import (
    Cluster,
    build_legacy_database,
    catalog_fingerprint,
    owners,
    row_counts,
)
from tests.db_admin_support import cluster as cluster  # noqa: F401  (fixture)
from tests.db_admin_support import scratch_database as scratch_database  # noqa: F401  (fixture)


def prepare(cluster: Cluster, scratch_database: Callable[[], str]) -> tuple[str, dict[str, int]]:
    database = scratch_database()
    counts = build_legacy_database(cluster, database)
    bootstrap(cluster.admin("postgres"), cluster.passwords, database=database, names=cluster.names)
    return database, counts


def run_adopt(cluster: Cluster, database: str, *, apply: bool) -> object:
    return adopt(cluster.admin("postgres"), database=database, names=cluster.names, apply=apply)


def test_a_dry_run_changes_nothing_and_lists_the_plan(
    cluster: Cluster, scratch_database: Callable[[], str]
) -> None:
    database, counts = prepare(cluster, scratch_database)
    before = (owners(cluster, database), catalog_fingerprint(cluster, database))

    report = run_adopt(cluster, database, apply=False)

    assert (owners(cluster, database), catalog_fingerprint(cluster, database)) == before
    assert row_counts(cluster, database) == counts
    assert report.applied is False and report.planned  # type: ignore[attr-defined]


def test_adoption_moves_every_object_keeps_rows_and_catalog(
    cluster: Cluster, scratch_database: Callable[[], str]
) -> None:
    database, counts = prepare(cluster, scratch_database)
    fingerprint = catalog_fingerprint(cluster, database)
    before = owners(cluster, database)
    assert set(before.values()) == {make_admin_name(cluster)}

    report = run_adopt(cluster, database, apply=True)

    after = owners(cluster, database)
    assert set(after) == set(before)
    assert set(after.values()) == {cluster.names.migrator}  # tables, indexes, enums, bookkeeping
    assert {"users", "alembic_version", "document_status", "user_role"} <= set(after)
    assert row_counts(cluster, database) == counts
    assert catalog_fingerprint(cluster, database) == fingerprint
    assert report.applied is True  # type: ignore[attr-defined]
    with cluster.admin_connection(database) as conn:
        extension = conn.execute(
            "SELECT r.rolname FROM pg_catalog.pg_extension e JOIN pg_catalog.pg_roles r "
            "ON r.oid = e.extowner WHERE e.extname = 'vector'"
        ).fetchone()
        db_owner = conn.execute(
            "SELECT r.rolname FROM pg_catalog.pg_database d JOIN pg_catalog.pg_roles r "
            "ON r.oid = d.datdba WHERE d.datname = current_database()"
        ).fetchone()
    assert extension == (make_admin_name(cluster),)  # the extension and the database stay
    assert db_owner == (make_admin_name(cluster),)


def test_adoption_is_idempotent(cluster: Cluster, scratch_database: Callable[[], str]) -> None:
    database, counts = prepare(cluster, scratch_database)
    run_adopt(cluster, database, apply=True)

    second = run_adopt(cluster, database, apply=True)

    assert second.planned == ()  # type: ignore[attr-defined]
    assert row_counts(cluster, database) == counts


def test_the_migrator_can_migrate_after_adopting(
    cluster: Cluster, scratch_database: Callable[[], str]
) -> None:
    database, _ = prepare(cluster, scratch_database)
    run_adopt(cluster, database, apply=True)

    with cluster.connect(cluster.migrator_url(database)) as conn:
        conn.execute("ALTER TABLE users ADD COLUMN tst_extra integer")
        conn.execute("ALTER TABLE users DROP COLUMN tst_extra")


@pytest.mark.parametrize("role", ["app", "worker", "cli"])
def test_adoption_is_refused_while_a_runtime_session_exists_and_nothing_changes(
    cluster: Cluster, scratch_database: Callable[[], str], role: str
) -> None:
    database, counts = prepare(cluster, scratch_database)
    before = owners(cluster, database)

    with (
        cluster.connect(cluster.role_url(role, database)),
        pytest.raises(AdoptRefusedError, match="session"),
    ):
        run_adopt(cluster, database, apply=True)

    assert owners(cluster, database) == before
    assert row_counts(cluster, database) == counts


@pytest.mark.parametrize(
    "unexpected",
    [
        "CREATE VIEW public.tst_view AS SELECT 1 AS x",
        "CREATE FUNCTION public.tst_fn() RETURNS int LANGUAGE sql AS 'SELECT 1'",
        "CREATE SCHEMA tst_other; CREATE TABLE tst_other.t (x int)",
        "CREATE TABLE public.tst_stranger (x int)",
        "CREATE SEQUENCE public.tst_seq",
        "CREATE TYPE public.tst_type AS (a int)",
    ],
    ids=["view", "function", "other-schema", "stranger-table", "sequence", "composite-type"],
)
def test_adoption_refuses_unexpected_objects_and_changes_nothing(
    cluster: Cluster, scratch_database: Callable[[], str], unexpected: str
) -> None:
    database, counts = prepare(cluster, scratch_database)
    with cluster.admin_connection(database) as conn:
        for statement in unexpected.split("; "):
            conn.execute(statement)
    before = owners(cluster, database)

    with pytest.raises(AdoptRefusedError):
        run_adopt(cluster, database, apply=True)

    assert owners(cluster, database) == before
    assert row_counts(cluster, database) == counts


def test_adoption_is_atomic_when_a_statement_fails(
    cluster: Cluster, scratch_database: Callable[[], str]
) -> None:
    database, counts = prepare(cluster, scratch_database)
    before = owners(cluster, database)
    # A SHARE lock on `users` does not block the row counts but blocks `ALTER TABLE users OWNER`,
    # which is the last table alphabetically: the earlier tables have already been moved when the
    # lock timeout hits, so only the rollback can leave every owner unchanged.
    with cluster.connect(
        cluster.admin(database), autocommit=False, application_name="tst-lock-holder"
    ) as holder:
        holder.execute("LOCK TABLE users IN SHARE MODE")
        with pytest.raises(AdoptRefusedError, match="lock"):
            adopt(
                cluster.admin("postgres"),
                database=database,
                names=cluster.names,
                apply=True,
                lock_timeout_ms=300,
                ignore_application_names=("tst-lock-holder",),
            )
        holder.rollback()

    assert owners(cluster, database) == before  # not one table moved
    assert row_counts(cluster, database) == counts


def test_adoption_is_refused_while_the_administrator_still_serves_the_database(
    cluster: Cluster, scratch_database: Callable[[], str]
) -> None:
    # Before adoption the API and the worker connect as the administrator: that is who must be gone.
    database, counts = prepare(cluster, scratch_database)
    before = owners(cluster, database)

    with (
        cluster.connect(cluster.admin(database), application_name="tst-api-standin"),
        pytest.raises(AdoptRefusedError, match="session") as caught,
    ):
        run_adopt(cluster, database, apply=True)

    assert "tst-api-standin" in str(caught.value)
    assert owners(cluster, database) == before and row_counts(cluster, database) == counts


def test_rollback_returns_ownership_keeps_rows_and_never_drops_owned_first(
    cluster: Cluster, scratch_database: Callable[[], str]
) -> None:
    database, counts = prepare(cluster, scratch_database)
    fingerprint = catalog_fingerprint(cluster, database)
    run_adopt(cluster, database, apply=True)

    report = rollback_adoption(
        cluster.admin("postgres"), database=database, names=cluster.names, remove_roles=False
    )

    assert set(owners(cluster, database).values()) == {make_admin_name(cluster)}
    assert row_counts(cluster, database) == counts
    assert catalog_fingerprint(cluster, database) == fingerprint
    assert report.owners_verified is True
    assert not any("DROP OWNED" in s for s in report.statements[: report.first_removal_index])


def test_removing_the_roles_is_refused_while_they_own_objects(
    cluster: Cluster, scratch_database: Callable[[], str]
) -> None:
    database, counts = prepare(cluster, scratch_database)
    run_adopt(cluster, database, apply=True)

    with pytest.raises(AdoptRefusedError, match="owns"):
        remove_roles(cluster.admin("postgres"), names=cluster.names)

    assert row_counts(cluster, database) == counts  # the tables survived (no DROP OWNED)
    assert set(owners(cluster, database).values()) == {cluster.names.migrator}


def test_rollback_then_removing_the_roles_leaves_the_database_with_the_administrator(
    cluster: Cluster, scratch_database: Callable[[], str]
) -> None:
    database, counts = prepare(cluster, scratch_database)
    run_adopt(cluster, database, apply=True)

    rollback_adoption(
        cluster.admin("postgres"), database=database, names=cluster.names, remove_roles=True
    )

    with cluster.admin_connection() as conn:
        left = conn.execute(
            "SELECT count(*) FROM pg_catalog.pg_roles WHERE rolname = ANY(%s)",
            (list(cluster.names.all()),),
        ).fetchone()
    assert left == (0,)
    assert row_counts(cluster, database) == counts
    assert set(owners(cluster, database).values()) == {make_admin_name(cluster)}
    # A new bootstrap and adoption start from scratch again.
    bootstrap(cluster.admin("postgres"), cluster.passwords, database=database, names=cluster.names)
    run_adopt(cluster, database, apply=True)
    assert row_counts(cluster, database) == counts


def make_admin_name(cluster: Cluster) -> str:
    from sqlalchemy.engine import make_url

    name = make_url(cluster.admin_url).username
    assert name
    return name
