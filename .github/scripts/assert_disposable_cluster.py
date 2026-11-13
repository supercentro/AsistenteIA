"""Refuse any PostgreSQL cluster that is not the exclusive, empty, local one the workflow created.

usage:
  assert_disposable_cluster.py check <flow|tests> <ENV_VARIABLE_WITH_THE_ADMIN_URL>
  assert_disposable_cluster.py distinct <ENV_VARIABLE> <ENV_VARIABLE>

The privilege gate bootstraps roles, closes PUBLIC on every database of a cluster and drops
databases, so before anything destructive the cluster must prove what it is: a local server
(`CI_ALLOWED_HOSTS`, default 127.0.0.1 and localhost), PostgreSQL 15 with pgvector 0.8.7, a
superuser session, only the default databases (the `tests` cluster may also hold its own
`tstdb_*_test` scratch databases) and no role of the project (`asistente*`). Nothing is printed
that contains a password. Change `database-least-privilege`, task 10.1.
"""

import os
import sys
from dataclasses import dataclass, field
from urllib.parse import urlsplit

DEFAULT_DATABASES = {"postgres", "template0", "template1"}
EXPECTED_VECTOR = "0.8.7"


@dataclass(frozen=True)
class Facts:
    host: str
    port: int
    version: str
    vector_versions: list[str] = field(default_factory=list)
    databases: list[str] = field(default_factory=list)
    roles: list[str] = field(default_factory=list)
    superuser: bool = False


def evaluate(facts: Facts, label: str, allowed_hosts: set[str]) -> list[str]:
    problems: list[str] = []
    if facts.host not in allowed_hosts:
        problems.append(f"{label}: the host {facts.host} is not one of {sorted(allowed_hosts)}")
    if not facts.version.startswith("PostgreSQL 15."):
        problems.append(f"{label}: the version is not PostgreSQL 15 ({facts.version[:30]})")
    if EXPECTED_VECTOR not in facts.vector_versions:
        problems.append(f"{label}: pgvector {EXPECTED_VECTOR} is not available")
    if not facts.superuser:
        problems.append(f"{label}: the session is not a superuser, the cluster is not the one created")
    for database in facts.databases:
        scratch = label == "tests" and database.startswith("tstdb_") and database.endswith("_test")
        if database not in DEFAULT_DATABASES and not scratch:
            problems.append(f"{label}: the cluster holds the database {database}, it is not empty")
    for role in facts.roles:
        scratch = label == "tests" and role.startswith("tstrole_")
        if role.startswith("asistente") or (role.startswith("tstrole_") and not scratch):
            problems.append(f"{label}: the cluster holds the role {role}, it is not exclusive")
    return problems


def same_server(first: str, second: str) -> bool:
    a, b = urlsplit(first), urlsplit(second)
    return (a.hostname, a.port) == (b.hostname, b.port)


def describe(facts: Facts, label: str) -> str:
    return (
        f"{label}: {facts.host}:{facts.port} {facts.version.split(' on ')[0]}, "
        f"pgvector {','.join(facts.vector_versions) or 'none'}, "
        f"databases {sorted(facts.databases)}, roles {sorted(facts.roles)}, "
        f"superuser {facts.superuser}"
    )


def collect(url: str) -> Facts:
    import psycopg  # imported here so the pure functions need no driver

    parts = urlsplit(url)
    with psycopg.connect(url.replace("postgresql+psycopg", "postgresql"), autocommit=True) as conn:
        version = str(conn.execute("SELECT version()").fetchone()[0])  # type: ignore[index]
        vectors = [
            str(r[0])
            for r in conn.execute(
                "SELECT version FROM pg_available_extension_versions WHERE name = 'vector'"
            )
        ]
        databases = [str(r[0]) for r in conn.execute("SELECT datname FROM pg_database")]
        roles = [
            str(r[0]) for r in conn.execute("SELECT rolname FROM pg_roles WHERE rolname !~ '^pg_'")
        ]
        superuser = bool(
            conn.execute(
                "SELECT rolsuper FROM pg_roles WHERE rolname = current_user"
            ).fetchone()[0]  # type: ignore[index]
        )
    return Facts(parts.hostname or "", parts.port or 5432, version, vectors, databases, roles, superuser)


def main(argv: list[str]) -> int:
    allowed = set(os.environ.get("CI_ALLOWED_HOSTS", "127.0.0.1,localhost").split(","))
    if argv[:1] == ["distinct"]:
        first, second = (os.environ.get(name, "") for name in argv[1:3])
        if not first or not second:
            print(f"::error::missing prerequisite {argv[1]} or {argv[2]}")
            return 1
        if same_server(first, second):
            print("::error::the two clusters are the same server; each needs its own")
            return 1
        print("the two clusters are different servers")
        return 0
    if argv[:1] == ["check"] and len(argv) == 3:
        label, variable = argv[1], argv[2]
        url = os.environ.get(variable, "")
        if not url:
            print(f"::error::missing prerequisite {variable}")
            return 1
        facts = collect(url)
        print(describe(facts, label))
        problems = evaluate(facts, label, allowed)
        for problem in problems:
            print(f"::error::{problem}")
        return 1 if problems else 0
    print(__doc__)
    return 2


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
