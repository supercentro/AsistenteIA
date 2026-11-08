"""The validation helper and the database check `vector_norm(embedding) BETWEEN 1e-6 AND 1e6`
must agree on every vector, including those next to the edges (finding F5)."""

import math
import random

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
    vectors = near_edge_vectors()
    assert len(vectors) >= 80
    disagreements = [
        index
        for index, vector in enumerate(vectors)
        if accepted_by_helper(vector) != accepted_by_database(clean_db, vector)
    ]
    assert disagreements == []


@pytest.mark.parametrize("edge", [1e-6, 1e6])
def test_both_outcomes_occur_around_each_edge(clean_db: str, edge: float) -> None:
    """Guards the test above: the sample must contain accepted and rejected vectors."""
    outcomes = {
        accepted_by_database(clean_db, vector)
        for vector in near_edge_vectors()
        if 0.5 * edge < math.hypot(*vector) < 2 * edge
    }
    assert outcomes == {True, False}
