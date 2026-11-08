"""Validation of query vectors and `top_k` (D8): rejected early, values never leaked."""

import math
from collections.abc import Iterator, Sequence
from typing import Any

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


def _next_single(value: float, steps: int = 1) -> float:
    """The single-precision number `steps` representable values above `value` (value >= 0)."""
    import struct

    bits = struct.unpack("<I", struct.pack("<f", value))[0]
    return float(struct.unpack("<f", struct.pack("<I", bits + steps))[0])


def test_the_upper_edge_is_accepted() -> None:
    assert validate_embedding(with_norm(1e6)) == with_norm(1e6)


def test_the_smallest_single_precision_norm_at_or_above_the_lower_edge_is_accepted() -> None:
    # 1e-6 itself is stored by the database as the single-precision number just below it (F5).
    smallest = _next_single(single_precision([1e-6])[0])
    assert smallest >= MIN_NORM
    assert validate_embedding(with_norm(smallest)) == with_norm(smallest)


def test_a_norm_that_rounds_below_the_lower_edge_in_single_precision_is_rejected() -> None:
    # In double precision this is exactly 1e-6, but the stored vector would have a norm below it.
    assert single_precision([1e-6])[0] < MIN_NORM
    with pytest.raises(InvalidSearchInputError):
        validate_embedding(with_norm(1e-6))


@pytest.mark.parametrize("factor", [1 + 1e-8, 1 + 3e-8, 1 - 3e-8])
def test_a_norm_within_single_precision_rounding_of_the_upper_edge_is_accepted(
    factor: float,
) -> None:
    # The database stores 1e6 * factor as exactly 1e6, which the check accepts (F5).
    assert validate_embedding(with_norm(1e6 * factor)) is not None


def test_the_next_single_precision_value_above_the_upper_edge_is_rejected() -> None:
    above = _next_single(1e6)
    assert above > MAX_NORM
    with pytest.raises(InvalidSearchInputError):
        validate_embedding(with_norm(above))


def test_a_component_too_small_for_single_precision_counts_as_zero() -> None:
    vector = [1e-50] * EMBEDDING_DIMENSIONS  # stored as all zeros
    with pytest.raises(InvalidSearchInputError):
        validate_embedding(vector)


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


@pytest.mark.parametrize("huge", [10**400, -(10**400)], ids=["positive", "negative"])
def test_integers_too_large_for_a_float_are_rejected_with_the_controlled_error(huge: int) -> None:
    vector: list[object] = list(unit())
    vector[2] = huge
    with pytest.raises(InvalidSearchInputError) as raised:
        validate_embedding(vector)  # type: ignore[arg-type]
    assert "400" not in str(raised.value)


class _LyingLength(Sequence[float]):
    """Reports 384 items but yields a different number: the length cannot be trusted alone."""

    def __init__(self, produced: int) -> None:
        self._produced = produced

    def __len__(self) -> int:
        return EMBEDDING_DIMENSIONS

    def __getitem__(self, index: Any) -> Any:  # pragma: no cover - iteration is used instead
        return 1.0

    def __iter__(self) -> Iterator[float]:
        return iter([1.0] * self._produced)


@pytest.mark.parametrize("produced", [0, 383, 385, 5000])
def test_a_sequence_that_yields_another_number_of_items_than_its_length_is_rejected(
    produced: int,
) -> None:
    with pytest.raises(InvalidSearchInputError):
        validate_embedding(_LyingLength(produced))


class _HostileInt(int):
    """An int subclass whose conversion to float fails in the way a broken numeric type could."""

    def __init__(self, error: Exception) -> None:
        super().__init__()
        self._error = error

    def __new__(cls, error: Exception) -> "_HostileInt":
        return super().__new__(cls, 1)

    def __float__(self) -> float:
        raise self._error


@pytest.mark.parametrize("error", [ValueError("secret-component-7.654321"), TypeError("x")])
def test_a_numeric_type_whose_float_conversion_fails_is_rejected_with_the_controlled_error(
    error: Exception,
) -> None:
    vector: list[object] = list(unit())
    vector[4] = _HostileInt(error)
    with pytest.raises(InvalidSearchInputError) as raised:
        validate_embedding(vector)  # type: ignore[arg-type]
    assert "7.654321" not in f"{raised.value} {raised.value!r}"
    assert raised.value.__cause__ is None
