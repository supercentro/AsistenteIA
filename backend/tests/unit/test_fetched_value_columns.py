"""The columns the code never sets on insert are fetched server values (change
`database-least-privilege`, 8A): the declared model, the mechanical inventory and the matrix agree.
"""

import pytest
from sqlalchemy import FetchedValue, inspect

from app.core.database import Base
from app.db_privileges import APP, MATRIX
from app.models.document import Document
from app.models.ingestion import IngestionJob
from tests.privilege_inventory import Inventory, build_inventory
from tests.privilege_matrix_check import ANTICIPATED_ROOTS

FETCHED = {
    "ingestion_jobs": ("locked_by", "locked_until"),
    "documents": ("error_message", "error_code"),
}


@pytest.fixture(scope="module")
def inventory() -> Inventory:
    return build_inventory(ANTICIPATED_ROOTS)


@pytest.mark.parametrize(("table", "columns"), sorted(FETCHED.items()))
def test_the_column_is_a_fetched_server_value(table: str, columns: tuple[str, ...]) -> None:
    for name in columns:
        default = Base.metadata.tables[table].c[name].server_default
        assert isinstance(default, FetchedValue), (table, name)


def test_the_job_mapper_does_not_ask_for_the_server_values_back() -> None:
    assert inspect(IngestionJob).eager_defaults is False


def test_the_api_inventory_needs_no_insert_on_the_pair_of_ingestion_jobs(
    inventory: Inventory,
) -> None:
    need = inventory.required("api")["ingestion_jobs"]

    assert need["INSERT"] == {"document_id", "payload"}
    assert not {"locked_by", "locked_until"} & need["SELECT"]  # not through RETURNING either


def test_the_matrix_grants_the_application_role_only_what_the_job_insert_sets() -> None:
    assert MATRIX[APP]["ingestion_jobs"].insert == frozenset({"document_id", "payload"})


def test_documents_keep_the_default_returning_because_the_application_reads_them() -> None:
    assert inspect(Document).eager_defaults == "auto"
    assert {"error_message", "error_code"} <= MATRIX[APP]["documents"].select


def test_the_matrix_grants_the_application_role_only_what_the_document_insert_sets() -> None:
    assert MATRIX[APP]["documents"].insert == frozenset(
        {"subject_id", "filename", "content_type", "size_bytes", "status"}
    )
