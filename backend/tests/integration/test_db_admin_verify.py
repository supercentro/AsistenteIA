"""db-verify against a disposable cluster (change `database-least-privilege`, task 4.5)."""

from collections.abc import Callable

import pytest

from app.db_admin.bootstrap import bootstrap
from app.db_admin.migrate import migrate
from app.db_admin.verify import Finding, render_findings, verify
from tests.db_admin_support import Cluster, catalog_fingerprint
from tests.db_admin_support import cluster as cluster  # noqa: F401  (fixture)
from tests.db_admin_support import scratch_database as scratch_database  # noqa: F401  (fixture)


def healthy(cluster: Cluster, scratch_database: Callable[[], str]) -> str:
    database = scratch_database()
    bootstrap(cluster.admin("postgres"), cluster.passwords, database=database, names=cluster.names)
    migrate(cluster.migrator_url(database), names=cluster.names)
    return database


def run_verify(cluster: Cluster, database: str) -> list[Finding]:
    return verify(cluster.migrator_url(database), cluster.passwords, names=cluster.names)


def test_a_healthy_database_has_no_findings(
    cluster: Cluster, scratch_database: Callable[[], str]
) -> None:
    database = healthy(cluster, scratch_database)

    assert run_verify(cluster, database) == []


def test_verify_changes_nothing_and_can_run_twice(
    cluster: Cluster, scratch_database: Callable[[], str]
) -> None:
    database = healthy(cluster, scratch_database)
    before = catalog_fingerprint(cluster, database)
    with cluster.admin_connection(database) as conn:
        acl = conn.execute(
            "SELECT string_agg(relname || coalesce(relacl::text, ''), ',' ORDER BY relname) "
            "FROM pg_catalog.pg_class WHERE relnamespace = 'public'::regnamespace"
        ).fetchone()

    run_verify(cluster, database)
    run_verify(cluster, database)

    assert catalog_fingerprint(cluster, database) == before
    with cluster.admin_connection(database) as conn:
        assert (
            conn.execute(
                "SELECT string_agg(relname || coalesce(relacl::text, ''), ',' ORDER BY relname) "
                "FROM pg_catalog.pg_class WHERE relnamespace = 'public'::regnamespace"
            ).fetchone()
            == acl
        )


# (id, SQL run by the administrator in the application database, check expected in the findings)
DRIFTS = [
    ("extra-column-grant", "GRANT SELECT (locked_by) ON ingestion_jobs TO {app}", "privileges"),
    ("missing-grant", "REVOKE UPDATE ON documents FROM {worker}", "privileges"),
    ("extra-delete", "GRANT DELETE ON ingestion_jobs TO {app}", "privileges"),
    ("cli-gets-subjects", "GRANT SELECT ON subjects TO {cli}", "privileges"),
    ("superuser", "ALTER ROLE {app} SUPERUSER", "role-attributes"),
    ("bypassrls", "ALTER ROLE {worker} BYPASSRLS", "role-attributes"),
    ("connection-limit", "ALTER ROLE {app} CONNECTION LIMIT 500", "role-attributes"),
    ("membership", "GRANT pg_read_all_data TO {worker}", "memberships"),
    ("role-setting", "ALTER ROLE {cli} SET statement_timeout = '1s'", "role-settings"),
    ("search-path", "ALTER ROLE {app} SET search_path = public", "role-settings"),
    ("table-owner", "ALTER TABLE users OWNER TO {admin}", "ownership"),
    ("enum-owner", "ALTER TYPE user_role OWNER TO {admin}", "ownership"),
    ("changed-password", "ALTER ROLE {app} PASSWORD 'Another-0123456789-secret'", "login-probe"),
    ("public-connect", "GRANT CONNECT ON DATABASE postgres TO PUBLIC", "databases"),
    ("role-reaches-other-db", "GRANT CONNECT ON DATABASE postgres TO {app}", "databases"),
    ("template-open", "GRANT CONNECT ON DATABASE template1 TO PUBLIC", "databases"),
    ("schema-create", "GRANT CREATE ON SCHEMA public TO {app}", "schema"),
    ("schema-public", "GRANT USAGE ON SCHEMA public TO PUBLIC", "schema"),
    (
        "foreign-function",
        "CREATE FUNCTION public.tst_fn() RETURNS int LANGUAGE sql AS 'SELECT 1'",
        "foreign-objects",
    ),
    (
        "default-privileges",
        "ALTER DEFAULT PRIVILEGES FOR ROLE {migrator} GRANT EXECUTE ON FUNCTIONS TO PUBLIC",
        "default-privileges",
    ),
    (
        "default-privileges-to-a-role",
        "ALTER DEFAULT PRIVILEGES FOR ROLE {migrator} GRANT EXECUTE ON FUNCTIONS TO {app}",
        "default-privileges",
    ),
    (
        "sequence-grant",
        "CREATE SEQUENCE public.tst_seq; GRANT USAGE ON SEQUENCE public.tst_seq TO {app}",
        "sequences",
    ),
    ("table-without-decision", "CREATE TABLE public.tst_new (x integer)", "tables"),
    ("grant-option", "GRANT SELECT ON users TO {app} WITH GRANT OPTION", "privileges"),
    (
        "stranger-in-the-acl",
        "CREATE ROLE tstrole_stranger; GRANT SELECT ON users TO tstrole_stranger",
        "privileges",
    ),
    ("database-temporary", "GRANT TEMPORARY ON DATABASE {database} TO {app}", "databases"),
    (
        "database-role-setting",
        "ALTER ROLE {app} IN DATABASE postgres SET statement_timeout = '1s'",
        "role-settings",
    ),
    ("row-level-security", "ALTER TABLE users ENABLE ROW LEVEL SECURITY", "row-level-security"),
    ("composite-type", "CREATE TYPE public.tst_type AS (a integer)", "foreign-objects"),
    (
        "member-of-a-working-role",
        "CREATE ROLE tstrole_child; GRANT {app} TO tstrole_child",
        "memberships",
    ),
    ("other-schema", "CREATE SCHEMA tst_other; CREATE TABLE tst_other.t (x integer)", "schema"),
]


