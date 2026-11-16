"""db-bootstrap against a disposable cluster (change `database-least-privilege`, tasks 4.1-4.2)."""

import io
import logging
from collections.abc import Callable
from contextlib import redirect_stderr, redirect_stdout

import psycopg
import pytest

from app.db_admin.bootstrap import BootstrapReport, bootstrap
from app.db_admin.errors import DbAdminError
from app.db_admin.names import CONNECTION_LIMITS, EXPECTED_SEARCH_PATH, SEARCH_PATHS
from tests.db_admin_support import Cluster
from tests.db_admin_support import cluster as cluster  # noqa: F401  (fixture)
from tests.db_admin_support import scratch_database as scratch_database  # noqa: F401  (fixture)

ATTRIBUTES = (
    "rolsuper",
    "rolcreatedb",
    "rolcreaterole",
    "rolreplication",
    "rolbypassrls",
)


def run_bootstrap(cluster: Cluster, database: str) -> BootstrapReport:
    return bootstrap(
        cluster.admin("postgres"), cluster.passwords, database=database, names=cluster.names
    )


def state(cluster: Cluster, database: str) -> str:
    """Everything the bootstrap sets except passwords (which are salted and differ each run)."""
    names = list(cluster.names.all())
    with cluster.admin_connection(database) as conn:
        roles = conn.execute(
            "SELECT rolname, rolcanlogin, rolsuper, rolcreatedb, rolcreaterole, rolreplication, "
            "rolbypassrls, rolinherit, rolconnlimit, rolconfig FROM pg_catalog.pg_roles "
            "WHERE rolname = ANY(%s) ORDER BY rolname",
            (names,),
        ).fetchall()
        members = conn.execute(
            "SELECT count(*) FROM pg_catalog.pg_auth_members m JOIN pg_catalog.pg_roles r "
            "ON r.oid = m.member WHERE r.rolname = ANY(%s)",
            (names,),
        ).fetchall()
        databases = conn.execute(
            "SELECT datname, datacl::text FROM pg_catalog.pg_database ORDER BY datname"
        ).fetchall()
    with cluster.admin_connection(database) as conn:
        schema = conn.execute(
            "SELECT nspacl::text FROM pg_catalog.pg_namespace WHERE nspname = 'public'"
        ).fetchall()
        defaults = conn.execute(
            "SELECT defaclrole::regrole::text, defaclobjtype, defaclacl::text "
            "FROM pg_catalog.pg_default_acl ORDER BY 1, 2"
        ).fetchall()
        extension = conn.execute(
            "SELECT extname, extnamespace::regnamespace::text FROM pg_catalog.pg_extension "
            "WHERE extname = 'vector'"
        ).fetchall()
    return repr((roles, members, databases, schema, defaults, extension))


def test_roles_are_created_with_minimal_attributes_and_limits(
    cluster: Cluster, scratch_database: Callable[[], str]
) -> None:
    database = scratch_database()

    report = run_bootstrap(cluster, database)

    assert sorted(report.created) == sorted(cluster.names.all())
    with cluster.admin_connection() as conn:
        for logical, limit in CONNECTION_LIMITS.items():
            name = getattr(cluster.names, logical)
            row = conn.execute(
                "SELECT rolcanlogin, rolinherit, rolconnlimit, rolconfig, "
                + ", ".join(ATTRIBUTES)
                + " FROM pg_catalog.pg_roles WHERE rolname = %s",
                (name,),
            ).fetchone()
            assert row is not None
            assert row[0] is True and row[2] == limit
            assert row[3] == [f"search_path={SEARCH_PATHS[logical]}"]
            assert not any(row[4:]), name
        memberships = conn.execute(
            "SELECT count(*) FROM pg_catalog.pg_auth_members m JOIN pg_catalog.pg_roles r "
            "ON r.oid = m.member WHERE r.rolname = ANY(%s)",
            (list(cluster.names.all()),),
        ).fetchone()
        assert memberships == (0,)


def test_passwords_are_stored_as_scram_verifiers_and_work(
    cluster: Cluster, scratch_database: Callable[[], str]
) -> None:
    database = scratch_database()
    run_bootstrap(cluster, database)

    with cluster.admin_connection() as conn:
        for name in cluster.names.all():
            stored = conn.execute(
                "SELECT rolpassword FROM pg_catalog.pg_authid WHERE rolname = %s", (name,)
            ).fetchone()
            assert stored is not None and str(stored[0]).startswith("SCRAM-SHA-256$4096:")
    for logical in ("migrator", "app", "worker", "cli"):
        with cluster.connect(cluster.role_url(logical, database)) as conn:
            assert conn.execute("SELECT current_user").fetchone() == (
                getattr(cluster.names, logical),
            )


