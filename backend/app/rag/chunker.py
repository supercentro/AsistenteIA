"""Token-based chunking (change 6, task 5.3), design D8.

Each page is split on its own, so a chunk never crosses a page and `page_number` stays exact. The
splitter measures length in model tokens without special tokens (`size` 100, `overlap` 20); every
chunk is then measured again with the special tokens and, if it is above the model limit of 128,
re-split, so nothing is silently truncated at embedding time. Chunks without a visible character
are dropped, and a document that would produce more than `max_chunks` chunks fails early.

The work is bounded (review finding R-01): a page is handed to the splitter in windows of at most
`DEFAULT_WINDOW_CHARS` characters, cut on the strongest separator found in the second half of the
window, so the cap is checked after each window and a caller-supplied `poll` can stop the job (the
deadline) between windows. A page that fits one window is chunked exactly as before; a longer one
loses the 20-token overlap only across a window cut, never a character of text.

The text is data: error messages are fixed and never contain any of it.
"""

from collections.abc import Callable, Iterator, Sequence
from dataclasses import dataclass

from app.rag.embedder import TokenCounter
from app.rag.normalizer import has_visible_text

DEFAULT_CHUNK_SIZE = 100
DEFAULT_CHUNK_OVERLAP = 20
MODEL_TOKEN_LIMIT = 128
DEFAULT_MAX_CHUNKS = 2_000
# About 3,000 words: seconds of tokenizer work at worst; most pages fit a single window.
DEFAULT_WINDOW_CHARS = 20_000
_WINDOW_BREAKS = ("\n\n", "\n", ". ", " ")
# Paragraph, line, sentence, word, character.
SEPARATORS = ["\n\n", "\n", ". ", " ", ""]


class ChunkingError(RuntimeError):
    """Base of the controlled chunking failures (fixed text)."""


class TooManyChunksError(ChunkingError):
    """The document would produce more chunks than allowed (TOO_MANY_CHUNKS)."""

    def __init__(self) -> None:
        super().__init__("the document produces more chunks than allowed")


class ChunkTooLongError(ChunkingError):
    """A chunk cannot be made to fit the model limit (PROCESSING_FAILED)."""

    def __init__(self) -> None:
        super().__init__("a fragment cannot be made to fit the model limit")


@dataclass(frozen=True)
class Page:
    """Normalised text of one page; `number` is None for plain text and Markdown."""

    number: int | None
    text: str


@dataclass(frozen=True)
class Chunk:
    index: int
    page_number: int | None
    text: str


def _fit(text: str, counter: TokenCounter, limit: int) -> list[str]:
    """Split `text` into pieces of at most `limit` tokens (special tokens included)."""
    if counter.count_tokens(text, include_special=True) <= limit:
        return [text]
    if len(text) <= 1:
        raise ChunkTooLongError
    middle = len(text) // 2
    cut = text.rfind(" ", 0, middle + 1)
    if cut <= 0:
        cut = middle
    left, right = text[:cut].strip(), text[cut:].strip()
    pieces: list[str] = []
    for part in (left, right):
        if part:
            pieces.extend(_fit(part, counter, limit))
    return pieces


def split_windows(text: str, limit: int) -> Iterator[str]:
    """Yield consecutive slices of `text` of at most `limit` characters that rebuild it exactly.

    A slice ends after the strongest separator (paragraph, line, sentence, space) found in its
    second half; text without any is cut at the limit.
    """
    if limit < 1:
        raise ValueError("window must be at least 1 character")
    start, length = 0, len(text)
    while start < length:
        end = min(start + limit, length)
        if end < length:
            for separator in _WINDOW_BREAKS:
                cut = text.rfind(separator, start + limit // 2, end)
                if cut != -1:
                    end = cut + len(separator)
                    break
        yield text[start:end]
        start = end


def chunk_pages(
    pages: Sequence[Page],
    counter: TokenCounter,
    *,
    size: int = DEFAULT_CHUNK_SIZE,
    overlap: int = DEFAULT_CHUNK_OVERLAP,
    max_tokens: int = MODEL_TOKEN_LIMIT,
    max_chunks: int = DEFAULT_MAX_CHUNKS,
    window_chars: int = DEFAULT_WINDOW_CHARS,
    poll: Callable[[], None] | None = None,
) -> list[Chunk]:
    """Split the pages into chunks with consecutive global indexes.

    Raises `ValueError` for an invalid size, overlap or window, `TooManyChunksError` as soon as the
    cap is exceeded, and `ChunkTooLongError` if a fragment cannot fit `max_tokens`. `poll` runs
    before every window and every 16 pieces; an exception it raises stops the work.
    """
    if size < 1:
        raise ValueError("size must be at least 1")
    if not 0 <= overlap < size:
        raise ValueError("overlap must be between 0 and size - 1")
    # Imported here so that importing this module (and the API process) does not need the library.
    from langchain_text_splitters import RecursiveCharacterTextSplitter

    splitter = RecursiveCharacterTextSplitter(
        chunk_size=size,
        chunk_overlap=overlap,
        length_function=lambda text: counter.count_tokens(text, include_special=False),
        separators=SEPARATORS,
        keep_separator="end",
        strip_whitespace=True,
    )
    chunks: list[Chunk] = []
    pieces_seen = 0
    for page in pages:
        for window in split_windows(page.text, window_chars):
            if poll is not None:
                poll()
            for piece in splitter.split_text(window):
                pieces_seen += 1
                if poll is not None and pieces_seen % 16 == 0:
                    poll()
                if not has_visible_text(piece):
                    continue
                for fitted in _fit(piece, counter, max_tokens):
                    if not has_visible_text(fitted):
                        continue
                    if len(chunks) >= max_chunks:
                        raise TooManyChunksError
                    chunks.append(Chunk(index=len(chunks), page_number=page.number, text=fitted))
    return chunks
