"""The validation helper and the database check `vector_norm(embedding) BETWEEN 1e-6 AND 1e6`
must agree on every vector, including those next to the edges (finding F5)."""

import math
import random
import struct

import pytest

from app.core.vector_validation import InvalidSearchInputError, validate_embedding
from tests.sql_support import scalar, vector_literal


def accepted_by_helper(vector: list[float]) -> bool:
    try:
        validate_embedding(vector)
    except InvalidSearchInputError:
        return False
    return True


def accepted_by_database(url: str, vector: list[float]) -> bool:
    value = scalar(
        url,
        "SELECT vector_norm(CAST(:v AS vector(384))) BETWEEN 1e-6 AND 1e6",
        v=vector_literal(vector),
    )
    assert isinstance(value, bool)
    return value


def near_edge_vectors() -> list[list[float]]:
    rng = random.Random(20261108)  # noqa: S311 - reproducible test data
    vectors: list[list[float]] = []
    for edge in (1e-6, 1e6):
        for factor in (1 - 1e-5, 1 - 1e-7, 1 - 3e-8, 1 - 1e-8, 1.0, 1 + 1e-8, 1 + 3e-8, 1 + 1e-7):
            single = [0.0] * 384
            single[0] = edge * factor
            vectors.append(single)
            uniform = [edge * factor / math.sqrt(384)] * 384
            vectors.append(uniform)
            for _ in range(3):
                raw = [rng.uniform(-1, 1) for _ in range(384)]
                norm = math.hypot(*raw)
                vectors.append([x * edge * factor / norm for x in raw])
    return vectors


def test_helper_and_database_check_agree_next_to_both_edges(clean_db: str) -> None:
    """Away from the safety margin the two decisions are identical; inside it only the helper
    may be stricter (never the other way round)."""
    vectors = near_edge_vectors()
    assert len(vectors) >= 80
    unsafe = []
    stricter = 0
    for index, vector in enumerate(vectors):
        helper, database = accepted_by_helper(vector), accepted_by_database(clean_db, vector)
        if helper and not database:
            unsafe.append(index)
        if database and not helper:
            stricter += 1
            single = [_single(x) for x in vector]
            norm = math.hypot(*single)
            assert min(abs(norm - 1e-6) / 1e-6, abs(norm - 1e6) / 1e6) < 1e-12
    assert unsafe == []
    assert stricter <= 12  # only vectors stored as exactly an edge value


@pytest.mark.parametrize("edge", [1e-6, 1e6])
def test_both_outcomes_occur_around_each_edge(clean_db: str, edge: float) -> None:
    """Guards the test above: the sample must contain accepted and rejected vectors."""
    outcomes = {
        accepted_by_database(clean_db, vector)
        for vector in near_edge_vectors()
        if 0.5 * edge < math.hypot(*vector) < 2 * edge
    }
    assert outcomes == {True, False}


# ------------------------------------------------ residual disagreements found by the review


def _single(value: float) -> float:
    return float(struct.unpack("<f", struct.pack("<f", value))[0])


def _next_single(value: float) -> float:
    bits = struct.unpack("<I", struct.pack("<f", abs(value)))[0]
    return float(struct.unpack("<f", struct.pack("<I", bits + 1))[0])


def midpoint_vectors() -> list[list[float]]:
    """Near the edges, with half of the components at exact single-precision midpoints."""
    rng = random.Random(7)  # noqa: S311 - reproducible test data
    vectors: list[list[float]] = []
    for edge in (1e-6, 1e6):
        for _ in range(150):
            raw = [rng.uniform(-1, 1) for _ in range(384)]
            norm = math.hypot(*raw)
            scale = edge * (1 + rng.uniform(-3e-7, 3e-7)) / norm
            vector = []
            for index, x in enumerate(raw):
                value = x * scale
                if index % 2:
                    low = _single(value)
                    high = _next_single(low) if value >= 0 else -_next_single(low)
                    value = (low + high) / 2  # exact midpoint of two single-precision numbers
                vector.append(value)
            vectors.append(vector)
    return vectors


def _step_single(value: float, steps: int) -> float:
    """`value` (positive) moved by `steps` single-precision numbers."""
    bits = struct.unpack("<I", struct.pack("<f", value))[0]
    return float(struct.unpack("<f", struct.pack("<I", bits + steps))[0])


def summation_order_vectors() -> list[list[float]]:
    """Exact single-precision components whose exact norm is within about 1e-13 of an edge."""
    rng = random.Random(11)  # noqa: S311 - reproducible test data
    vectors: list[list[float]] = []
    for edge in (1e-6, 1e6):
        for _ in range(40):
            body: list[float] = []
            remainder = -1.0
            while not 0 < remainder < 2e-10 * edge * edge:  # a small positive remainder
                raw = [rng.uniform(-1, 1) for _ in range(383)]
                factor = edge * (1 - 1e-10) / math.hypot(*raw)
                body = [_single(x * factor) for x in raw]
                remainder = edge * edge - math.fsum(x * x for x in body)
            last = _single(math.sqrt(remainder))
            for steps in range(-25, 26):
                vectors.append([*body, _step_single(last, steps)])
    return vectors


def helper_accepts_implies_database_accepts(url: str, vectors: list[list[float]]) -> list[int]:
    """Indexes of vectors that the helper accepts but the database check rejects.

    What is checked in the database is what the helper returns, which is what the repository
    binds as the query (and what ingestion must bind).
    """
    unsafe: list[int] = []
    for index, vector in enumerate(vectors):
        try:
            accepted = validate_embedding(vector)
        except InvalidSearchInputError:
            continue
        if not accepted_by_database(url, accepted):
            unsafe.append(index)
    return unsafe


def test_a_vector_accepted_by_the_helper_is_never_rejected_by_the_database_at_midpoints(
    clean_db: str,
) -> None:
    vectors = midpoint_vectors()
    assert helper_accepts_implies_database_accepts(clean_db, vectors) == []


def test_a_vector_accepted_by_the_helper_is_never_rejected_by_the_database_by_summation_order(
    clean_db: str,
) -> None:
    vectors = summation_order_vectors()
    assert len(vectors) >= 4000
    assert helper_accepts_implies_database_accepts(clean_db, vectors) == []


def test_the_accepted_vector_is_returned_in_single_precision_so_the_text_round_trips() -> None:
    vector = [0.0] * 384
    vector[0] = (_single(1.0) + _next_single(1.0)) / 2 * 5e5  # a midpoint component
    returned = validate_embedding(vector)
    assert returned[0] == _single(returned[0])