def test_it_is_idempotent_and_rotates_a_changed_password(
    cluster: Cluster, scratch_database: Callable[[], str]
) -> None:
    database = scratch_database()
    run_bootstrap(cluster, database)
    first = state(cluster, database)

    second_report = run_bootstrap(cluster, database)

    assert state(cluster, database) == first
    assert second_report.created == () and sorted(second_report.updated) == sorted(
        cluster.names.all()
    )

    old = cluster.passwords
    cluster.passwords = type(old)(
        migrator=old.migrator, app="New-0123456789-abcdefghij", worker=old.worker, cli=old.cli
    )
    try:
        run_bootstrap(cluster, database)
        with pytest.raises(psycopg.OperationalError):
            cluster.connect(cluster.url(cluster.names.app, old.app, database))
        with cluster.connect(cluster.role_url("app", database)) as conn:
            assert conn.execute("SELECT 1").fetchone() == (1,)
    finally:
        cluster.passwords = old
        run_bootstrap(cluster, database)


def test_persistent_role_settings_and_memberships_are_healed(
    cluster: Cluster, scratch_database: Callable[[], str]
) -> None:
    database = scratch_database()
    run_bootstrap(cluster, database)
    app = cluster.names.app
    with cluster.admin_connection() as conn:
        conn.execute(f"ALTER ROLE \"{app}\" SET statement_timeout = '1ms'")
        conn.execute(f'ALTER ROLE "{app}" SET search_path = public')
        conn.execute(f'GRANT pg_read_all_data TO "{app}"')
        conn.execute(f'ALTER ROLE "{app}" SUPERUSER BYPASSRLS CREATEROLE')

    run_bootstrap(cluster, database)

    with cluster.admin_connection() as conn:
        row = conn.execute(
            "SELECT rolconfig, rolsuper, rolbypassrls, rolcreaterole FROM pg_catalog.pg_roles "
            "WHERE rolname = %s",
            (app,),
        ).fetchone()
        assert row == ([f"search_path={EXPECTED_SEARCH_PATH}"], False, False, False)
        member = conn.execute(
            "SELECT count(*) FROM pg_catalog.pg_auth_members m JOIN pg_catalog.pg_roles r "
            "ON r.oid = m.member WHERE r.rolname = %s",
            (app,),
        ).fetchone()
        assert member == (0,)


def test_settings_a_role_gave_itself_for_one_database_are_healed(
    cluster: Cluster, scratch_database: Callable[[], str]
) -> None:
    database = scratch_database()
    run_bootstrap(cluster, database)
    app = cluster.names.app
    with cluster.admin_connection() as conn:
        conn.execute(f"ALTER ROLE \"{app}\" IN DATABASE postgres SET statement_timeout = '1ms'")
        conn.execute(f'ALTER ROLE "{app}" IN DATABASE "{database}" SET search_path = public')

    run_bootstrap(cluster, database)

    with cluster.admin_connection() as conn:
        left = conn.execute(
            "SELECT count(*) FROM pg_catalog.pg_db_role_setting s "
            "JOIN pg_catalog.pg_roles r ON r.oid = s.setrole WHERE r.rolname = %s "
            "AND s.setdatabase <> 0",
            (app,),
        ).fetchone()
    assert left == (0,)


def test_roles_that_are_members_of_a_working_role_are_revoked(
    cluster: Cluster, scratch_database: Callable[[], str]
) -> None:
    database = scratch_database()
    run_bootstrap(cluster, database)
    with cluster.admin_connection() as conn:
        conn.execute("CREATE ROLE tstrole_child")
        conn.execute(f'GRANT "{cluster.names.app}" TO tstrole_child')

    run_bootstrap(cluster, database)

    with cluster.admin_connection() as conn:
        left = conn.execute(
            "SELECT count(*) FROM pg_catalog.pg_auth_members m JOIN pg_catalog.pg_roles r "
            "ON r.oid = m.member WHERE r.rolname = 'tstrole_child'"
        ).fetchone()
    assert left == (0,)


def test_public_is_closed_on_every_database_including_the_templates(
    cluster: Cluster, scratch_database: Callable[[], str]
) -> None:
    database = scratch_database()
    other = scratch_database()  # a database that will not be the application one

    report = run_bootstrap(cluster, database)

    assert report.closed_databases >= 4
    with cluster.admin_connection() as conn:
        rows = conn.execute(
            "SELECT d.datname, a.privilege_type FROM pg_catalog.pg_database d, "
            "LATERAL pg_catalog.aclexplode(d.datacl) a WHERE a.grantee = 0"
        ).fetchall()
        assert rows == [], rows  # no database grants anything to PUBLIC
        for name in ("postgres", "template1", other):
            for role in cluster.names.all():
                row = conn.execute(
                    "SELECT pg_catalog.has_database_privilege(%s, %s, 'CONNECT')", (role, name)
                ).fetchone()
                assert row == (False,), (role, name)
        for role in cluster.names.all():
            row = conn.execute(
                "SELECT pg_catalog.has_database_privilege(%s, %s, 'CONNECT')", (role, database)
            ).fetchone()
            assert row == (True,)


