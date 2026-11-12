"""Compares the privilege matrix with the mechanical inventory (change `database-least-privilege`).

`compare` returns one message per disagreement; an empty list means the matrix is exactly what the
code needs, apart from the two documented, tested exceptions below.
"""

from collections.abc import Mapping

from app.db_privileges import APP, CLI, KNOWN_COLUMNS, WORKER, TableGrant
from tests.privilege_inventory import TABLES, Inventory

ACTOR_ROLE = {"api": APP, "worker": WORKER, "cli": CLI}

# (role, table, kind, column): the code needs it today, the matrix does not grant it yet.
KNOWN_GAPS: dict[tuple[str, str, str, str], str] = {
    (APP, "users", "INSERT", "role"): (
        "registration still passes role=student; task 8.4 removes it from the code and "
        "migration 0006 gives users.role a server default (decision DD-9, option A)"
    ),
}

# Anticipated needs: the matrix grants them although no entry point reaches the statement yet.
# The statements are named by the extra root given to the inventory, and `compare` fails as soon
# as an entry point reaches them (the entry then becomes derived and this exception must go).
ANTICIPATED_ROOTS = {
    "anticipated": ["app.repositories.chunk_repository:ChunkRepository.find_similar"],
}

_KINDS = (("select", "SELECT"), ("insert", "INSERT"), ("update", "UPDATE"))


def compare(
    matrix: Mapping[str, Mapping[str, TableGrant]],
    inventory: Inventory,
    known_columns: Mapping[str, frozenset[str]] = KNOWN_COLUMNS,
    known_gaps: Mapping[tuple[str, str, str, str], str] = KNOWN_GAPS,
) -> list[str]:
    problems: list[str] = []
    for table, columns in TABLES.items():
        if table not in known_columns:
            problems.append(f"table {table} has no KNOWN_COLUMNS entry")
        elif known_columns[table] != frozenset(columns):
            delta = sorted(known_columns[table] ^ frozenset(columns))
            problems.append(f"columns of {table} changed without a decision: {delta}")
    for table in known_columns:
        if table not in TABLES:
            problems.append(f"KNOWN_COLUMNS lists unknown table {table}")

    for actor, role in ACTOR_ROLE.items():
        required = inventory.required(actor)
        grants = matrix.get(role)
        if grants is None:
            problems.append(f"role {role} has no matrix")
            continue
        for table in TABLES:
            if table not in grants:
                problems.append(f"role {role} has no decision for table {table}")
        for table in grants:
            if table not in TABLES:
                problems.append(f"role {role} grants on unknown table {table}")
        for table, grant in grants.items():
            if table not in TABLES:
                continue
            needed = required.get(table, {})
            for attribute, kind in _KINDS:
                granted: frozenset[str] = getattr(grant, attribute)
                derived = needed.get(kind, frozenset())
                unknown = granted - frozenset(TABLES[table])
                if unknown:
                    problems.append(f"{role} {kind} {table}: unknown columns {sorted(unknown)}")
                allowed_gap = {c for c in derived if (role, table, kind, c) in known_gaps}
                for column in sorted(derived - granted - allowed_gap):
                    problems.append(f"{role} needs {kind} ({column}) on {table} but lacks it")
                carrier = {grant.lock_carrier} if kind == "UPDATE" and grant.lock_carrier else set()
                ahead = (
                    inventory.required("anticipated").get(table, {}).get(kind, frozenset())
                    if role == APP
                    else frozenset()
                )
                for column in sorted(granted - derived - carrier - ahead):
                    problems.append(f"{role} has {kind} ({column}) on {table} that no code uses")
            if "LOCK" in needed and not grant.update:
                problems.append(f"{role} locks rows of {table} but has no UPDATE column")
            if grant.lock_carrier:
                if grant.lock_carrier not in grant.update:
                    problems.append(f"{role} {table}: lock carrier is not an UPDATE column")
                if "LOCK" not in needed:
                    problems.append(f"{role} {table}: lock carrier without any row lock")
            if grant.delete != ("DELETE" in needed):
                problems.append(f"{role} DELETE on {table}: granted={grant.delete}")
        for (g_role, table, kind, column), _ in known_gaps.items():
            if g_role == role and column not in required.get(table, {}).get(kind, frozenset()):
                problems.append(f"known gap {role} {kind} {table}.{column} is no longer needed")
            if g_role == role and column in getattr(grants.get(table), kind.lower(), frozenset()):
                problems.append(f"known gap {role} {kind} {table}.{column} is already granted")
    for root in ANTICIPATED_ROOTS["anticipated"]:
        if any(root in keys for actor, keys in inventory.reachable.items() if actor in ACTOR_ROLE):
            problems.append(f"{root} is now reached by an entry point: drop ANTICIPATED_ROOTS")
    return problems
