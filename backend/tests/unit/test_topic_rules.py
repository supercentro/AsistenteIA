"""What a write of the topics of a document does (change `frequent-questions-and-topics`, D4, D5).

The decision is pure: what is stored today, what is requested and the highest page with text.
"""

import uuid
from datetime import UTC, date, datetime

import pytest
from pydantic import ValidationError

from app.models.topic import TopicSource
from app.schemas.topic import DocumentTopicsUpdate, TopicEntry
from app.services.activity_service import first_week_after
from app.services.topic_rules import (
    CurrentSet,
    InvalidDefinition,
    StaleRevision,
    Topic,
    plan_change,
)

LAST = 10


def topic(title: str, start: int, end: int) -> Topic:
    return Topic(title=title, start_page=start, end_page=end)


def stored(*topics: Topic, source: TopicSource = TopicSource.TEACHER, revision: int = 3):  # type: ignore[no-untyped-def]
    return CurrentSet(source=source, revision=revision, topics=tuple(topics))


# --- the first set ----------------------------------------------------------------------------


def test_the_first_set_is_created_without_moving_the_marker() -> None:
    plan = plan_change(None, 0, [topic("B", 4, 6), topic("A", 1, 3)], LAST)

    assert plan is not None and plan.creates and not plan.moves_marker
    assert plan.source is TopicSource.TEACHER and plan.revision == 1
    assert [t.title for t in plan.topics] == ["A", "B"]  # ordered by page


def test_an_empty_first_set_does_nothing() -> None:
    assert plan_change(None, 0, [], LAST) is None


def test_gaps_and_a_single_page_are_allowed() -> None:
    plan = plan_change(None, 0, [topic("A", 2, 2), topic("B", 9, 10)], LAST)

    assert plan is not None and len(plan.topics) == 2


@pytest.mark.parametrize(
    ("topics", "reason"),
    [
        ([topic("A", 1, 5), topic("B", 5, 8)], "overlap"),
        ([topic("A", 1, 5), topic("B", 2, 3)], "overlap"),
        ([topic("A", 1, 5), topic("B", 1, 5)], "overlap"),
        ([topic("A", 3, 2)], "page_range"),
        ([topic("A", 1, LAST + 1)], "page_range"),
        ([topic("A", 0, 1)], "page_range"),
    ],
)
def test_an_invalid_set_is_refused_with_its_reason(topics: list[Topic], reason: str) -> None:
    with pytest.raises(InvalidDefinition) as refused:
        plan_change(None, 0, topics, LAST)

    assert refused.value.reason == reason


# --- later writes -----------------------------------------------------------------------------


@pytest.mark.parametrize("revision", [0, 2, 4])
def test_a_write_on_another_revision_is_stale(revision: int) -> None:
    with pytest.raises(StaleRevision):
        plan_change(stored(topic("A", 1, 5)), revision, [topic("A", 1, 4)], LAST)


def test_a_first_write_that_names_a_revision_is_stale() -> None:
    with pytest.raises(StaleRevision):
        plan_change(None, 1, [topic("A", 1, 4)], LAST)


def test_changing_only_titles_is_a_rename() -> None:
    current = stored(topic("Normalizacion", 1, 5), source=TopicSource.BOOKMARKS)

    plan = plan_change(current, 3, [topic("Normalización", 1, 5)], LAST)

    assert plan is not None and not plan.moves_marker and not plan.creates
    assert plan.source is TopicSource.BOOKMARKS and plan.revision == 4


def test_a_rename_keeps_shared_ranges_of_bookmarks() -> None:
    current = stored(topic("A", 4, 6), topic("B", 4, 6), source=TopicSource.BOOKMARKS)

    plan = plan_change(current, 3, [topic("A2", 4, 6), topic("B", 4, 6)], LAST)

    assert plan is not None and not plan.moves_marker


def test_an_identical_write_does_nothing() -> None:
    assert plan_change(stored(topic("A", 1, 5)), 3, [topic("A", 1, 5)], LAST) is None
    assert plan_change(stored(), 3, [], LAST) is None


