"""Validation of embeddings and search limits (design D8), shared with the ingestion of change 6.

The reliable norm range is justified by `reports/2026-10-28-magnitude-experiment.md`: pgvector 0.8.7
returns NaN or silently wrong cosine distances for extreme magnitudes. The same range is enforced
in the database by the check `vector_norm(embedding) BETWEEN 1e-6 AND 1e6`. Inputs are neither
normalised nor rescaled. Error messages are fixed text: they never contain a component or a count.
"""

import math
import struct
import uuid
from collections.abc import Sequence

EMBEDDING_DIMENSIONS = 384
MIN_NORM = 1e-6
MAX_NORM = 1e6
MIN_TOP_K = 1
MAX_TOP_K = 50


class InvalidSearchInputError(ValueError):
    """Controlled domain error for an unusable query embedding or limit (no values in the text)."""

    def __init__(self, reason: str) -> None:
        super().__init__(f"invalid search input: {reason}")
        self.reason = reason


def validate_embedding(embedding: Sequence[float]) -> list[float]:
    """Return the embedding as a list of floats, or raise `InvalidSearchInputError`.

    Requires exactly `EMBEDDING_DIMENSIONS` real, finite numbers (booleans are not accepted) whose
    Euclidean norm lies within `[MIN_NORM, MAX_NORM]`. The norm is that of the single-precision
    values the database stores (`vector` keeps float32 components), accumulated in double
    precision as `vector_norm` does, so the helper and the CHECK constraint agree (finding F5).
    """
    if isinstance(embedding, str | bytes) or not isinstance(embedding, Sequence):
        raise InvalidSearchInputError("the embedding must be a sequence of numbers")
    if len(embedding) != EMBEDDING_DIMENSIONS:
        raise InvalidSearchInputError("the embedding has the wrong dimension")
    values: list[float] = []
    stored: list[
        float
    ] = []  # the same numbers rounded to single precision, as the database keeps them
    for item in embedding:
        if len(values) >= EMBEDDING_DIMENSIONS:  # the declared length cannot be trusted alone
            raise InvalidSearchInputError("the embedding has the wrong dimension")
        if isinstance(item, bool) or not isinstance(item, int | float):
            raise InvalidSearchInputError("the embedding must contain only real numbers")
        try:
            number = float(item)
        except (OverflowError, TypeError, ValueError):  # too large for a double, or a broken type
            raise InvalidSearchInputError(
                "the embedding must contain only finite numbers"
            ) from None
        if not math.isfinite(number):
            raise InvalidSearchInputError("the embedding must contain only finite numbers")
        try:
            stored.append(struct.unpack("<f", struct.pack("<f", number))[0])
        except OverflowError:  # beyond the largest single-precision number: the database refuses it
            raise InvalidSearchInputError(
                "the embedding magnitude is outside the supported range"
            ) from None
        values.append(number)
    if len(values) != EMBEDDING_DIMENSIONS:
        raise InvalidSearchInputError("the embedding has the wrong dimension")
    norm = math.hypot(*stored)  # overflow-safe, double precision
    if not (MIN_NORM <= norm <= MAX_NORM):
        raise InvalidSearchInputError("the embedding magnitude is outside the supported range")
    return values


def validate_top_k(top_k: int) -> int:
    """Return `top_k` if it is an integer between `MIN_TOP_K` and `MAX_TOP_K`."""
    if isinstance(top_k, bool) or not isinstance(top_k, int):
        raise InvalidSearchInputError("the limit must be an integer")
    if not MIN_TOP_K <= top_k <= MAX_TOP_K:
        raise InvalidSearchInputError("the limit is outside the supported range")
    return top_k


def validate_subject_id(subject_id: uuid.UUID) -> uuid.UUID:
    """Return `subject_id` if it is a `uuid.UUID`; anything else is rejected without echoing it."""
    if not isinstance(subject_id, uuid.UUID):
        raise InvalidSearchInputError("the subject id must be a UUID")
    return subject_id
