"""Chunking with the real tokenizer (marker `realmodel`; see `test_embedder_realmodel.py`).

Proves the 128-token limit with special tokens on the kinds of text that tokenise badly.
"""

import os
import time
from collections.abc import Iterator
from pathlib import Path

import pytest

from app.rag.chunker import Page, chunk_pages
from app.rag.embedder import LocalEmbedder
from app.rag.loaders import load_text

pytestmark = pytest.mark.realmodel

MODEL_PATH = Path(
    os.environ.get("EMBEDDING_MODEL_PATH", "/opt/models/paraphrase-multilingual-MiniLM-L12-v2")
)
LIMIT = 128

SPANISH = (
    "La derivada de una funcion en un punto mide la rapidez con que cambia su valor. "
    "Los estudiantes deben comprender el concepto de limite antes de abordar la regla de la "
    "cadena. "
)
SAMPLES = {
    "spanish prose": SPANISH * 120,
    "very long word": "supercalifragilisticoespialidoso" * 400,
    "very long ascii run": "a" * 6000,
    "urls": "visita https://ejemplo.edu.ar/materias/algebra/unidad-3?id=12345&lang=es#seccion "
    * 150,
    "digits": "3141592653589793238462643383279502884197169399375105820974944592307816406286 " * 80,
    "emoji": "\U0001f600\U0001f468\u200d\U0001f469\u200d\U0001f467 hola \U0001f680 " * 300,
    "cjk": "日本語のテキストは単語の間に空白がありません。" * 200,
    "right to left": "هذا نص تجريبي باللغة العربية لاختبار الترميز. " * 150,
    "mixed": (SPANISH + "日本語 😀 https://x.io/a?b=1 " + "z" * 300 + " ") * 40,
    "code": "def f(x):\n    return x**2 + 3*x - 1  # polinomio\n" * 200,
}


@pytest.fixture(scope="module")
def local() -> Iterator[LocalEmbedder]:
    if not MODEL_PATH.is_dir():
        pytest.skip(f"the embedding model is not available at {MODEL_PATH}")
    yield LocalEmbedder.load(MODEL_PATH, threads=2, batch_size=16)


@pytest.mark.parametrize("name", sorted(SAMPLES))
def test_no_chunk_exceeds_128_tokens_with_special_tokens(local: LocalEmbedder, name: str) -> None:
    chunks = chunk_pages([Page(1, SAMPLES[name])], local, max_chunks=100_000)

    assert chunks, name
    longest = max(local.count_tokens(chunk.text, include_special=True) for chunk in chunks)
    assert longest <= LIMIT, (name, longest)


def test_ordinary_spanish_prose_is_chunked_near_the_target_size(local: LocalEmbedder) -> None:
    chunks = chunk_pages([Page(None, SPANISH * 120)], local)

    sizes = [local.count_tokens(chunk.text, include_special=False) for chunk in chunks]
    assert max(sizes) <= 100
    assert sum(sizes) / len(sizes) >= 60  # chunks are not tiny


S01_PADDINGS = [
    pytest.param("\u200b", id="zero width space"),
    pytest.param("\u200d", id="zero width joiner"),
    pytest.param("\u2060", id="word joiner"),
    pytest.param("\u0301", id="combining acute"),
    pytest.param("\ue000", id="private use"),
    pytest.param(" ", id="space"),
    pytest.param("\t", id="tab"),
]


@pytest.mark.parametrize("padding", S01_PADDINGS)
def test_one_visible_character_and_two_million_padding_characters_cost_seconds_not_minutes(
    local: LocalEmbedder, padding: str
) -> None:
    # Second review S-01: this input took 17 to 60 s of tokenizer work on 2 CPUs before the
    # normaliser bounded the runs of characters without content.
    payload = ("x" + padding * 1_999_998 + "y").encode()
    started = time.perf_counter()

    pages = load_text(payload, max_chars=2_000_000)
    chunks = chunk_pages(pages, local, max_chunks=2_000)

    assert 1 <= len(chunks) <= 2
    assert time.perf_counter() - started < 5
