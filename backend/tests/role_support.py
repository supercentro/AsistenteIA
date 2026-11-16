"""Reserved names for the PostgreSQL roles that tests create, and the sweep of their leftovers.

Change `database-least-privilege`, task 3.4. Roles are cluster objects: a test that creates or
drops one can reach the real roles of the same server. Every role a test touches therefore carries
`TEST_ROLE_PREFIX`, no real role name can match it, and the only statements that drop roles run
through `sweep_test_roles`, which refuses a name without the prefix. The sweep takes a connection
and never opens one; the role-bound fixtures (group 9) call it with the guarded administrator URL.
"""

import re
from collections.abc import Sequence
from typing import Any, Protocol

from app.core.db_safety import UnsafeTestDatabaseError

TEST_ROLE_PREFIX = "tstrole_"
# Names that exist, or will, in a real cluster of this project; none may start with the prefix.
REAL_ROLE_NAMES: Sequence[str] = (
    "asistente",
    "asistente_migrator",
    "asistente_app",
    "asistente_worker",
    "asistente_cli",
)
_NAME = re.compile(rf"^{TEST_ROLE_PREFIX}[a-z0-9_]{{1,40}}$")


class _Result(Protocol):
    def fetchall(self) -> list[Any]: ...


class RoleConnection(Protocol):
    def execute(self, statement: str, parameters: Sequence[str] | None = None) -> _Result: ...


def make_test_role_name(suffix: str) -> str:
    """A role name for a test, validated before it can reach a statement."""
    name = TEST_ROLE_PREFIX + suffix
    assert_test_role_name(name)
    return name


def assert_test_role_name(name: str) -> None:
    """Raise unless `name` is a reserved test role name made of safe identifier characters."""
    if not _NAME.fullmatch(name):
        raise UnsafeTestDatabaseError(
            f"Refusing role name {name[:30]!r}: tests may only use names matching "
            f"'{TEST_ROLE_PREFIX}' followed by 1-40 of [a-z0-9_]"
        )


def sweep_test_roles(connection: RoleConnection) -> list[str]:
    """Drop the roles left by earlier runs (what they own first) and return their names."""
    pattern = TEST_ROLE_PREFIX.replace("_", r"\_") + "%"
    found = connection.execute(
        "SELECT rolname FROM pg_catalog.pg_roles WHERE rolname LIKE %s ESCAPE '" + chr(92) + "'",
        (pattern,),
    )
    names = [str(row[0]) for row in found.fetchall()]
    for name in names:  # validate every name before dropping any
        assert_test_role_name(name)
    for name in names:
        connection.execute(f'DROP OWNED BY "{name}"')
        connection.execute(f'DROP ROLE "{name}"')
    return names