@pytest.mark.parametrize(("name", "sql", "check"), DRIFTS, ids=[d[0] for d in DRIFTS])
def test_each_drift_is_reported_with_the_check_that_found_it(
    cluster: Cluster,
    scratch_database: Callable[[], str],
    name: str,
    sql: str,
    check: str,
) -> None:
    from sqlalchemy.engine import make_url

    from tests.db_admin_support import owners  # noqa: F401

    database = healthy(cluster, scratch_database)
    values = {
        "app": f'"{cluster.names.app}"',
        "worker": f'"{cluster.names.worker}"',
        "cli": f'"{cluster.names.cli}"',
        "migrator": f'"{cluster.names.migrator}"',
        "admin": f'"{make_url(cluster.admin_url).username}"',
        "database": f'"{database}"',
    }
    with cluster.admin_connection(database) as conn:
        for statement in sql.format(**values).split("; "):
            conn.execute(statement)

    findings = run_verify(cluster, database)

    assert findings, name
    assert check in {f.check for f in findings}, (name, [f.check for f in findings])


def test_findings_never_contain_a_secret(
    cluster: Cluster, scratch_database: Callable[[], str]
) -> None:
    database = healthy(cluster, scratch_database)
    with cluster.admin_connection(database) as conn:
        conn.execute(f"ALTER ROLE \"{cluster.names.app}\" PASSWORD 'Another-0123456789-secret'")
        conn.execute(f'GRANT SELECT (locked_by) ON ingestion_jobs TO "{cluster.names.app}"')

    findings = run_verify(cluster, database)
    text = render_findings(findings)

    assert text and findings
    for secret in (
        "Another-0123456789-secret",
        cluster.passwords.app,
        cluster.passwords.migrator,
        cluster.passwords.worker,
        cluster.passwords.cli,
        "SCRAM-SHA-256",
    ):
        assert secret not in text


def test_a_wrong_migrator_password_fails_without_echoing_it(
    cluster: Cluster, scratch_database: Callable[[], str]
) -> None:
    from app.db_admin.errors import DbAdminError

    database = healthy(cluster, scratch_database)
    url = cluster.url(cluster.names.migrator, "Wrong-0123456789-passwd", database)

    with pytest.raises(DbAdminError) as caught:
        verify(url, cluster.passwords, names=cluster.names)

    assert "Wrong-0123456789-passwd" not in str(caught.value)
