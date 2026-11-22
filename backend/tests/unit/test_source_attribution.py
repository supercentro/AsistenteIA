"""Attribution of the sources of an answer (change chat-source-presentation, slice 2).

`attribution_of` derives, from the stored answer text and the stored ranks, whether the sources of a
message were cited by the answer or are only the chunks that were retrieved. It is the same
decision `select_cited` takes when the answer is produced, so the answer of the chat and the
history agree, also for messages stored before the field existed.
"""

import random
from typing import Any

import pytest

from app.schemas.chat import ChatResponse
from app.schemas.conversation import MessageResponse
from app.services.prompt_builder import attribution_of, cited_ranks, select_cited
from tests.contract_support import load_spec, resolve

# --- the derivation ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("content", "ranks", "expected"),
    [
        ("It is beta [2].", [2], "cited"),
        ("Both [1] and [3] say so.", [1, 3], "cited"),
        ("See [1, 3].", [1, 3], "cited"),
        ("See [2][4]", [2, 4], "cited"),
        ("Only [3] is cited", [3], "cited"),
        ("No markers at all", [1, 2, 3], "retrieved"),
        ("A marker [9] outside the range", [1, 2, 3], "retrieved"),
        ("[0] and [1-3]", [1, 2, 3], "retrieved"),
        ("No tengo informacion en el material.", [1, 2], "retrieved"),
        # An answer stored before the list form was read: every rank was stored by the fallback.
        ("Segun [1, 2] es asi", [1, 2, 3, 4, 5], "retrieved"),
        # Documented limit: with only 2 chunks the old fallback stored the same ranks as a citation.
        ("Segun [1, 2] es asi", [1, 2], "cited"),
    ],
)
def test_the_flag_follows_the_markers_and_the_stored_ranks(
    content: str, ranks: list[int], expected: str
) -> None:
    assert attribution_of(content, ranks) == expected


@pytest.mark.parametrize("ranks", [[], ()])
def test_no_sources_means_no_attribution(ranks: Any) -> None:
    assert attribution_of("It is [1].", ranks) is None


def test_the_order_of_the_ranks_does_not_matter() -> None:
    assert attribution_of("See [3] and [1].", [3, 1]) == "cited"


def test_the_flag_of_the_stored_data_agrees_with_the_decision_taken_when_answering() -> None:
    pieces = ["[1]", "[2]", "[3]", "[1, 3]", "[2][4]", "[9]", "[0]", "[1-3]", "text", "[ 2 ]"]
    generator = random.Random(7)  # noqa: S311 - a seeded generator for a property test
    for _ in range(3000):
        chunk_count = generator.randint(1, 6)
        content = " ".join(generator.choice(pieces) for _ in range(generator.randint(0, 5)))
        stored_ranks = select_cited(content, chunk_count)
        live = "retrieved" if not cited_ranks(content, chunk_count) else "cited"
        assert attribution_of(content, stored_ranks) == live, (content, chunk_count)


# --- the contract -------------------------------------------------------------------------------


def _schema(name: str) -> Any:
    spec = load_spec()
    return resolve(spec, spec["components"]["schemas"][name])


@pytest.mark.parametrize("name", ["ChatResponse", "Message"])
def test_the_contract_declares_the_optional_nullable_flag(name: str) -> None:
    schema = _schema(name)
    flag = schema["properties"]["attribution"]
    assert flag["enum"] == ["cited", "retrieved"] or flag["enum"] == ["cited", "retrieved", None]
    assert flag.get("nullable") is True
    assert "attribution" not in schema.get("required", [])


@pytest.mark.parametrize(
    ("model", "name"), [(ChatResponse, "ChatResponse"), (MessageResponse, "Message")]
)
def test_the_response_models_publish_the_same_values_as_the_contract(model: Any, name: str) -> None:
    published = model.model_json_schema()["properties"]["attribution"]
    values = {
        value for option in published.get("anyOf", [published]) for value in option.get("enum", [])
    }
    assert values == {"cited", "retrieved"}
    declared = set(_schema(name)["properties"]["attribution"]["enum"]) - {None}
    assert declared == values
