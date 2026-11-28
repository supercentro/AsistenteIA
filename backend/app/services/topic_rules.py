"""What a write of the topics of a document does (change `frequent-questions-and-topics`, D4, D5).

Pure: the stored set, the requested topics and the highest page with text go in; the plan comes
out. The rule that protects students is here: after the first set, any change of page ranges moves
the marker, so the figures of the document only count weeks that start after the change and two
reads under different ranges cannot be subtracted. A change of titles alone moves nothing.
"""

from collections.abc import Sequence
from dataclasses import dataclass

from app.models.topic import TopicSource


@dataclass(frozen=True)
class Topic:
    title: str
    start_page: int
    end_page: int


@dataclass(frozen=True)
class CurrentSet:
    source: TopicSource
    revision: int
    topics: tuple[Topic, ...]


@dataclass(frozen=True)
class Plan:
    creates: bool
    source: TopicSource
    revision: int
    moves_marker: bool
    topics: tuple[Topic, ...]


class StaleRevision(Exception):
    """The write was based on another revision than the stored one."""


class InvalidDefinition(Exception):
    """The requested topics break a rule; `reason` is a fixed value, never input text."""

    def __init__(self, reason: str) -> None:
        super().__init__(reason)
        self.reason = reason


def _ranges(topics: Sequence[Topic]) -> list[tuple[int, int]]:
    return sorted((topic.start_page, topic.end_page) for topic in topics)


def _check(topics: Sequence[Topic], last_page: int) -> None:
    if any(not 1 <= t.start_page <= t.end_page <= last_page for t in topics):
        raise InvalidDefinition("page_range")
    ranges = _ranges(topics)
    if any(later[0] <= earlier[1] for earlier, later in zip(ranges, ranges[1:], strict=False)):
        raise InvalidDefinition("overlap")


def plan_change(
    current: CurrentSet | None, revision: int, requested: Sequence[Topic], last_page: int
) -> Plan | None:
    """The change to apply, or `None` when the write would change nothing."""
    if revision != (current.revision if current else 0):
        raise StaleRevision
    ordered = tuple(sorted(requested, key=lambda t: t.start_page))
    if current is None:
        if not ordered:
            return None
        _check(ordered, last_page)
        return Plan(True, TopicSource.TEACHER, 1, False, ordered)
    if _ranges(ordered) == _ranges(current.topics):
        # A rename: the unchanged ranges were valid when stored, shared bookmark pages included.
        if ordered == current.topics:
            return None
        return Plan(False, current.source, current.revision + 1, False, ordered)
    _check(ordered, last_page)
    return Plan(False, TopicSource.TEACHER, current.revision + 1, True, ordered)
