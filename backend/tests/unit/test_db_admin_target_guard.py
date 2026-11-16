"""The cluster-wide commands refuse a system database as their target (PG-07, task 15.2).

`--database postgres`, `template0` and `template1` would install the extension, close `PUBLIC` or
move ownership inside a database the cluster itself depends on. The guard runs before any
connection: the administrator URL below points to a port nobody listens on, so a connection
attempt would produce a different error than the one asserted.
"""

import pytest

from app.db_admin.adopt import adopt, rollback_adoption
from app.db_admin.bootstrap import bootstrap
from app.db_admin.errors import DbAdminError
from app.db_admin.names import RolePasswords

NOWHERE = "postgresql+psycopg://admin:never-used-secret@127.0.0.1:1/postgres"
PASSWORDS = RolePasswords(
    migrator="m" * 20 + "A1", app="a" * 20 + "B2", worker="w" * 20 + "C3", cli="c" * 20 + "D4"
)
SYSTEM_DATABASES = ["postgres", "template0", "template1"]


@pytest.mark.parametrize("database", SYSTEM_DATABASES)
def test_bootstrap_refuses_a_system_database_before_connecting(database: str) -> None:
    with pytest.raises(DbAdminError, match="system database") as refused:
        bootstrap(NOWHERE, PASSWORDS, database=database)

    assert "never-used-secret" not in str(refused.value)


@pytest.mark.parametrize("database", SYSTEM_DATABASES)
@pytest.mark.parametrize("apply", [False, True])
def test_adopt_refuses_a_system_database_before_connecting(database: str, apply: bool) -> None:
    with pytest.raises(DbAdminError, match="system database"):
        adopt(NOWHERE, database=database, apply=apply)


@pytest.mark.parametrize("database", SYSTEM_DATABASES)
@pytest.mark.parametrize("remove_roles", [False, True])
def test_the_rollback_refuses_a_system_database_before_connecting(
    database: str, remove_roles: bool
) -> None:
    with pytest.raises(DbAdminError, match="system database"):
        rollback_adoption(NOWHERE, database=database, remove_roles=remove_roles)


@pytest.mark.parametrize("database", ["POSTGRES", "Template1", " postgres ", "TEMPLATE0"])
def test_the_guard_does_not_depend_on_the_spelling(database: str) -> None:
    """A near miss of a system name is refused as well, never taken for an application database."""
    with pytest.raises(DbAdminError, match="system database"):
        bootstrap(NOWHERE, PASSWORDS, database=database)