def test_schema_public_extension_and_default_privileges(
    cluster: Cluster, scratch_database: Callable[[], str]
) -> None:
    database = scratch_database()
    run_bootstrap(cluster, database)

    with cluster.admin_connection(database) as conn:
        public_grants = conn.execute(
            "SELECT a.privilege_type FROM pg_catalog.pg_namespace n, "
            "LATERAL pg_catalog.aclexplode(n.nspacl) a WHERE n.nspname = 'public' "
            "AND a.grantee = 0"
        ).fetchall()
        assert public_grants == []
        for role in (cluster.names.app, cluster.names.worker, cluster.names.cli):
            usage = conn.execute(
                "SELECT pg_catalog.has_schema_privilege(%s, 'public', 'USAGE'), "
                "pg_catalog.has_schema_privilege(%s, 'public', 'CREATE')",
                (role, role),
            ).fetchone()
            assert usage == (True, False), role
        creator = conn.execute(
            "SELECT pg_catalog.has_schema_privilege(%s, 'public', 'CREATE')",
            (cluster.names.migrator,),
        ).fetchone()
        assert creator == (True,)
        extension = conn.execute(
            "SELECT extnamespace::regnamespace::text FROM pg_catalog.pg_extension "
            "WHERE extname = 'vector'"
        ).fetchone()
        assert extension == ("public",)

    with cluster.connect(cluster.migrator_url(database)) as conn:
        conn.execute("CREATE FUNCTION public.tst_probe() RETURNS int LANGUAGE sql AS 'SELECT 1'")
        executable = conn.execute(
            "SELECT pg_catalog.has_function_privilege('tstrole_app', "
            "'public.tst_probe()'::regprocedure, 'EXECUTE')"
        ).fetchone()
        assert executable == (False,)  # PUBLIC no longer executes what the migrator creates


def test_a_function_planted_in_public_does_not_change_what_the_bootstrap_does(
    cluster: Cluster, scratch_database: Callable[[], str]
) -> None:
    database = scratch_database()
    run_bootstrap(cluster, database)
    with cluster.admin_connection(database) as conn:
        conn.execute(
            "CREATE FUNCTION public.lower(character varying) RETURNS character varying "
            "LANGUAGE plpgsql AS $$ BEGIN RAISE EXCEPTION 'planted function called'; END $$"
        )
        conn.execute(
            "CREATE FUNCTION public.varchar_eq(character varying, character varying) "
            "RETURNS boolean LANGUAGE plpgsql AS $$ BEGIN RAISE EXCEPTION 'planted operator'; "
            "END $$"
        )
        conn.execute(
            "CREATE OPERATOR public.= (LEFTARG = character varying, RIGHTARG = character varying, "
            "FUNCTION = public.varchar_eq)"
        )

    run_bootstrap(cluster, database)  # must not call the planted function or operator

    assert state(cluster, database)


def test_the_bootstrap_only_reports_ownership_drift(
    cluster: Cluster, scratch_database: Callable[[], str]
) -> None:
    from tests.db_admin_support import build_legacy_database, owners

    database = scratch_database()
    build_legacy_database(cluster, database)
    before = owners(cluster, database)

    report = run_bootstrap(cluster, database)

    assert owners(cluster, database) == before  # nothing was re-owned
    assert report.ownership_drift
    assert all(cluster.names.migrator not in line for line in report.ownership_drift)


def test_no_secret_reaches_the_output_the_logs_or_an_error(
    cluster: Cluster,
    scratch_database: Callable[[], str],
    caplog: pytest.LogCaptureFixture,
) -> None:
    database = scratch_database()
    out, err = io.StringIO(), io.StringIO()
    caplog.set_level(logging.DEBUG)

    with redirect_stdout(out), redirect_stderr(err):
        report = run_bootstrap(cluster, database)
        for line in report.summary():
            print(line)
        wrong = type(cluster.passwords)(
            migrator="x" * 20, app="y" * 20, worker="z" * 20, cli="w" * 20
        )
        bad_url = cluster.admin("postgres").replace(
            make_password(cluster), "Wrong-0123456789-passwd"
        )
        with pytest.raises(DbAdminError) as caught:
            bootstrap(bad_url, wrong, database=database, names=cluster.names)

    everything = out.getvalue() + err.getvalue() + caplog.text + str(caught.value)
    secrets_used = [
        *(getattr(cluster.passwords, r) for r in ("migrator", "app", "worker", "cli")),
        make_password(cluster),
        "Wrong-0123456789-passwd",
        "SCRAM-SHA-256",
    ]
    for secret in secrets_used:
        assert secret not in everything


def make_password(cluster: Cluster) -> str:
    from sqlalchemy.engine import make_url

    password = make_url(cluster.admin_url).password
    assert password
    return password


def test_a_bad_database_name_is_refused_before_any_connection(cluster: Cluster) -> None:
    from app.db_admin.sql import UnsafeIdentifierError

    with pytest.raises(UnsafeIdentifierError):
        bootstrap(
            "postgresql+psycopg://u:p@127.0.0.1:1/postgres",  # nothing listens: not reached
            cluster.passwords,
            database='x"; DROP DATABASE postgres; --',
            names=cluster.names,
        )
