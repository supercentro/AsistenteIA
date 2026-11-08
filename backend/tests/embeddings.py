"""Deterministic 384-dimension embeddings for tests: standard library only, no model, no network.

Named vectors have a cosine similarity that can be derived by hand, so retrieval tests can assert
exact rankings. Everything is a pure function of its arguments and identical across runs.
"""

import hashlib
import math
import struct

DIM = 384

# Pinned so that an accidental change of the generator (which would silently change fixture
# rankings) fails a test. Recompute only when the generator is changed on purpose.
PINNED_FINGERPRINT_SEED_7 = "051e44ae9f471e7f"

_SNAP = 1e-15  # trigonometric rounding noise (cos 90 degrees = 6e-17) is snapped to zero


def _check_index(index: int) -> None:
    if not 0 <= index < DIM:
        raise ValueError(f"index must be between 0 and {DIM - 1}")


def basis(index: int) -> list[float]:
    """Unit vector along one axis."""
    _check_index(index)
    values = [0.0] * DIM
    values[index] = 1.0
    return values


def negate(vector: list[float]) -> list[float]:
    return [-x if x != 0.0 else 0.0 for x in vector]


def scaled(vector: list[float], factor: float) -> list[float]:
    if not factor > 0.0:
        raise ValueError("factor must be positive")
    return [x * factor for x in vector]


def at_angle(first: int, second: int, degrees: float) -> list[float]:
    """Unit vector in the plane of two axes, `degrees` away from the first axis."""
    _check_index(first)
    _check_index(second)
    if first == second:
        raise ValueError("axes must be different")
    radians = math.radians(degrees)
    values = [0.0] * DIM
    for axis, component in ((first, math.cos(radians)), (second, math.sin(radians))):
        values[axis] = 0.0 if abs(component) < _SNAP else component
    return values


def deterministic_vector(seed: int) -> list[float]:
    """Pseudo-random unit vector derived from SHA-256 blocks of the seed (stable across runs)."""
    raw: list[float] = []
    counter = 0
    while len(raw) < DIM:
        digest = hashlib.sha256(f"fixture-embedding:{seed}:{counter}".encode("ascii")).digest()
        for (word,) in struct.iter_unpack(">I", digest):
            raw.append(word / 2**32 * 2.0 - 1.0)
        counter += 1
    raw = raw[:DIM]
    norm = math.sqrt(math.fsum(x * x for x in raw))
    return [x / norm for x in raw]


def cosine_similarity(left: list[float], right: list[float]) -> float:
    dot = math.fsum(a * b for a, b in zip(left, right, strict=True))
    norms = math.sqrt(math.fsum(a * a for a in left)) * math.sqrt(math.fsum(b * b for b in right))
    return dot / norms


def to_literal(vector: list[float]) -> str:
    """pgvector text input: `[x1,x2,...]`."""
    return "[" + ",".join(repr(x) for x in vector) + "]"
