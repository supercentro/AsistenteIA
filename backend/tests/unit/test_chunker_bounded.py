"""The chunker does bounded work (review finding R-01).

A 2,000,000-character text with no separator used to be split in one piece before the chunk cap was
looked at (about 60 s of tokenizer work for a file that would be refused anyway), and the job
deadline was only checked between phases. The text is now handed to the splitter in windows, the cap
is checked after each window and a `poll` callback lets the caller stop the work.
"""

import pytest

from app.rag.chunker import (
    DEFAULT_WINDOW_CHARS,
    Page,
    TooManyChunksError,
    chunk_pages,
    split_windows,
)


class CountingCounter:
    """One token per word (two special tokens when asked); remembers how much text it measured."""

    def __init__(self) -> None:
        self.characters = 0

    def count_tokens(self, text: str, *, include_special: bool = True) -> int:
        self.characters += len(text)
        return len(text.split()) + (2 if include_special else 0)


class CharCounter:
    """One token per character: text without separators is the worst case for the splitter."""

    def __init__(self) -> None:
        self.characters = 0

    def count_tokens(self, text: str, *, include_special: bool = True) -> int:
        self.characters += len(text)
        return len(text) + (2 if include_special else 0)


# --- windows ------------------------------------------------------------------------------------


def test_a_short_text_is_one_window() -> None:
    assert list(split_windows("hola mundo", 100)) == ["hola mundo"]


def test_the_windows_rebuild_the_text_and_respect_the_limit() -> None:
    text = " ".join(f"palabra{number}" for number in range(5_000))

    windows = list(split_windows(text, 1_000))

    assert "".join(windows) == text
    assert all(0 < len(window) <= 1_000 for window in windows)
    assert len(windows) > 20


def test_a_window_ends_on_the_strongest_separator_available() -> None:
    text = ("a" * 60 + "\n\n") + ("b" * 20 + " ") + ("c" * 40)

    windows = list(split_windows(text, 100))

    assert windows[0].endswith("\n\n")


def test_text_without_any_separator_is_cut_at_the_limit() -> None:
    windows = list(split_windows("x" * 2_500, 1_000))

    assert [len(window) for window in windows] == [1_000, 1_000, 500]


def test_the_window_limit_is_validated() -> None:
    with pytest.raises(ValueError, match="window"):
        list(split_windows("text", 0))


def test_the_default_window_is_small_enough_to_bound_the_work() -> None:
    assert 1_000 <= DEFAULT_WINDOW_CHARS <= 50_000


# --- early rejection ------------------------------------------------------------------------------


def test_a_document_over_the_cap_is_rejected_without_measuring_all_the_text() -> None:
    counter = CountingCounter()
    text = "palabra " * 250_000  # 2,000,000 characters, about 2,500 chunks of 100 words

    with pytest.raises(TooManyChunksError):
        chunk_pages([Page(None, text)], counter, max_chunks=10)

    assert counter.characters < len(text) // 10


def test_text_without_separators_is_rejected_after_a_bounded_amount_of_work() -> None:
    counter = CharCounter()
    text = "a" * 400_000

    with pytest.raises(TooManyChunksError):
        chunk_pages([Page(None, text)], counter, max_chunks=50)

    # 50 chunks need about 50 x 100 characters; the work stays within a few windows, not 400,000.
    assert counter.characters < 10 * DEFAULT_WINDOW_CHARS


def test_the_cap_is_checked_before_the_next_window_is_split() -> None:
    counter = CountingCounter()
    pages = [Page(None, "palabra " * 50_000), Page(None, "otra " * 50_000)]

    with pytest.raises(TooManyChunksError):
        chunk_pages(pages, counter, max_chunks=5)

    assert counter.characters < 100_000  # the second page was never measured


# --- the deadline hook ----------------------------------------------------------------------------


def test_poll_is_called_between_windows() -> None:
    calls: list[int] = []

    chunk_pages(
        [Page(None, "palabra " * 6_000)],
        CountingCounter(),
        max_chunks=10_000,
        window_chars=5_000,
        poll=lambda: calls.append(1),
    )

    assert len(calls) >= 8  # 48,000 characters / 5,000 per window


def test_an_exception_from_poll_stops_the_work_at_once() -> None:
    counter = CountingCounter()
    state = {"calls": 0}

    class Stop(Exception):
        pass

    def poll() -> None:
        state["calls"] += 1
        if state["calls"] == 3:
            raise Stop

    with pytest.raises(Stop):
        chunk_pages(
            [Page(None, "palabra " * 100_000)],
            counter,
            max_chunks=100_000,
            window_chars=5_000,
            poll=poll,
        )

    assert counter.characters < 60_000  # two windows of 5,000 characters, measured a few times
    assert state["calls"] == 3


# --- what must not change -------------------------------------------------------------------------


def test_a_page_inside_one_window_is_chunked_exactly_as_before() -> None:
    text = " ".join(f"palabra{number}" for number in range(700))
    page = [Page(3, text)]

    assert chunk_pages(page, CountingCounter()) == chunk_pages(
        page, CountingCounter(), window_chars=10_000_000
    )


def test_a_long_valid_document_is_covered_without_gaps_and_keeps_the_size() -> None:
    vocabulary = [f"w{number}" for number in range(30_000)]
    text = " ".join(vocabulary)

    chunks = chunk_pages(
        [Page(None, text)], CountingCounter(), max_chunks=2_000, window_chars=5_000
    )

    seen = {word for chunk in chunks for word in chunk.text.split()}
    assert seen == set(vocabulary)
    assert all(len(chunk.text.split()) <= 100 for chunk in chunks)
    assert [chunk.index for chunk in chunks] == list(range(len(chunks)))
    assert 300 <= len(chunks) <= 400  # 30,000 words / about 80-100 words per chunk


def test_a_valid_long_document_below_the_cap_is_accepted_with_the_default_window() -> None:
    text = " ".join(f"w{number}" for number in range(90_000))  # about 600,000 characters

    chunks = chunk_pages([Page(None, text)], CountingCounter(), max_chunks=2_000)

    assert 900 <= len(chunks) <= 1_200


def test_page_numbers_survive_the_windows() -> None:
    pages = [Page(1, "palabra " * 4_000), Page(2, "otra " * 4_000)]

    chunks = chunk_pages(pages, CountingCounter(), max_chunks=10_000, window_chars=3_000)

    numbers = [chunk.page_number or 0 for chunk in chunks]
    assert numbers == sorted(numbers)
    assert set(numbers) == {1, 2}
