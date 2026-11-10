"""Contract test (group 4, task 4.2): code and `docs/api-spec.yml` cannot drift apart.

The comparison mechanism is verified here on synthetic documents (so a broken comparison cannot
pass silently), the contract itself is checked against the closed error catalogue, and the real
application document is compared for the three document paths.
"""

import copy
from collections.abc import Mapping
from typing import Any

import pytest

from app.main import create_app
from app.models.ingestion import DocumentErrorCode
from tests.contract_support import (
    contract_differences,
    load_spec,
    operations,
    schema_names,
    schema_required,
    server_prefix,
    status_codes,
)
from tests.integration.helpers import build_settings

DOCUMENT_PATHS = [
    "/subjects/{subject_id}/documents",
    "/subjects/{subject_id}/documents/{document_id}",
]
Spec = Mapping[str, Any]


@pytest.fixture(scope="module")
def spec() -> Spec:
    return load_spec()


def application_like(spec: Spec) -> dict[str, Any]:
    """A copy of the contract as the application would publish it, under the server prefix."""
    prefix = server_prefix(spec)
    document = copy.deepcopy(dict(spec))
    document["paths"] = {prefix + path: item for path, item in document["paths"].items()}
    return document


def differences(spec: Spec, actual: dict[str, Any]) -> list[str]:
    return contract_differences(spec, actual, DOCUMENT_PATHS, server_prefix(spec))


# --- the mechanism ------------------------------------------------------------------------------


def test_the_server_prefix_is_the_api_version_path(spec: Spec) -> None:
    assert server_prefix(spec) == "/api/v1"


def test_identical_documents_have_no_differences(spec: Spec) -> None:
    assert differences(spec, application_like(spec)) == []


def mutate_drop_status(actual: dict[str, Any]) -> None:
    del actual["paths"]["/api/v1/subjects/{subject_id}/documents"]["post"]["responses"]["408"]


def mutate_extra_status(actual: dict[str, Any]) -> None:
    responses = actual["paths"]["/api/v1/subjects/{subject_id}/documents"]["get"]["responses"]
    responses["500"] = {"description": "unexpected"}


def mutate_drop_method(actual: dict[str, Any]) -> None:
    del actual["paths"]["/api/v1/subjects/{subject_id}/documents"]["post"]


def mutate_extra_method(actual: dict[str, Any]) -> None:
    item = actual["paths"]["/api/v1/subjects/{subject_id}/documents/{document_id}"]
    item["get"] = copy.deepcopy(item["delete"])


def mutate_missing_path(actual: dict[str, Any]) -> None:
    del actual["paths"]["/api/v1/subjects/{subject_id}/documents/{document_id}"]


def mutate_form_field(actual: dict[str, Any]) -> None:
    post = actual["paths"]["/api/v1/subjects/{subject_id}/documents"]["post"]
    schema = post["requestBody"]["content"]["multipart/form-data"]["schema"]
    schema["properties"]["upload"] = schema["properties"].pop("file")


def mutate_document_field(actual: dict[str, Any]) -> None:
    del actual["components"]["schemas"]["Document"]["properties"]["error_code"]


def mutate_document_required(actual: dict[str, Any]) -> None:
    actual["components"]["schemas"]["Document"]["required"].remove("status")


@pytest.mark.parametrize(
    ("mutation", "fragment"),
    [
        (mutate_drop_status, "status codes"),
        (mutate_extra_status, "status codes"),
        (mutate_drop_method, "methods"),
        (mutate_extra_method, "methods"),
        (mutate_missing_path, "methods"),
        (mutate_form_field, "form fields"),
        (mutate_document_field, "Document: fields"),
        (mutate_document_required, "Document: required"),
    ],
)
def test_every_kind_of_drift_is_reported(spec: Spec, mutation: Any, fragment: str) -> None:
    actual = application_like(spec)
    mutation(actual)

    found = differences(spec, actual)

    assert found, mutation.__name__
    assert any(fragment in line for line in found), found


def test_references_are_followed_when_comparing(spec: Spec) -> None:
    actual = application_like(spec)
    post = actual["paths"]["/api/v1/subjects/{subject_id}/documents"]["post"]
    schema = post["requestBody"]["content"]["multipart/form-data"]["schema"]
    actual["components"]["schemas"]["Body_upload"] = schema
    post["requestBody"]["content"]["multipart/form-data"]["schema"] = {
        "$ref": "#/components/schemas/Body_upload"
    }

    assert differences(spec, actual) == []


# --- the contract itself ------------------------------------------------------------------------


def test_the_contract_lists_the_upload_responses_of_the_design(spec: Spec) -> None:
    post = operations(spec, DOCUMENT_PATHS[0])["post"]

    assert status_codes(spec, post) == {
        "202",
        "401",
        "403",
        "404",
        "408",
        "409",
        "413",
        "415",
        "422",
        "429",
        "503",
    }
    assert status_codes(spec, operations(spec, DOCUMENT_PATHS[0])["get"]) == {
        "200",
        "401",
        "403",
        "404",
    }
    assert status_codes(spec, operations(spec, DOCUMENT_PATHS[1])["delete"]) == {
        "204",
        "401",
        "403",
        "404",
    }


def test_the_failure_codes_of_the_contract_are_the_closed_catalogue(spec: Spec) -> None:
    enum = spec["components"]["schemas"]["Document"]["properties"]["error_code"]["enum"]

    assert [value for value in enum if value is not None] == [
        code.value for code in DocumentErrorCode
    ]
    assert enum[-1] is None  # nullable enum in OpenAPI 3.0 lists null explicitly


def test_the_document_schema_requires_the_fields_a_client_depends_on(spec: Spec) -> None:
    document = {"$ref": "#/components/schemas/Document"}

    assert schema_required(spec, document) == {
        "id",
        "subject_id",
        "filename",
        "content_type",
        "size_bytes",
        "status",
        "chunks_count",
        "created_at",
    }
    assert schema_names(spec, document) == schema_required(spec, document) | {
        "error_code",
        "error_message",
    }


# --- the application ----------------------------------------------------------------------------


def test_the_application_publishes_the_document_contract(spec: Spec) -> None:
    app = create_app(build_settings("postgresql+psycopg://user:pw@localhost:5432/contract_test"))

    assert differences(spec, app.openapi()) == []
