"""The real model (marker `realmodel`, excluded from CI and from the default run).

Run inside the worker image, where the pinned model is baked in and the hub is offline:
`pytest -m realmodel tests/unit/test_embedder_realmodel.py`. Skipped when the model is absent.
"""

import os
from collections.abc import Iterator
from pathlib import Path

import pytest

from app.core.vector_validation import EMBEDDING_DIMENSIONS, validate_embedding
from app.rag.embedder import LocalEmbedder

pytestmark = pytest.mark.realmodel

MODEL_PATH = Path(
    os.environ.get("EMBEDDING_MODEL_PATH", "/opt/models/paraphrase-multilingual-MiniLM-L12-v2")
)


@pytest.fixture(scope="module")
def local() -> Iterator[LocalEmbedder]:
    if not MODEL_PATH.is_dir():
        pytest.skip(f"the embedding model is not available at {MODEL_PATH}")
    yield LocalEmbedder.load(MODEL_PATH, threads=2, batch_size=16)


def test_spanish_and_english_texts_give_384_valid_components(local: LocalEmbedder) -> None:
    vectors = local.embed(["La derivada mide la tasa de cambio.", "The integral sums areas."])

    assert len(vectors) == 2
    for vector in vectors:
        assert len(vector) == EMBEDDING_DIMENSIONS
        assert validate_embedding(vector) == vector


def test_the_same_text_gives_the_same_vector(local: LocalEmbedder) -> None:
    first = local.embed(["Una frase de prueba."])[0]
    second = local.embed(["Otra distinta.", "Una frase de prueba."])[1]

    assert first == pytest.approx(second, abs=1e-5)


def test_related_text_is_closer_than_unrelated_text(local: LocalEmbedder) -> None:
    question, related, unrelated = local.embed(
        [
            "Que es la derivada de una funcion?",
            "La derivada de una funcion mide su variacion instantanea.",
            "El imperio romano cayo en el siglo quinto.",
        ]
    )

    def dot(a: list[float], b: list[float]) -> float:
        return sum(x * y for x, y in zip(a, b, strict=True))

    assert dot(question, related) > dot(question, unrelated)


def test_special_tokens_add_exactly_two(local: LocalEmbedder) -> None:
    for text in ("hola mundo", "La derivada mide el cambio.", "日本語のテキスト", "😀"):
        assert local.count_tokens(text) == local.count_tokens(text, include_special=False) + 2


def test_the_model_ignores_tokens_beyond_the_limit_so_chunks_must_fit(local: LocalEmbedder) -> None:
    short = "La derivada mide el cambio de una funcion. " * 6
    long = short + "El imperio romano cayo en el siglo quinto. " * 40

    assert local.count_tokens(short) <= 128 < local.count_tokens(long)
