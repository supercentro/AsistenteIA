"""The deterministic embedding helpers used by the storage and retrieval tests (no database)."""

import ast
import hashlib
import math
import os
import subprocess
import sys
from pathlib import Path

import pytest

from tests import embeddings as emb

TESTS_DIR = Path(__file__).resolve().parents[1]


def is_unit(vector: list[float]) -> bool:
    return math.isclose(math.sqrt(sum(x * x for x in vector)), 1.0, abs_tol=1e-12)


def fingerprint(vector: list[float]) -> str:
    return hashlib.sha256(emb.to_literal(vector).encode("ascii")).hexdigest()[:16]


def test_every_helper_returns_384_finite_non_zero_vectors() -> None:
    vectors = [
        emb.basis(0),
        emb.basis(383),
        emb.negate(emb.basis(5)),
        emb.at_angle(0, 1, 45),
        emb.scaled(emb.basis(2), 0.001),
        emb.deterministic_vector(0),
        emb.deterministic_vector(12345),
    ]
    for vector in vectors:
        assert len(vector) == emb.DIM == 384
        assert all(math.isfinite(x) for x in vector)
        assert math.sqrt(sum(x * x for x in vector)) > 0


def test_basis_and_angle_vectors_are_unit_length() -> None:
    assert is_unit(emb.basis(7))
    for degrees in (0, 10, 30, 45, 60, 90, 135, 180):
        assert is_unit(emb.at_angle(0, 1, degrees))
    assert is_unit(emb.deterministic_vector(3))


@pytest.mark.parametrize(
    ("left", "right", "expected"),
    [
        (emb.basis(0), emb.basis(1), 0.0),  # orthogonal
        (emb.basis(0), emb.basis(0), 1.0),  # identical
        (emb.basis(0), emb.negate(emb.basis(0)), -1.0),  # opposite
        (emb.basis(0), emb.at_angle(0, 1, 45), math.sqrt(2) / 2),  # 45 degrees
        (emb.basis(0), emb.at_angle(0, 1, 30), math.sqrt(3) / 2),
        (emb.basis(0), emb.at_angle(0, 1, 60), 0.5),
        (emb.basis(0), emb.at_angle(0, 1, 90), 0.0),
    ],
    ids=["orthogonal", "identical", "opposite", "45deg", "30deg", "60deg", "90deg"],
)
def test_named_vectors_have_the_documented_cosine_similarity(
    left: list[float], right: list[float], expected: float
) -> None:
    assert emb.cosine_similarity(left, right) == pytest.approx(expected, abs=1e-12)


def test_cosine_similarity_ignores_magnitude() -> None:
    assert emb.cosine_similarity(emb.basis(0), emb.scaled(emb.basis(0), 250.0)) == pytest.approx(
        1.0
    )
    assert emb.cosine_similarity(emb.basis(0), emb.scaled(emb.at_angle(0, 1, 60), 1e-3)) == (
        pytest.approx(0.5)
    )


def test_deterministic_vectors_repeat_for_a_seed_and_differ_between_seeds() -> None:
    assert emb.deterministic_vector(42) == emb.deterministic_vector(42)
    assert emb.deterministic_vector(42) != emb.deterministic_vector(43)
    assert (
        abs(emb.cosine_similarity(emb.deterministic_vector(1), emb.deterministic_vector(2))) < 0.5
    )


def test_deterministic_vector_is_reproducible_across_processes() -> None:
    """Different interpreter runs (different hash seeds) must give the same bytes."""
    code = (
        "import hashlib; from tests import embeddings as e; "
        "print(hashlib.sha256(e.to_literal(e.deterministic_vector(7)).encode()).hexdigest()[:16])"
    )
    outputs = set()
    for hash_seed in ("0", "1", "random"):
        proc = subprocess.run(  # noqa: S603 - fixed arguments, no user input
            [sys.executable, "-c", code],
            capture_output=True,
            text=True,
            cwd=TESTS_DIR.parent,
            env={**os.environ, "PYTHONHASHSEED": hash_seed, "PYTHONPATH": str(TESTS_DIR.parent)},
            timeout=60,
            check=True,
        )
        outputs.add(proc.stdout.strip())
    assert outputs == {fingerprint(emb.deterministic_vector(7))}


def test_known_fingerprints_guard_against_accidental_changes() -> None:
    # Pinned values: changing the generator would silently change every fixture ranking.
    assert fingerprint(emb.deterministic_vector(7)) == emb.PINNED_FINGERPRINT_SEED_7


def test_literal_has_384_components_and_parses_back() -> None:
    literal = emb.to_literal(emb.at_angle(2, 3, 45))
    assert literal.startswith("[") and literal.endswith("]")
    parsed = [float(x) for x in literal[1:-1].split(",")]
    assert len(parsed) == 384
    assert parsed == pytest.approx(emb.at_angle(2, 3, 45))


def test_helpers_reject_out_of_range_arguments() -> None:
    with pytest.raises(ValueError, match="index"):
        emb.basis(384)
    with pytest.raises(ValueError, match="index"):
        emb.basis(-1)
    with pytest.raises(ValueError, match="different"):
        emb.at_angle(3, 3, 10)
    with pytest.raises(ValueError, match="positive"):
        emb.scaled(emb.basis(0), 0.0)


def test_the_embedding_module_uses_only_the_standard_library() -> None:
    """No model, network or third-party code is needed to build the fixtures."""
    tree = ast.parse((TESTS_DIR / "embeddings.py").read_text(encoding="utf-8"))
    imported: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            imported.update(alias.name.split(".")[0] for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module:
            imported.add(node.module.split(".")[0])
    assert imported <= {"__future__", "hashlib", "math", "struct"}, imported
