"""Token-based chunking with a fake counter (group 5, task 5.3).

The fake counter counts words, so the sizes are exact and the tests do not need the model. The real
tokenizer is exercised by `test_chunker_realmodel.py` (marker `realmodel`).
"""

import pytest

from app.rag.chunker import (
    Chunk,
    ChunkTooLongError,
    Page,
    TooManyChunksError,
    chunk_pages,
)

SPECIAL_TOKENS = 2


class WordCounter:
    """One token per word, plus two special tokens when asked."""

    def __init__(self) -> None:
        self.calls = 0

    def count_tokens(self, text: str, *, include_special: bool = True) -> int:
        self.calls += 1
        return len(text.split()) + (SPECIAL_TOKENS if include_special else 0)


class GreedyCounter:
    """Under-reports without special tokens: a chunk of 100 words measures 202 with them."""

    def count_tokens(self, text: str, *, include_special: bool = True) -> int:
        words = len(text.split())
        return words * 2 + SPECIAL_TOKENS if include_special else words


class CharCounter:
    """One token per character: a long word cannot be split on spaces."""

    def count_tokens(self, text: str, *, include_special: bool = True) -> int:
        return len(text) + (SPECIAL_TOKENS if include_special else 0)


def words(prefix: str, count: int) -> str:
    return " ".join(f"{prefix}{number}" for number in range(count))


def test_a_short_page_is_one_chunk() -> None:
    chunks = chunk_pages([Page(1, "una pagina corta")], WordCounter())

    assert chunks == [Chunk(index=0, page_number=1, text="una pagina corta")]


def test_chunks_respect_the_size_of_100_tokens() -> None:
    counter = WordCounter()

    chunks = chunk_pages([Page(None, words("w", 1000))], counter)

    assert len(chunks) > 10
    assert all(counter.count_tokens(c.text, include_special=False) <= 100 for c in chunks)
    assert max(counter.count_tokens(c.text, include_special=False) for c in chunks) >= 90


def test_consecutive_chunks_overlap_by_about_20_tokens() -> None:
    chunks = chunk_pages([Page(None, words("w", 600))], WordCounter())

    for before, after in zip(chunks, chunks[1:], strict=False):
        shared = set(before.text.split()) & set(after.text.split())
        assert 1 <= len(shared) <= 20, (len(shared), before.index)
    assert len(set(chunks[0].text.split()) & set(chunks[1].text.split())) >= 10


def test_the_text_is_covered_without_gaps() -> None:
    original = words("w", 750)

    chunks = chunk_pages([Page(None, original)], WordCounter())

    seen = {word for chunk in chunks for word in chunk.text.split()}
    assert seen == set(original.split())


def test_indexes_are_global_and_consecutive_across_pages() -> None:
    pages = [Page(1, words("a", 250)), Page(2, words("b", 250)), Page(3, words("c", 250))]

    chunks = chunk_pages(pages, WordCounter())

    assert [c.index for c in chunks] == list(range(len(chunks)))


def test_a_chunk_never_crosses_a_page_and_keeps_its_page_number() -> None:
    pages = [Page(1, words("a", 250)), Page(7, words("b", 250)), Page(8, words("c", 90))]

    chunks = chunk_pages(pages, WordCounter())

    assert {c.page_number for c in chunks} == {1, 7, 8}
    for chunk in chunks:
        prefixes = {word[0] for word in chunk.text.split()}
        assert len(prefixes) == 1
        assert {"a": 1, "b": 7, "c": 8}[next(iter(prefixes))] == chunk.page_number
    assert [c.page_number for c in chunks] == sorted(c.page_number or 0 for c in chunks)


def test_a_page_of_three_chunks_gives_three_chunks_with_the_same_page_number() -> None:
    chunks = chunk_pages([Page(7, words("w", 220))], WordCounter())

    assert len(chunks) == 3
    assert [(c.index, c.page_number) for c in chunks] == [(0, 7), (1, 7), (2, 7)]


def test_text_pages_have_no_page_number() -> None:
    chunks = chunk_pages([Page(None, words("w", 150))], WordCounter())

    assert all(c.page_number is None for c in chunks)


@pytest.mark.parametrize("blank", ["", "   ", "\n\n", "\u00a0\x85", "\u200b"])
def test_blank_pages_are_skipped(blank: str) -> None:
    pages = [Page(1, "primera"), Page(2, blank), Page(3, "tercera")]

    chunks = chunk_pages(pages, WordCounter())

    assert [(c.index, c.page_number, c.text) for c in chunks] == [
        (0, 1, "primera"),
        (1, 3, "tercera"),
    ]


