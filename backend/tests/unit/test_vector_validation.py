"""Validation of query vectors and `top_k` (D8): rejected early, values never leaked."""

import math

import pytest

from app.core.vector_validation import (
    EMBEDDING_DIMENSIONS,
    MAX_NORM,
    MAX_TOP_K,
    MIN_NORM,
    InvalidSearchInputError,
    validate_embedding,
    validate_top_k,
)
from tests import embeddings as emb

SECRET = 7.654321e-3  # a recognisable component that must never appear in an error message


def unit(index: int = 0) -> list[float]:
    return emb.basis(index)


def with_norm(norm: float) -> list[float]:
    return emb.scaled(emb.basis(0), norm)


def single_precision(vector: list[float]) -> list[float]:
    import struct

    return [struct.unpack("f", struct.pack("f", x))[0] for x in vector]


def test_range_constants_match_the_database_check() -> None:
    assert EMBEDDING_DIMENSIONS == 384
    assert MIN_NORM == 1e-6
    assert MAX_NORM == 1e6
    assert MAX_TOP_K == 50


@pytest.mark.parametrize("size", [0, 1, 383, 385, 768])
def test_wrong_dimension_is_rejected(size: int) -> None:
    with pytest.raises(InvalidSearchInputError):
        validate_embedding([1.0] * size)


@pytest.mark.parametrize("bad", [math.nan, math.inf, -math.inf])
def test_non_finite_components_are_rejected(bad: float) -> None:
    vector = unit()
    vector[100] = bad
    with pytest.raises(InvalidSearchInputError):
        validate_embedding(vector)


def test_zero_vector_is_rejected() -> None:
    with pytest.raises(InvalidSearchInputError):
        validate_embedding([0.0] * EMBEDDING_DIMENSIONS)


@pytest.mark.parametrize("norm", [1e-7, 1e-30, 1e7, 1e38])
def test_norms_outside_the_reliable_range_are_rejected(norm: float) -> None:
    with pytest.raises(InvalidSearchInputError):
        validate_embedding(with_norm(norm))


def test_one_large_component_pushing_the_norm_above_the_range_is_rejected() -> None:
    vector = unit()
    vector[200] = 1.0000001e6
    with pytest.raises(InvalidSearchInputError):
        validate_embedding(vector)


def test_overflowing_squares_are_rejected_not_accepted_as_infinite_norm() -> None:
    vector = unit()
    vector[5] = 1e200  # its square overflows a double: still outside the range
    with pytest.raises(InvalidSearchInputError):
        validate_embedding(vector)


@pytest.mark.parametrize("norm", [1e-6, 1e6])
def test_norms_exactly_at_the_edges_are_accepted(norm: float) -> None:
    assert validate_embedding(with_norm(norm)) == with_norm(norm)


def test_unit_vectors_and_single_precision_unit_vectors_are_accepted() -> None:
    assert validate_embedding(unit()) == unit()
    rounded = single_precision(emb.deterministic_vector(3))
    assert validate_embedding(rounded) == rounded


@pytest.mark.parametrize("item", ["1.0", None, b"1", [1.0], {"x": 1.0}, 1 + 2j])
def test_non_numeric_items_are_rejected(item: object) -> None:
    vector: list[object] = list(unit())
    vector[10] = item
    with pytest.raises(InvalidSearchInputError):
        validate_embedding(vector)  # type: ignore[arg-type]


@pytest.mark.parametrize("value", [None, "a string", 5, 1.5, {"a": 1}])
def test_non_sequence_embeddings_are_rejected(value: object) -> None:
    with pytest.raises(InvalidSearchInputError):
        validate_embedding(value)  # type: ignore[arg-type]


def test_booleans_are_not_accepted_as_numbers() -> None:
    vector: list[object] = list(unit())
    vector[3] = True
    with pytest.raises(InvalidSearchInputError):
        validate_embedding(vector)  # type: ignore[arg-type]


def test_integers_are_accepted_and_returned_as_floats() -> None:
    vector: list[int] = [0] * EMBEDDING_DIMENSIONS
    vector[0] = 1
    result = validate_embedding(vector)
    assert result[0] == 1.0
    assert all(isinstance(x, float) for x in result)


@pytest.mark.parametrize("top_k", [1, 5, 50])
def test_valid_limits_are_accepted(top_k: int) -> None:
    assert validate_top_k(top_k) == top_k


@pytest.mark.parametrize("top_k", [0, -1, 51, 10_000])
def test_limits_out_of_range_are_rejected(top_k: int) -> None:
    with pytest.raises(InvalidSearchInputError):
        validate_top_k(top_k)


@pytest.mark.parametrize("top_k", [None, "5", 5.0, True])
def test_non_integer_limits_are_rejected(top_k: object) -> None:
    with pytest.raises(InvalidSearchInputError):
        validate_top_k(top_k)  # type: ignore[arg-type]


def test_error_messages_never_contain_components() -> None:
    cases: list[list[float]] = []
    secret_vector = unit()
    secret_vector[7] = SECRET
    secret_vector[8] = math.nan
    cases.append(secret_vector)
    big = unit()
    big[9] = SECRET * 1e12
    cases.append(big)
    cases.append([SECRET] * 383)
    for vector in cases:
        with pytest.raises(InvalidSearchInputError) as raised:
            validate_embedding(vector)
        text = f"{raised.value} {raised.value!r} {raised.value.args}"
        assert "7.654321" not in text
        assert "nan" not in text.lower()


def test_error_is_a_value_error_with_a_stable_generic_message() -> None:
    with pytest.raises(ValueError, match="invalid search input"):
        validate_embedding([])
    with pytest.raises(ValueError, match="invalid search input"):
        validate_top_k(0)
