"""Privacy by shape (task 1.3): no field of the activity response can hold text or a person.

The test walks the JSON schema of the response. A new field fails the allow-list until somebody
reviews it, and any string field must be a date, an identifier of a document, a file name or a
closed set of values.
"""

from typing import Any

from app.schemas.activity import ActivityResponse

ALLOWED_FIELDS = {
    # response
    "window", "minimum_group", "enrolled_students", "active_students", "questions",
    "no_material_rate", "no_cited_source_rate", "documents", "suppressed",
    # window
    "start", "end", "granularity", "weeks",
    # period
    "period_start", "count",
    # document
    "document_id", "filename", "cited_appearances",
}  # fmt: skip
FORBIDDEN_FRAGMENTS = (
    "student_id",
    "email",
    "user",
    "text",
    "content",
    "message",
    "question_text",
    "answer",
    "name_of",
)


def leaves(
    node: dict[str, Any], defs: dict[str, Any], path: str = ""
) -> list[tuple[str, dict[str, Any]]]:
    """Every property of the schema with its resolved definition, recursively."""
    found: list[tuple[str, dict[str, Any]]] = []
    for name, raw in node.get("properties", {}).items():
        definition = _resolve(raw, defs)
        found.append((f"{path}{name}", definition))
        found.extend(leaves(definition, defs, f"{path}{name}."))
        items = definition.get("items")
        if items is not None:
            found.extend(leaves(_resolve(items, defs), defs, f"{path}{name}[]."))
    return found


def _resolve(node: dict[str, Any], defs: dict[str, Any]) -> dict[str, Any]:
    if "$ref" in node:
        return defs[node["$ref"].split("/")[-1]]
    for key in ("anyOf", "oneOf", "allOf"):
        for option in node.get(key, []):
            resolved = _resolve(option, defs)
            if resolved.get("properties") or resolved.get("type") not in (None, "null"):
                return resolved
    return node


def variants(node: dict[str, Any]) -> list[dict[str, Any]]:
    return node.get("anyOf", [node])


def test_the_response_has_only_reviewed_fields() -> None:
    schema = ActivityResponse.model_json_schema(mode="serialization")
    names = {
        path.split(".")[-1].removesuffix("[]")
        for path, _ in leaves(schema, schema.get("$defs", {}))
    }

    assert names == ALLOWED_FIELDS


def test_no_field_name_can_hold_text_an_email_or_a_student() -> None:
    schema = ActivityResponse.model_json_schema(mode="serialization")
    for path, _ in leaves(schema, schema.get("$defs", {})):
        leaf = path.split(".")[-1]
        assert not any(fragment in leaf for fragment in FORBIDDEN_FRAGMENTS), path


def test_every_string_field_is_a_date_an_identifier_a_file_name_or_a_closed_set() -> None:
    schema = ActivityResponse.model_json_schema(mode="serialization")
    free_text: list[str] = []
    for path, definition in leaves(schema, schema.get("$defs", {})):
        for option in variants(definition):
            if option.get("type") != "string":
                continue
            closed = "enum" in option or "const" in option
            formatted = option.get("format") in {"date", "uuid"}
            if not (closed or formatted or path.endswith("filename")):
                free_text.append(path)

    assert free_text == []


def test_the_only_free_string_is_the_file_name_of_a_document_of_the_subject() -> None:
    schema = ActivityResponse.model_json_schema(mode="serialization")
    strings = [
        path
        for path, definition in leaves(schema, schema.get("$defs", {}))
        for option in variants(definition)
        if option.get("type") == "string" and not {"enum", "const", "format"} & option.keys()
    ]

    assert strings == ["documents[].filename"]
