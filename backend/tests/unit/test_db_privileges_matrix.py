"""The privilege matrix equals what the code needs, and the suite notices every drift.

Change `database-least-privilege`, tasks 2.1, 2.3 and 2.4 (the mutation checks run in memory: each
mutated copy of the matrix must produce a problem, so a test would fail if the guard were gone).
"""

import dataclasses

import pytest

from app.db_privileges import APP, CLI, KNOWN_COLUMNS, MATRIX, RUNTIME_ROLES, WORKER, TableGrant
from tests.privilege_inventory import TABLES, Inventory, build_inventory
from tests.privilege_matrix_check import ANTICIPATED_ROOTS, KNOWN_GAPS, compare


@pytest.fixture(scope="module")
def inventory() -> Inventory:
    return build_inventory(ANTICIPATED_ROOTS)


def _mutable() -> dict[str, dict[str, TableGrant]]:
    return {role: dict(tables) for role, tables in MATRIX.items()}


def test_matrix_equals_what_the_code_needs(inventory: Inventory) -> None:
    assert compare(MATRIX, inventory) == []


def test_every_role_decides_every_table() -> None:
    assert set(MATRIX) == set(RUNTIME_ROLES)
    for role in RUNTIME_ROLES:
        assert set(MATRIX[role]) == set(TABLES), role


def test_matrix_uses_only_known_columns() -> None:
    assert {t: frozenset(c) for t, c in TABLES.items()} == dict(KNOWN_COLUMNS)
    for role, tables in MATRIX.items():
        for table, grant in tables.items():
            used = grant.select | grant.insert | grant.update
            assert used <= KNOWN_COLUMNS[table], (role, table)


def test_the_migrator_and_alembic_are_not_in_the_matrix() -> None:
    assert "migrator" not in MATRIX and "alembic_version" not in TABLES
    for tables in MATRIX.values():
        assert "alembic_version" not in tables


def test_the_decided_least_privilege_properties() -> None:
    assert not {"locked_by", "locked_until", "document_id"} & MATRIX[APP]["ingestion_jobs"].select
    assert MATRIX[WORKER]["document_chunks"].select == frozenset({"id"})
    assert not MATRIX[WORKER]["document_chunks"].delete
    assert "role" not in MATRIX[APP]["users"].insert and "role" in MATRIX[CLI]["users"].insert
    assert MATRIX[APP]["users"].update == frozenset({"consent_version", "consent_accepted_at"})
    assert "role" not in MATRIX[APP]["users"].update
    assert MATRIX[APP]["subjects"].lock_carrier == "description"
    assert not any(g.delete for g in MATRIX[WORKER].values())
    cli_allowed = {"users", "conversations", "messages"}
    assert not any(MATRIX[CLI][t] != TableGrant() for t in TABLES if t not in cli_allowed)


def test_no_known_gap_remains_after_task_8_4(inventory: Inventory) -> None:
    assert KNOWN_GAPS == {}
    assert "role" not in inventory.required("api")["users"]["INSERT"]
    assert "role" in inventory.required("cli")["users"]["INSERT"]


# ---- mutation checks (task 2.4): each mutated matrix must be rejected ---------------------------


def _problems(matrix: dict[str, dict[str, TableGrant]], inventory: Inventory) -> list[str]:
    return compare(matrix, inventory)


def test_mutation_remove_a_needed_grant(inventory: Inventory) -> None:
    mutated = _mutable()
    grant = mutated[WORKER]["documents"]
    mutated[WORKER]["documents"] = dataclasses.replace(
        grant, update=grant.update - frozenset({"status"})
    )
    assert any(
        "worker needs UPDATE (status) on documents" in p for p in _problems(mutated, inventory)
    )


def test_mutation_remove_the_worker_returning_column(inventory: Inventory) -> None:
    mutated = _mutable()
    mutated[WORKER]["document_chunks"] = dataclasses.replace(
        mutated[WORKER]["document_chunks"], select=frozenset()
    )
    assert any(
        "worker needs SELECT (id) on document_chunks" in p for p in _problems(mutated, inventory)
    )


def test_mutation_add_an_extra_grant(inventory: Inventory) -> None:
    mutated = _mutable()
    grant = mutated[APP]["users"]
    mutated[APP]["users"] = dataclasses.replace(grant, update=grant.update | {"role"})
    assert any(
        "app has UPDATE (role) on users that no code uses" in p
        for p in _problems(mutated, inventory)
    )


def test_mutation_add_an_extra_delete(inventory: Inventory) -> None:
    mutated = _mutable()
    mutated[APP]["ingestion_jobs"] = dataclasses.replace(
        mutated[APP]["ingestion_jobs"], delete=True
    )
    assert any("DELETE on ingestion_jobs" in p for p in _problems(mutated, inventory))


def test_mutation_widen_a_select(inventory: Inventory) -> None:
    mutated = _mutable()
    grant = mutated[APP]["ingestion_jobs"]
    mutated[APP]["ingestion_jobs"] = dataclasses.replace(grant, select=grant.select | {"locked_by"})
    assert any("app has SELECT (locked_by)" in p for p in _problems(mutated, inventory))


def test_mutation_drop_a_table_from_a_role(inventory: Inventory) -> None:
    mutated = _mutable()
    del mutated[CLI]["enrollments"]
    assert any(
        "cli has no decision for table enrollments" in p for p in _problems(mutated, inventory)
    )


def test_mutation_drop_a_role(inventory: Inventory) -> None:
    mutated = _mutable()
    del mutated[WORKER]
    assert any("role worker has no matrix" in p for p in _problems(mutated, inventory))


def test_mutation_grant_on_an_unknown_table(inventory: Inventory) -> None:
    mutated = _mutable()
    mutated[APP]["audit_log"] = TableGrant()
    assert any("unknown table audit_log" in p for p in _problems(mutated, inventory))


def test_mutation_remove_the_lock_carrier(inventory: Inventory) -> None:
    mutated = _mutable()
    mutated[APP]["subjects"] = dataclasses.replace(
        mutated[APP]["subjects"], update=frozenset(), lock_carrier=None
    )
    assert any(
        "locks rows of subjects but has no UPDATE column" in p
        for p in _problems(mutated, inventory)
    )


def test_mutation_a_new_column_needs_a_decision(inventory: Inventory) -> None:
    columns = {t: set(c) for t, c in KNOWN_COLUMNS.items()}
    columns["users"].discard("created_at")  # as if the model gained created_at after the review
    reduced = {t: frozenset(c) for t, c in columns.items()}
    assert any("columns of users changed" in p for p in compare(MATRIX, inventory, reduced))


def test_mutation_a_new_table_needs_a_decision(inventory: Inventory) -> None:
    reduced = {t: c for t, c in KNOWN_COLUMNS.items() if t != "documents"}
    assert any(
        "table documents has no KNOWN_COLUMNS" in p for p in compare(MATRIX, inventory, reduced)
    )


def test_mutation_granting_the_role_to_the_application_is_rejected(inventory: Inventory) -> None:
    mutated = _mutable()
    grant = mutated[APP]["users"]
    mutated[APP]["users"] = dataclasses.replace(grant, insert=grant.insert | {"role"})
    problems = _problems(mutated, inventory)
    assert any("role" in p for p in problems), problems


def test_mutation_a_stale_gap_is_rejected(inventory: Inventory) -> None:
    stale = {(APP, "ingestion_jobs", "UPDATE", "locked_by"): "not needed by any code"}
    assert any("no longer needed" in p for p in compare(MATRIX, inventory, KNOWN_COLUMNS, stale))
