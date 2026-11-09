"""Token-based chunking (change 6, task 5.3), design D8.

Each page is split on its own, so a chunk never crosses a page and `page_number` stays exact. The
splitter measures length in model tokens without special tokens (`size` 100, `overlap` 20); every
chunk is then measured again with the special tokens and, if it is above the model limit of 128,
re-split, so nothing is silently truncated at embedding time. Chunks without a visible character
are dropped, and a document that would produce more than `max_chunks` chunks fails early.

The text is data: error messages are fixed and never contain any of it.
"""

from collections.abc import Sequence
from dataclasses import dataclass

from app.rag.embedder import TokenCounter
from app.rag.normalizer import has_visible_text

DEFAULT_CHUNK_SIZE = 100
DEFAULT_CHUNK_OVERLAP = 20
MODEL_TOKEN_LIMIT = 128
DEFAULT_MAX_CHUNKS = 2_000
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


def chunk_pages(
    pages: Sequence[Page],
    counter: TokenCounter,
    *,
    size: int = DEFAULT_CHUNK_SIZE,
    overlap: int = DEFAULT_CHUNK_OVERLAP,
    max_tokens: int = MODEL_TOKEN_LIMIT,
    max_chunks: int = DEFAULT_MAX_CHUNKS,
) -> list[Chunk]:
    """Split the pages into chunks with consecutive global indexes.

    Raises `ValueError` for an invalid size or overlap, `TooManyChunksError` as soon as the cap is
    exceeded, and `ChunkTooLongError` if a fragment cannot fit `max_tokens`.
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
    for page in pages:
        for piece in splitter.split_text(page.text):
            if not has_visible_text(piece):
                continue
            for fitted in _fit(piece, counter, max_tokens):
                if not has_visible_text(fitted):
                    continue
                if len(chunks) >= max_chunks:
                    raise TooManyChunksError
                chunks.append(Chunk(index=len(chunks), page_number=page.number, text=fitted))
    return chunks
