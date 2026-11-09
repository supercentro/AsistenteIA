"""Text embeddings (change 6, task 5.1): the `Embedder` protocol, a fake and the local model.

The local model is `paraphrase-multilingual-MiniLM-L12-v2` (384 dimensions, `max_seq_length` 128)
run on the CPU from files that are already on disk. `torch` and `sentence_transformers` are
imported lazily, only when the local model is loaded, so the API process never imports them.

Rules (text-embedding spec):
- there is no fallback: if the local model cannot be loaded or fails its startup check, the error
  propagates and the process stops; the fake embedder is built only on explicit configuration;
- the number of `torch` threads is set before the model is loaded and before the first inference;
- every vector is validated (`validate_embedding`) and the validated single-precision values are
  the ones returned, so they are exactly what the database stores;
- errors carry fixed text only: never the input text, a path or the library's message.
"""

import hashlib
import importlib
import math
import re
from collections.abc import Sequence
from pathlib import Path
from typing import TYPE_CHECKING, Any, Protocol, runtime_checkable

from app.core.vector_validation import (
    EMBEDDING_DIMENSIONS,
    InvalidSearchInputError,
    validate_embedding,
)

if TYPE_CHECKING:
    from app.core.config import Settings

# Model input limit in tokens, special tokens included (the model ignores everything after it).
MODEL_MAX_SEQ_LENGTH = 128
# Text embedded at start to prove the model works before any job is claimed.
PROBE_TEXT = "Probe de arranque: la derivada mide el cambio de una funcion."
_SPECIAL_TOKENS_FAKE = 2
_WORD = re.compile(r"\w+", re.UNICODE)


class EmbedderConfigurationError(RuntimeError):
    """The configuration asks for an embedder that is not allowed in this environment."""


class EmbedderStartupError(RuntimeError):
    """The embedder cannot start: missing or unusable model, wrong dimension, bad probe."""


class EmbeddingError(RuntimeError):
    """Embedding failed or produced an invalid vector. The document fails with EMBEDDING_FAILED."""


@runtime_checkable
class TokenCounter(Protocol):
    """Counts tokens the way the model does (used by the chunker)."""

    def count_tokens(self, text: str, *, include_special: bool = True) -> int: ...


@runtime_checkable
class Embedder(TokenCounter, Protocol):
    """Turns texts into validated 384-component vectors and counts model tokens."""

    def embed(self, texts: Sequence[str]) -> list[list[float]]: ...


class FakeEmbedder:
    """Deterministic embedder for tests and explicitly controlled environments (never a fallback).

    A hashed bag of words: texts that share words get closer vectors, which lets end-to-end tests
    check retrieval order without the model. Tokens are words; special tokens add two.
    """

    def embed(self, texts: Sequence[str]) -> list[list[float]]:
        return [self._vector(text) for text in texts]

    def count_tokens(self, text: str, *, include_special: bool = True) -> int:
        return len(text.split()) + (_SPECIAL_TOKENS_FAKE if include_special else 0)

    @staticmethod
    def _vector(text: str) -> list[float]:
        values = [0.0] * EMBEDDING_DIMENSIONS
        words = _WORD.findall(text.lower()) or ["\x00empty"]
        for word in words:
            digest = hashlib.sha256(word.encode("utf-8", "replace")).digest()
            slot = int.from_bytes(digest[:4], "big") % EMBEDDING_DIMENSIONS
            values[slot] += 1.0
        norm = math.sqrt(sum(value * value for value in values))
        return validate_embedding([value / norm for value in values])


def startup_check(embedder: Embedder) -> None:
    """Embed the probe text and verify dimension and norm; raise `EmbedderStartupError` if not."""
    try:
        vectors = embedder.embed([PROBE_TEXT])
        if len(vectors) != 1:
            raise EmbedderStartupError("the embedder startup check failed")
        validate_embedding(vectors[0])
    except EmbedderStartupError:
        raise
    except Exception:  # noqa: BLE001 - any failure of the probe stops the start; text is not kept
        raise EmbedderStartupError("the embedder startup check failed") from None


class LocalEmbedder:
    """The local sentence-transformers model on the CPU."""

    def __init__(self, model: Any, batch_size: int) -> None:
        self._model = model
        self._batch_size = batch_size

    @classmethod
    def load(cls, model_path: Path, threads: int, batch_size: int) -> "LocalEmbedder":
        """Load the model from `model_path` and run the startup check.

        Order: the directory is checked first (nothing is imported when it is missing), then the
        thread count is set, then the model is loaded, then dimension and sequence length are
        verified, and finally the probe text goes through `validate_embedding`.
        """
        if not model_path.is_dir() or not any(model_path.iterdir()):
            raise EmbedderStartupError("the embedding model files were not found")
        try:
            torch = importlib.import_module("torch")
            torch.set_num_threads(threads)
            sentence_transformers = importlib.import_module("sentence_transformers")
            model = sentence_transformers.SentenceTransformer(str(model_path), device="cpu")
            # sentence-transformers 6 renamed the method; older names keep working elsewhere.
            get_dimension = getattr(model, "get_embedding_dimension", None)
            if get_dimension is None:
                get_dimension = model.get_sentence_embedding_dimension
            dimension = get_dimension()
            max_seq_length = model.max_seq_length
        except Exception:  # noqa: BLE001 - library messages can name paths or contents
            raise EmbedderStartupError("the embedding model could not be loaded") from None
        if dimension != EMBEDDING_DIMENSIONS:
            raise EmbedderStartupError("the embedding model has an unexpected dimension")
        if max_seq_length != MODEL_MAX_SEQ_LENGTH:
            raise EmbedderStartupError("the embedding model has an unexpected sequence length")
        embedder = cls(model, batch_size)
        startup_check(embedder)
        return embedder

    def embed(self, texts: Sequence[str]) -> list[list[float]]:
        if not texts:
            return []
        try:
            rows = self._model.encode(
                list(texts),
                batch_size=self._batch_size,
                convert_to_numpy=True,
                show_progress_bar=False,
                normalize_embeddings=False,
            )
            vectors = [
                validate_embedding(row.tolist() if hasattr(row, "tolist") else list(row))
                for row in rows
            ]
        except InvalidSearchInputError:
            raise EmbeddingError("the model produced an invalid embedding") from None
        except Exception:  # noqa: BLE001 - never keep the library message: it can echo the text
            raise EmbeddingError("embedding failed") from None
        if len(vectors) != len(texts):
            raise EmbeddingError("embedding failed")
        return vectors

    def count_tokens(self, text: str, *, include_special: bool = True) -> int:
        encoded = self._model.tokenizer.encode(text, add_special_tokens=include_special)
        return len(encoded)


def build_embedder(settings: "Settings") -> Embedder:
    """Build the embedder chosen by the settings; fail fast, never fall back.

    `fake` is accepted only with `APP_ENV=test`, or with `ALLOW_FAKE_EMBEDDER=true` outside
    production (the settings validator enforces it and this function repeats the check, so a
    bypassed validation still cannot put a fake embedder in production).
    """
    if settings.embedder_backend == "fake":
        allowed = settings.app_env == "test" or (
            settings.allow_fake_embedder and settings.app_env != "production"
        )
        if not allowed:
            raise EmbedderConfigurationError("the fake embedder is not allowed in this environment")
        return FakeEmbedder()
    return LocalEmbedder.load(
        settings.embedding_model_path,
        threads=settings.effective_embedding_threads(),
        batch_size=settings.ingestion_batch_size,
    )
