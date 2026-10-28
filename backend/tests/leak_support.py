"""Helpers for the data-leak tests (spike incident I2), reusable by later changes.

PostgreSQL puts the failing row (text and part of the embedding) into the DETAIL of a constraint
violation. These helpers produce *real* SQL exceptions carrying such data and capture every log
record, so tests can prove the application never forwards that text.
"""

import logging
from collections.abc import Callable, Iterator
from contextlib import contextmanager
from dataclasses import dataclass, field

from tests.sql_support import (
    DIM,
    insert_chunk,
    run,
    seed_basic,
    unit_vector,
    vector_literal,
)

CONTENT_MARKER = "LEAKMARKER-7731-course-text"
# First component of the out-of-range embedding below, as PostgreSQL prints it in the row DETAIL.
EMBEDDING_MARKER = "1.2345675e+06"  # how PostgreSQL prints the component 1234567.5
ROW_DETAIL_MARKER = "Failing row contains"


def out_of_range_embedding() -> str:
    values = [0.0] * DIM
    values[0] = 1234567.5  # norm > 1e6: violates the norm-range check
    return vector_literal(values)


@dataclass(frozen=True)
class Violation:
    """A statement that fails in the database in a specific way."""

    name: str
    execute: Callable[[], None]


def build_violations(url: str) -> list[Violation]:
    seed = seed_basic(url)
    insert_chunk(url, seed.document_id, seed.subject_id, chunk_index=0, embedding=unit_vector(1))
    other_subject_id = seed.document_id  # any uuid that is not the document's subject

    def check_violation() -> None:
        insert_chunk(
            url,
            seed.document_id,
            seed.subject_id,
            chunk_index=1,
            content=CONTENT_MARKER,
            embedding=out_of_range_embedding(),
        )

    def foreign_key_violation() -> None:
        insert_chunk(
            url,
            seed.document_id,
            other_subject_id,
            chunk_index=2,
            content=CONTENT_MARKER,
            embedding=unit_vector(2),
        )

    def unique_violation() -> None:
        insert_chunk(
            url,
            seed.document_id,
            seed.subject_id,
            chunk_index=0,
            content=CONTENT_MARKER,
            embedding=unit_vector(3),
        )

    def wrong_dimension() -> None:
        insert_chunk(
            url,
            seed.document_id,
            seed.subject_id,
            chunk_index=3,
            content=CONTENT_MARKER,
            embedding=vector_literal([0.5] * (DIM - 1)),
        )

    def blank_content() -> None:
        insert_chunk(
            url,
            seed.document_id,
            seed.subject_id,
            chunk_index=4,
            content="   ",
            embedding=unit_vector(4),
        )

    def statement_with_marker_parameter() -> None:
        run(url, "SELECT CAST(:v AS integer)", v=CONTENT_MARKER)

    return [
        Violation("check_violation", check_violation),
        Violation("foreign_key_violation", foreign_key_violation),
        Violation("unique_violation", unique_violation),
        Violation("wrong_dimension", wrong_dimension),
        Violation("blank_content", blank_content),
        Violation("bad_parameter", statement_with_marker_parameter),
    ]


@dataclass
class LogSpy:
    """Collects the formatted text (message and traceback) of every record on the root logger."""

    chunks: list[str] = field(default_factory=list)

    @property
    def text(self) -> str:
        return "\n".join(self.chunks)


@contextmanager
def spy_on_logs() -> Iterator[LogSpy]:
    spy = LogSpy()

    class Capture(logging.Handler):
        def emit(self, record: logging.LogRecord) -> None:
            spy.chunks.append(self.format(record))

    handler = Capture(level=logging.NOTSET)
    root = logging.getLogger()
    previous_level = root.level
    root.addHandler(handler)
    root.setLevel(logging.DEBUG)
    try:
        yield spy
    finally:
        root.removeHandler(handler)
        root.setLevel(previous_level)
