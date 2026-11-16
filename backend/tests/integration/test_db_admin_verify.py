"""db-verify against a disposable cluster (change `database-least-privilege`, task 4.5)."""

import re
import secrets
from collections.abc import Callable, Iterator
from contextlib import contextmanager

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


# --- Finding P2 of the Codex review of PR #12 (task 19.3.2): column ACLs of strangers ---


@contextmanager
def outsider_role(cluster: Cluster, database: str) -> Iterator[str]:
    """A login-less role outside the four managed identities, dropped with its privileges.

    The name carries the sweep prefix `tstrole_` (so the fixture removes it even if the process
    dies half way) and a random suffix (so two runs never collide on the name).
    """
    role = f"tstrole_out_{secrets.token_hex(4)}"
    with cluster.admin_connection(database) as conn:
        conn.execute(f"CREATE ROLE {role} NOLOGIN")
    try:
        yield role
    finally:
        with cluster.admin_connection(database) as conn:
            conn.execute(f"DROP OWNED BY {role}")
            conn.execute(f"DROP ROLE {role}")


def forget_database_grants_of_earlier_drifts(cluster: Cluster) -> None:
    """Undo what the drift cases above leave on the shared cluster (`CONNECT` on `postgres`).

    The bootstrap closes `PUBLIC` again but not an explicit grant to a managed role, so a case
    that asserts "no findings" after those drifts must start from a clean cluster.
    """
    roles = ", ".join(f'"{role}"' for role in cluster.names.all())
    with cluster.admin_connection("postgres") as conn:
        conn.execute(f"REVOKE ALL ON DATABASE postgres FROM {roles}")


def names_column(finding: Finding, grantee: str, table: str, column: str) -> bool:
    """True only for the finding of exactly this grantee, table and column.

    A finding has no structured fields, only `check` and `detail`, so the whole detail must match
    (no substring): `users.password_hash` does not match `users.password_hash_old` nor another role.
    """
    pattern = (
        rf"{re.escape(grantee)}, outside the four roles, has privileges on column "
        rf"{re.escape(table)}\.{re.escape(column)}"
    )
    return finding.check == "privileges" and re.fullmatch(pattern, finding.detail) is not None


def test_a_column_grant_to_a_role_outside_the_four_is_reported(
    cluster: Cluster, scratch_database: Callable[[], str]
) -> None:
    database = healthy(cluster, scratch_database)
    with outsider_role(cluster, database) as outsider:
        with cluster.admin_connection(database) as conn:
            conn.execute(f"GRANT SELECT (password_hash) ON users TO {outsider}")

        findings = run_verify(cluster, database)

    assert any(names_column(f, outsider, "users", "password_hash") for f in findings), [
        f.detail for f in findings
    ]


def test_a_column_grant_to_public_is_reported_as_public(
    cluster: Cluster, scratch_database: Callable[[], str]
) -> None:
    database = healthy(cluster, scratch_database)
    with cluster.admin_connection(database) as conn:
        conn.execute("GRANT SELECT (password_hash) ON users TO PUBLIC")

    findings = run_verify(cluster, database)

    # Other checks may also notice the effect on a managed role; one finding must name PUBLIC.
    assert any(names_column(f, "PUBLIC", "users", "password_hash") for f in findings), [
        f.detail for f in findings
    ]


def test_the_column_finding_names_grantee_table_and_column_and_holds_no_value(
    cluster: Cluster, scratch_database: Callable[[], str]
) -> None:
    database = healthy(cluster, scratch_database)
    with outsider_role(cluster, database) as outsider:
        with cluster.admin_connection(database) as conn:
            conn.execute(f"GRANT SELECT (email) ON users TO {outsider}")

        findings = run_verify(cluster, database)
        text = render_findings(findings)

    assert any(names_column(f, outsider, "users", "email") for f in findings), [
        f.detail for f in findings
    ]
    for secret in (
        cluster.passwords.app,
        cluster.passwords.migrator,
        cluster.passwords.worker,
        cluster.passwords.cli,
        "SCRAM-SHA-256",
    ):
        assert secret not in text


def test_verify_reports_a_column_grant_without_removing_it(
    cluster: Cluster, scratch_database: Callable[[], str]
) -> None:
    database = healthy(cluster, scratch_database)
    with outsider_role(cluster, database) as outsider:
        with cluster.admin_connection(database) as conn:
            conn.execute(f"GRANT SELECT (password_hash) ON users TO {outsider}")

        findings = run_verify(cluster, database)

        with cluster.admin_connection(database) as conn:
            row = conn.execute(
                "SELECT pg_catalog.has_column_privilege(%s, 'users', 'password_hash', 'SELECT')",
                (outsider,),
            ).fetchone()
    assert any(names_column(f, outsider, "users", "password_hash") for f in findings)
    assert row == (True,)  # the verifier repairs nothing


def test_an_outsider_without_privileges_is_not_a_finding(
    cluster: Cluster, scratch_database: Callable[[], str]
) -> None:
    database = healthy(cluster, scratch_database)
    forget_database_grants_of_earlier_drifts(cluster)
    with outsider_role(cluster, database):
        assert run_verify(cluster, database) == []


def test_the_column_grants_of_the_managed_roles_are_not_findings(
    cluster: Cluster, scratch_database: Callable[[], str]
) -> None:
    database = healthy(cluster, scratch_database)
    forget_database_grants_of_earlier_drifts(cluster)
    with cluster.admin_connection(database) as conn:
        managed_column_acls = conn.execute(
            "SELECT count(*) FROM pg_catalog.pg_attribute a "
            "WHERE a.attrelid = 'public.users'::pg_catalog.regclass AND a.attacl IS NOT NULL"
        ).fetchone()
    assert managed_column_acls is not None and managed_column_acls[0] > 0  # the premise

    assert run_verify(cluster, database) == []
