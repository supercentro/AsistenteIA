"""The privileges the catalog reports for the runtime roles are exactly the matrix (task 9.2).

`information_schema` is read with the administrator on a database prepared like production. Every
column privilege, table privilege and PUBLIC grant is compared with `app.db_privileges.MATRIX`,
so an unexpected grant (for example one of the six columns that the ORM used to need) fails here.
Run with `-s` to print the effective matrix that the group report records.
"""

from collections import defaultdict

from app.db_privileges import APP, CLI, MATRIX, WORKER
from tests.db_admin_support import Cluster
from tests.db_admin_support import cluster as cluster  # noqa: F401  (fixture)
from tests.db_admin_support import scratch_database as scratch_database  # noqa: F401  (fixture)
from tests.db_roles_support import own_database as own_database

Effective = dict[str, dict[str, set[str]]]  # table -> kind -> columns (DELETE: {"*"})


def effective(cluster: Cluster, database: str, role: str) -> Effective:
    found: Effective = defaultdict(lambda: defaultdict(set))
    with cluster.admin_connection(database) as conn:
        for table, kind, column in conn.execute(
            "SELECT table_name, privilege_type, column_name "
            "FROM information_schema.column_privileges "
            "WHERE table_schema = 'public' AND grantee = %s",
            (role,),
        ).fetchall():
            found[str(table)][str(kind)].add(str(column))
        for table, kind in conn.execute(
            "SELECT table_name, privilege_type FROM information_schema.table_privileges "
            "WHERE table_schema = 'public' AND grantee = %s AND privilege_type NOT IN "
            "('SELECT', 'INSERT', 'UPDATE')",
            (role,),
        ).fetchall():
            found[str(table)][str(kind)].add("*")
    return found


def declared(logical: str) -> Effective:
    expected: Effective = defaultdict(lambda: defaultdict(set))
    for table, grant in MATRIX[logical].items():
        for kind, columns in (
            ("SELECT", grant.select),
            ("INSERT", grant.insert),
            ("UPDATE", grant.update),
        ):
            if columns:
                expected[table][kind] = set(columns)
        if grant.delete:
            expected[table]["DELETE"] = {"*"}
    return expected


def normalised(value: Effective) -> dict[str, dict[str, list[str]]]:
    return {t: {k: sorted(c) for k, c in kinds.items() if c} for t, kinds in value.items() if kinds}


def test_the_effective_privileges_equal_the_matrix_with_no_unexpected_grant(
    cluster: Cluster, own_database: str
) -> None:
    names = {APP: cluster.names.app, WORKER: cluster.names.worker, CLI: cluster.names.cli}
    for logical, role in names.items():
        actual = normalised(effective(cluster, own_database, role))
        assert actual == normalised(declared(logical)), logical
        print(f"\n== {logical} ({role})")
        for table in sorted(actual):
            for kind, columns in sorted(actual[table].items()):
                print(f"  {table:16} {kind:7} {', '.join(columns)}")


def test_nothing_is_granted_to_public_and_no_runtime_role_owns_an_object(
    cluster: Cluster, own_database: str
) -> None:
    with cluster.admin_connection(own_database) as conn:
        public = conn.execute(
            "SELECT count(*) FROM information_schema.table_privileges "
            "WHERE table_schema = 'public' AND grantee = 'PUBLIC'"
        ).fetchone()
        owned = conn.execute(
            "SELECT count(*) FROM pg_catalog.pg_class c "
            "JOIN pg_catalog.pg_roles r ON r.oid = c.relowner "
            "WHERE c.relnamespace = 'public'::regnamespace AND r.rolname IN (%s, %s, %s)",
            (cluster.names.app, cluster.names.worker, cluster.names.cli),
        ).fetchone()
    assert public == (0,) and owned == (0,)
