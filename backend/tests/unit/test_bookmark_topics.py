"""Topics from the bookmarks of a PDF (change `frequent-questions-and-topics`, D8), any system.

The child's walk of the outline runs in-process with a stand-in reader, the parent's parsing of the
child protocol and the title and range rules are pure. The real child is covered on Linux in
`test_pdf_outline.py`.
"""

import io
import json
import sys
import types
from dataclasses import dataclass
from typing import Any

import pytest

from app.rag import pdf_child
from app.rag.loaders import DocumentLoadError, OutlineEntry, parse_outline
from app.services.bookmark_topics import bookmark_topics
from app.services.topic_rules import Topic


@dataclass
class Item:
    title: Any
    page: int | None  # zero-based page index, None when it cannot be resolved


class Reader:
    outline: list[Any] = []
    pages = [None] * 50

    def get_destination_page_number(self, item: Item) -> int | None:
        if item.page == -99:
            raise KeyError("broken destination")
        return item.page


def walk(outline: list[Any], monkeypatch: pytest.MonkeyPatch) -> list[dict[str, Any]]:
    reader = Reader()
    reader.outline = outline
    buffer = io.BytesIO()
    monkeypatch.setattr(sys, "stdout", types.SimpleNamespace(buffer=buffer))
    pdf_child._write_outline(reader)
    return [json.loads(line) for line in buffer.getvalue().decode("utf-8").splitlines()]


def entries(records: list[dict[str, Any]]) -> list[tuple[str, int]]:
    assert records[-1] == {"end": True}
    return [(r["title"], r["page"]) for r in records[:-1]]


# --- the child ----------------------------------------------------------------------------------


def test_the_top_level_is_used_when_it_has_two_entries(monkeypatch: pytest.MonkeyPatch) -> None:
    outline = [Item("Uno", 0), [Item("Sub", 1)], Item("Dos", 4)]

    assert entries(walk(outline, monkeypatch)) == [("Uno", 1), ("Dos", 5)]


def test_a_single_root_gives_its_children(monkeypatch: pytest.MonkeyPatch) -> None:
    outline = [Item("Libro", 0), [Item("Uno", 1), Item("Dos", 2)]]

    assert entries(walk(outline, monkeypatch)) == [("Uno", 2), ("Dos", 3)]


@pytest.mark.parametrize("outline", [[], [Item("Solo", 0)]])
def test_no_or_one_entry_gives_that_much(
    monkeypatch: pytest.MonkeyPatch, outline: list[Any]
) -> None:
    assert len(entries(walk(outline, monkeypatch))) == len(outline)


def test_more_than_a_hundred_entries_give_none(monkeypatch: pytest.MonkeyPatch) -> None:
    outline = [Item(f"T{n}", n % 10) for n in range(101)]

    assert entries(walk(outline, monkeypatch)) == []


def test_unresolvable_destinations_are_skipped(monkeypatch: pytest.MonkeyPatch) -> None:
    outline = [Item("Rota", -99), Item("Sin pagina", None), Item("Buena", 2), Item(None, 3)]

    assert entries(walk(outline, monkeypatch)) == [("Buena", 3)]


def test_titles_are_cut_and_surrogates_removed_by_the_child(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    outline = [Item("x" * 10_000, 0), Item("a\ud800b", 1)]

    found = entries(walk(outline, monkeypatch))

    assert [len(found[0][0]), found[1][0]] == [1000, "ab"]


# --- the parent ---------------------------------------------------------------------------------


def lines(*records: object) -> bytes:
    return b"".join(json.dumps(r).encode() + b"\n" for r in records)


def test_the_parent_reads_a_complete_stream() -> None:
    output = lines({"title": "Uno", "page": 1}, {"end": True})

    assert parse_outline(output, 0) == [OutlineEntry("Uno", 1)]


@pytest.mark.parametrize(
    ("output", "returncode"),
    [
        (lines({"title": "Uno", "page": 1}), 0),  # no end
        (lines({"end": True}), 1),
        (lines({"title": "Uno", "page": 0}, {"end": True}), 0),
        (lines({"title": "Uno", "page": "1"}, {"end": True}), 0),
        (lines({"title": "Uno", "page": True}, {"end": True}), 0),
        (lines({"title": 4, "page": 1}, {"end": True}), 0),
        (lines({"title": "Uno", "page": 1, "x": 1}, {"end": True}), 0),
        (lines({"end": True}, {"title": "Uno", "page": 1}), 0),
        (lines({"error": "CORRUPT_FILE"}), 1),
        (lines(*({"title": "t", "page": 1} for _ in range(101)), {"end": True}), 0),
        (b"not json\n", 0),
        (b"[1]\n", 0),
    ],
)
def test_the_parent_refuses_anything_else(output: bytes, returncode: int) -> None:
    with pytest.raises(DocumentLoadError):
        parse_outline(output, returncode)


# --- titles and ranges --------------------------------------------------------------------------


def entry(title: str, page: int) -> OutlineEntry:
    return OutlineEntry(title, page)


def test_each_topic_ends_before_the_next_start_and_the_last_at_the_end() -> None:
    topics = bookmark_topics([entry("B", 5), entry("A", 2)], last_page=9)

    assert topics == [Topic("A", 2, 4), Topic("B", 5, 9)]


def test_entries_on_one_page_share_the_range() -> None:
    topics = bookmark_topics([entry("A", 4), entry("B", 4), entry("C", 7)], last_page=8)

    assert topics == [Topic("A", 4, 6), Topic("B", 4, 6), Topic("C", 7, 8)]


def test_entries_after_the_last_page_with_text_are_dropped() -> None:
    topics = bookmark_topics([entry("A", 1), entry("B", 3), entry("C", 9)], last_page=5)

    assert topics == [Topic("A", 1, 2), Topic("B", 3, 5)]


def test_titles_are_cleaned_collapsed_and_cut() -> None:
    hostile = "  <b>Formas</b>\n\tnormales\x00‮  "

    topics = bookmark_topics([entry(hostile, 1), entry("y" * 300, 2)], last_page=3)

    assert topics[0].title == "<b>Formas</b> normales"
    assert len(topics[1].title) == 200


@pytest.mark.parametrize(
    "found",
    [
        [],
        [entry("Solo", 1)],
        [entry("A", 1), entry("\x00‮  ", 2)],  # one usable
        [entry("A", 1), entry("B", 30)],  # one inside the pages with text
    ],
)
def test_fewer_than_two_usable_entries_give_no_topics(found: list[OutlineEntry]) -> None:
    assert bookmark_topics(found, last_page=10) == []


def test_no_pages_with_text_gives_no_topics() -> None:
    assert bookmark_topics([entry("A", 1), entry("B", 2)], last_page=0) == []


def test_a_bookmark_that_shows_nothing_is_dropped() -> None:
    entries = [OutlineEntry("Uno", 1), OutlineEntry("\u200b\u2800", 3), OutlineEntry("Dos", 5)]

    assert [t.title for t in bookmark_topics(entries, last_page=8)] == ["Uno", "Dos"]