@pytest.mark.parametrize(
    "requested",
    [
        [topic("A", 1, 4), topic("B", 6, 8)],  # moved boundary
        [topic("A", 1, 5)],  # removed
        [topic("A", 1, 5), topic("B", 6, 8), topic("C", 9, 9)],  # added
        [topic("A", 1, 8)],  # merged
        [],  # cleared
    ],
)
def test_any_change_of_ranges_moves_the_marker(requested: list[Topic]) -> None:
    current = stored(topic("A", 1, 5), topic("B", 6, 8), source=TopicSource.BOOKMARKS)

    plan = plan_change(current, 3, requested, LAST)

    assert plan is not None and plan.moves_marker
    assert plan.source is TopicSource.TEACHER and plan.revision == 4


def test_defining_again_after_clearing_moves_the_marker() -> None:
    plan = plan_change(stored(), 3, [topic("A", 1, 5)], LAST)

    assert plan is not None and plan.moves_marker and not plan.creates


def test_changed_ranges_may_not_overlap_even_if_one_was_shared_before() -> None:
    current = stored(topic("A", 4, 6), topic("B", 4, 6))

    with pytest.raises(InvalidDefinition):
        plan_change(current, 3, [topic("A", 4, 6), topic("B", 4, 6), topic("C", 8, 8)], LAST)


# --- the counting start -----------------------------------------------------------------------


@pytest.mark.parametrize(
    ("moved", "expected"),
    [
        (datetime(2026, 3, 2, 0, 0, tzinfo=UTC), date(2026, 3, 9)),  # Monday midnight
        (datetime(2026, 3, 8, 23, 59, 59, tzinfo=UTC), date(2026, 3, 9)),  # Sunday night
        (datetime(2026, 3, 5, 12, 0, tzinfo=UTC), date(2026, 3, 9)),
    ],
)
def test_counting_restarts_on_the_monday_after_the_week_of_the_change(
    moved: datetime, expected: date
) -> None:
    assert first_week_after(moved) == expected


# --- the request body -------------------------------------------------------------------------


def body(**topic_fields: object) -> dict[str, object]:
    entry: dict[str, object] = {"title": "A", "start_page": 1, "end_page": 2}
    entry.update(topic_fields)
    return {"revision": 0, "topics": [entry]}


def test_the_title_is_trimmed_and_its_spaces_collapsed() -> None:
    parsed = DocumentTopicsUpdate.model_validate(body(title="  Formas   normales  "))

    assert parsed.topics[0].title == "Formas normales"


@pytest.mark.parametrize(
    "fields",
    [
        {"title": ""},
        {"title": "   "},
        {"title": "a" * 201},
        {"title": "a" * 100_000},
        {"title": "line\nbreak"},
        {"title": "tab\there"},
        {"title": "nul\x00"},
        {"title": "rtl‮over"},
        {"title": "sep arator"},
        {"title": "lone\ud800"},
        {"title": 5},
        {"start_page": "1"},
        {"start_page": 1.5},
        {"start_page": True},
        {"start_page": 0},
        {"end_page": -3},
        {"end_page": 10**30},
        {"document_id": str(uuid.uuid4())},
    ],
)
def test_the_body_refuses_hostile_or_loose_values(fields: dict[str, object]) -> None:
    with pytest.raises(ValidationError):
        DocumentTopicsUpdate.model_validate(body(**fields))


@pytest.mark.parametrize(
    "payload",
    [
        {"topics": []},
        {"revision": -1, "topics": []},
        {"revision": "0", "topics": []},
        {"revision": 0},
        {"revision": 0, "topics": None},
        {"revision": 0, "topics": [], "source": "bookmarks"},
        {"revision": 0, "topics": [{"title": "A", "start_page": 1, "end_page": 1}] * 101},
    ],
)
def test_the_body_refuses_missing_extra_or_oversized_input(payload: dict[str, object]) -> None:
    with pytest.raises(ValidationError):
        DocumentTopicsUpdate.model_validate(payload)


@pytest.mark.parametrize(
    "title", ["\u200b", "\ufeff\u00ad", "\u2800", "\u3164 \u115f", "\uffa0", "\u0301"]
)
def test_a_title_that_shows_nothing_is_refused(title: str) -> None:
    with pytest.raises(ValidationError):
        TopicEntry(title=title, start_page=1, end_page=2)


@pytest.mark.parametrize("title", ["A\u200b", "\u0915\u094d\u200d\u0937", "3NF", "\u00bf?"])
def test_a_title_with_something_to_show_is_kept(title: str) -> None:
    assert TopicEntry(title=title, start_page=1, end_page=2).title == title