def test_a_document_of_only_blank_pages_has_no_chunks() -> None:
    assert chunk_pages([Page(1, ""), Page(2, "\u00a0")], WordCounter()) == []


def test_no_chunk_is_blank_looking() -> None:
    text = "alfa beta\n\n\u200b\n\ngamma delta"

    chunks = chunk_pages([Page(None, text)], WordCounter())

    assert chunks
    assert all(any(ch.isalnum() for ch in c.text) for c in chunks)


def test_paragraph_boundaries_are_preferred() -> None:
    first = words("p", 60)
    second = words("q", 60)

    chunks = chunk_pages([Page(None, f"{first}\n\n{second}")], WordCounter())

    assert [c.text for c in chunks] == [first, second]


def test_exactly_the_cap_of_chunks_is_accepted() -> None:
    pages = [Page(number, f"pagina {number}") for number in range(1, 6)]

    chunks = chunk_pages(pages, WordCounter(), max_chunks=5)

    assert len(chunks) == 5


def test_more_than_the_cap_of_chunks_fails_before_the_rest_is_split() -> None:
    counter = WordCounter()
    pages = [Page(number, f"pagina {number}") for number in range(1, 200)]

    with pytest.raises(TooManyChunksError):
        chunk_pages(pages, counter, max_chunks=5)

    assert counter.calls < 100  # stopped early, did not measure all 199 pages


def test_the_default_cap_is_2000_chunks() -> None:
    pages = [Page(number, f"p{number}") for number in range(1, 2002)]

    with pytest.raises(TooManyChunksError):
        chunk_pages(pages, WordCounter())

    assert len(chunk_pages(pages[:2000], WordCounter())) == 2000


def test_the_error_messages_are_fixed_text() -> None:
    with pytest.raises(TooManyChunksError) as exc:
        chunk_pages([Page(1, "secretoXYZ uno"), Page(2, "dos")], WordCounter(), max_chunks=1)

    assert "secretoXYZ" not in str(exc.value)


def test_the_runtime_guard_resplits_chunks_above_128_tokens_with_special_tokens() -> None:
    counter = GreedyCounter()

    chunks = chunk_pages([Page(1, words("w", 400))], counter)

    assert chunks
    assert all(counter.count_tokens(c.text, include_special=True) <= 128 for c in chunks)
    assert {word for c in chunks for word in c.text.split()} == set(words("w", 400).split())
    assert [c.index for c in chunks] == list(range(len(chunks)))


def test_the_guard_does_not_touch_chunks_that_already_fit() -> None:
    chunks = chunk_pages([Page(1, words("w", 400))], WordCounter())

    assert max(WordCounter().count_tokens(c.text) for c in chunks) <= 102


def test_a_very_long_word_is_split_by_characters_to_fit() -> None:
    counter = CharCounter()

    chunks = chunk_pages([Page(None, "x" * 1000)], counter, size=100, overlap=20)

    assert all(counter.count_tokens(c.text, include_special=True) <= 128 for c in chunks)
    assert "".join(c.text for c in chunks).count("x") >= 1000


def test_an_unsplittable_chunk_fails_with_a_controlled_error() -> None:
    class Hostile:
        def count_tokens(self, text: str, *, include_special: bool = True) -> int:
            return 0 if not include_special else 10_000

    with pytest.raises(ChunkTooLongError) as exc:
        chunk_pages([Page(1, "unico")], Hostile())

    assert "unico" not in str(exc.value)


def test_size_and_overlap_are_validated() -> None:
    with pytest.raises(ValueError, match="overlap"):
        chunk_pages([Page(1, "a")], WordCounter(), size=10, overlap=10)
    with pytest.raises(ValueError, match="size"):
        chunk_pages([Page(1, "a")], WordCounter(), size=0, overlap=0)


def test_chunks_are_immutable_values() -> None:
    chunk = Chunk(index=0, page_number=1, text="x")

    with pytest.raises(AttributeError):
        chunk.text = "y"  # type: ignore[misc]


class LengthCounter:
    """One token per character."""

    def count_tokens(self, text: str, *, include_special: bool = True) -> int:
        return len(text)


def test_a_fragment_made_only_of_invisible_characters_is_not_a_chunk() -> None:
    zero_width = chr(0x200B) * 4  # zero-width space: not whitespace, not visible
    pages = [Page(1, f"aaaa {zero_width}")]

    chunks = chunk_pages(pages, LengthCounter(), size=100, overlap=0, max_tokens=5)

    assert [chunk.text for chunk in chunks] == ["aaaa"]
    assert [chunk.index for chunk in chunks] == [0]
