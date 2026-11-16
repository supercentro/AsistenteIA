"""The privilege inventory: SQL analysis goldens and the shape of what it finds.

Change `database-least-privilege`, tasks 2.1 and 2.2. The goldens are written by hand from the
SQL text and do not depend on the application code, so they check the analyser itself.
"""

import pytest

from tests.privilege_inventory import Inventory, analyse_sql, build_inventory
from tests.privilege_matrix_check import ANTICIPATED_ROOTS

# Functions that hold statements and are reached by no entry point, each with the reason.
UNREACHED_ALLOWED = {
    "app.repositories.document_repository:DocumentRepository.get_for_teacher": (
        "no endpoint or service calls it; only an integration test does"
    ),
}


@pytest.fixture(scope="module")
def inventory() -> Inventory:
    return build_inventory(ANTICIPATED_ROOTS)


def _analysed(sql: str) -> dict[tuple[str, str], set[str]]:
    return {(kind, table): columns for kind, table, columns in analyse_sql(sql)}


def test_sql_update_with_returning_and_expression() -> None:
    found = _analysed(
        "UPDATE ingestion_jobs j SET locked_by = :t, attempts = j.attempts + 1 "
        "WHERE j.id = :job AND j.payload IS NOT NULL RETURNING j.id, j.document_id"
    )
    assert found[("UPDATE", "ingestion_jobs")] == {"locked_by", "attempts"}
    assert found[("SELECT", "ingestion_jobs")] == {"attempts", "id", "payload", "document_id"}
    assert ("LOCK", "ingestion_jobs") not in found


def test_sql_unqualified_single_table_statement() -> None:
    found = _analysed(
        "UPDATE documents SET status = 'failed', chunks_count = 0 "
        "WHERE id = :doc AND status IN ('pending', 'processing')"
    )
    assert found[("UPDATE", "documents")] == {"status", "chunks_count"}
    assert found[("SELECT", "documents")] == {"id", "status"}


def test_sql_join_lock_of_one_alias() -> None:
    found = _analysed(
        "SELECT d.id AS document_id, j.id AS job_id FROM documents d "
        "JOIN ingestion_jobs j ON j.document_id = d.id WHERE d.status = 'pending' "
        "FOR UPDATE OF d SKIP LOCKED"
    )
    assert found[("LOCK", "documents")] == set()
    assert ("LOCK", "ingestion_jobs") not in found
    assert found[("SELECT", "documents")] == {"id", "status"}
    assert found[("SELECT", "ingestion_jobs")] == {"id", "document_id"}


def test_sql_cte_then_update() -> None:
    found = _analysed(
        "WITH stale AS (SELECT j.id FROM ingestion_jobs j JOIN documents d ON d.id = j.document_id "
        "WHERE d.status IN ('ready') ORDER BY j.created_at LIMIT :n FOR UPDATE OF j SKIP LOCKED) "
        "UPDATE ingestion_jobs j SET payload = NULL, updated_at = now() "
        "FROM stale WHERE j.id = stale.id RETURNING j.id"
    )
    assert found[("UPDATE", "ingestion_jobs")] == {"payload", "updated_at"}
    assert found[("LOCK", "ingestion_jobs")] == set()
    assert found[("SELECT", "ingestion_jobs")] == {"id", "document_id", "created_at"}
    assert found[("SELECT", "documents")] == {"id", "status"}


def test_sql_insert_delete_and_for_update_without_of() -> None:
    inserted = _analysed("INSERT INTO enrollments (subject_id, student_id) VALUES (:a, :b)")
    assert inserted[("INSERT", "enrollments")] == {"subject_id", "student_id"}
    deleted = _analysed("DELETE FROM documents WHERE id = :doc")
    assert deleted[("DELETE", "documents")] == set()
    assert deleted[("SELECT", "documents")] == {"id"}
    locked = _analysed("SELECT d.subject_id FROM documents d WHERE d.id = :d FOR UPDATE")
    assert locked[("LOCK", "documents")] == set()


def test_sql_without_application_tables_needs_nothing() -> None:
    assert analyse_sql("SELECT 1") == []
    assert analyse_sql("SELECT pg_advisory_xact_lock(:key)") == []


def test_every_call_is_resolved(inventory: Inventory) -> None:
    assert inventory.unresolved == []


def test_every_actor_has_statements(inventory: Inventory) -> None:
    for actor in ("api", "worker", "cli", "anticipated"):
        assert inventory.statements[actor] > 0, actor
        assert inventory.required(actor), actor


def test_functions_with_statements_are_reached_or_declared(inventory: Inventory) -> None:
    assert set(inventory.unreached) == set(UNREACHED_ALLOWED)


def test_anticipated_statement_is_not_reached_by_an_entry_point(inventory: Inventory) -> None:
    root = ANTICIPATED_ROOTS["anticipated"][0]
    for actor in ("api", "worker", "cli"):
        assert root not in inventory.reachable[actor], f"{root} is wired: drop the special case"


def test_worker_needs_derived_from_raw_sql(inventory: Inventory) -> None:
    worker = inventory.required("worker")
    assert worker["documents"]["UPDATE"] == {
        "status",
        "chunks_count",
        "error_code",
        "error_message",
    }
    assert worker["ingestion_jobs"]["UPDATE"] == {
        "payload",
        "attempts",
        "locked_by",
        "locked_until",
        "updated_at",
    }
    assert worker["document_chunks"]["SELECT"] == {"id"}
    assert "DELETE" not in worker["documents"]
    assert set(worker) == {"documents", "document_chunks", "ingestion_jobs"}


def test_api_needs_derived_from_orm_statements(inventory: Inventory) -> None:
    api = inventory.required("api")
    assert api["users"]["UPDATE"] == {"consent_version", "consent_accepted_at"}
    assert "LOCK" in api["subjects"]
    assert {"DELETE"} <= set(api["subjects"]) and "DELETE" in api["enrollments"]
    assert "DELETE" in api["documents"] and "DELETE" not in api["ingestion_jobs"]
    # The fencing token and the lease are never read by the API.
    assert not {"locked_by", "locked_until"} & api["ingestion_jobs"]["SELECT"]
    # Registration no longer inserts the role (task 8.4): the server default supplies `student`.
    assert "role" not in api["users"]["INSERT"]


def test_cli_needs_only_users(inventory: Inventory) -> None:
    cli = inventory.required("cli")
    assert set(cli) == {"users"}
    assert cli["users"]["INSERT"] == {
        "name",
        "email",
        "password_hash",
        "role",
    }
    assert "UPDATE" not in cli["users"] and "DELETE" not in cli["users"]
