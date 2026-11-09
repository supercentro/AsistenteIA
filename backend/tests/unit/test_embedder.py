"""The embedder: protocol, fake, local model loading and the fail-fast rules (task 5.1).

The local model is replaced by fake `torch` and `sentence_transformers` modules injected into
`sys.modules`, so the order of the calls (threads before load, load before the probe) and the
failure handling are tested without the real model. The real model is `test_embedder_realmodel.py`.
"""

import logging
import math
import sys
import types
from collections.abc import Sequence
from pathlib import Path
from typing import Any

import pytest

from app.core import config as config_module
from app.core.config import Settings
from app.core.vector_validation import EMBEDDING_DIMENSIONS, validate_embedding
from app.rag import embedder as embedder_module
from app.rag.embedder import (
    PROBE_TEXT,
    Embedder,
    EmbedderConfigurationError,
    EmbedderStartupError,
    EmbeddingError,
    FakeEmbedder,
    LocalEmbedder,
    build_embedder,
    startup_check,
)
from tests.constants import TEST_JWT_SECRET

SECRET = "TEXTO-CONFIDENCIAL-12345"


# --- fake modules ---------------------------------------------------------------------------------


class FakeTokenizer:
    def __init__(self) -> None:
        self.calls: list[tuple[str, bool]] = []

    def encode(self, text: str, add_special_tokens: bool = True, **_: object) -> list[int]:
        self.calls.append((text, add_special_tokens))
        return [1] * (len(text.split()) + (2 if add_special_tokens else 0))


class FakeSentenceModel:
    """Stand-in for `SentenceTransformer`; behaviour is set per test through class attributes."""

    events: list[Any] = []
    dimension: int = EMBEDDING_DIMENSIONS
    reported_dimension: int | None = None  # what the model claims, when it differs from reality
    max_seq_length: int = 128
    vector: list[float] | None = None
    encode_error: Exception | None = None
    load_error: Exception | None = None

    def __init__(self, path: str, device: str | None = None, **kwargs: object) -> None:
        if FakeSentenceModel.load_error is not None:
            raise FakeSentenceModel.load_error
        FakeSentenceModel.events.append(("load", path, device, sorted(kwargs)))
        self.tokenizer = FakeTokenizer()
        self.max_seq_length = FakeSentenceModel.max_seq_length

    def get_sentence_embedding_dimension(self) -> int:
        reported = FakeSentenceModel.reported_dimension
        return FakeSentenceModel.dimension if reported is None else reported

    def encode(self, texts: Sequence[str], **kwargs: Any) -> list[list[float]]:
        FakeSentenceModel.events.append(("encode", len(texts), kwargs.get("batch_size")))
        if FakeSentenceModel.encode_error is not None:
            raise FakeSentenceModel.encode_error
        template = FakeSentenceModel.vector
        width = FakeSentenceModel.dimension
        if template is not None:
            return [list(template) for _ in texts]
        rows = []
        for position, _ in enumerate(texts):
            row = [0.0] * width
            row[position % width] = 1.0
            rows.append(row)
        return rows


@pytest.fixture
def fake_modules(monkeypatch: pytest.MonkeyPatch) -> list[Any]:
    FakeSentenceModel.events = []
    FakeSentenceModel.dimension = EMBEDDING_DIMENSIONS
    FakeSentenceModel.reported_dimension = None
    FakeSentenceModel.max_seq_length = 128
    FakeSentenceModel.vector = None
    FakeSentenceModel.encode_error = None
    FakeSentenceModel.load_error = None
    torch = types.ModuleType("torch")
    torch.set_num_threads = lambda n: FakeSentenceModel.events.append(("threads", n))  # type: ignore[attr-defined]
    st = types.ModuleType("sentence_transformers")
    st.SentenceTransformer = FakeSentenceModel  # type: ignore[attr-defined]
    monkeypatch.setitem(sys.modules, "torch", torch)
    monkeypatch.setitem(sys.modules, "sentence_transformers", st)
    return FakeSentenceModel.events


@pytest.fixture
def model_dir(tmp_path: Path) -> Path:
    path = tmp_path / "model"
    path.mkdir()
    (path / "config.json").write_text("{}", encoding="ascii")
    return path


def settings_for(model_dir: Path, **overrides: object) -> Settings:
    values: dict[str, object] = {
        "database_url": "postgresql+psycopg://u:p@localhost:5432/x_test",
        "jwt_secret": TEST_JWT_SECRET,
        "cors_origins": ["http://localhost:5173"],
        "embedding_model_path": model_dir,
    }
    values.update(overrides)
    return Settings(**values)  # type: ignore[arg-type]


# --- the fake embedder ----------------------------------------------------------------------------


def test_the_fake_embedder_returns_one_valid_vector_per_text_in_order() -> None:
    texts = ["la derivada mide el cambio", "the integral adds up", "matrices y vectores"]

    vectors = FakeEmbedder().embed(texts)

    assert len(vectors) == 3
    for vector in vectors:
        assert len(vector) == EMBEDDING_DIMENSIONS
        assert validate_embedding(vector) == pytest.approx(vector)
    assert vectors[0] != vectors[1] != vectors[2]


def test_the_fake_embedder_is_deterministic() -> None:
    first = FakeEmbedder().embed(["misma frase"])
    second = FakeEmbedder().embed(["misma frase", "otra"])

    assert first[0] == second[0]


def test_similar_texts_are_closer_than_unrelated_ones() -> None:
    a, b, c = FakeEmbedder().embed(
        ["derivada de una funcion", "la derivada de la funcion", "historia del imperio romano"]
    )

    def cosine(x: list[float], y: list[float]) -> float:
        return sum(p * q for p, q in zip(x, y, strict=True))

    assert cosine(a, b) > cosine(a, c) + 0.2


def test_the_fake_embedder_handles_empty_and_odd_input() -> None:
    fake = FakeEmbedder()

    assert fake.embed([]) == []
    for text in ("", "   ", "\x00", "emoji \U0001f600", "x" * 10_000):
        vector = fake.embed([text])[0]
        assert len(vector) == EMBEDDING_DIMENSIONS
        validate_embedding(vector)


def test_the_fake_embedder_counts_words_and_two_special_tokens() -> None:
    fake = FakeEmbedder()

    assert fake.count_tokens("uno dos tres", include_special=False) == 3
    assert fake.count_tokens("uno dos tres") == 5
    assert fake.count_tokens("", include_special=False) == 0


def test_fake_and_local_embedders_satisfy_the_protocol() -> None:
    assert isinstance(FakeEmbedder(), Embedder)
    assert Embedder.__name__ == "Embedder"


# --- the startup check ----------------------------------------------------------------------------


def test_the_startup_check_accepts_a_good_embedder() -> None:
    startup_check(FakeEmbedder())


class Broken:
    def __init__(self, vectors: list[list[float]] | Exception) -> None:
        self.vectors = vectors

    def embed(self, texts: Sequence[str]) -> list[list[float]]:
        if isinstance(self.vectors, Exception):
            raise self.vectors
        return self.vectors

    def count_tokens(self, text: str, *, include_special: bool = True) -> int:
        return 1


@pytest.mark.parametrize(
    "vectors",
    [
        [[1.0] * 100],  # wrong dimension
        [[0.0] * EMBEDDING_DIMENSIONS],  # zero vector: norm out of range
        [[math.nan] * EMBEDDING_DIMENSIONS],
        [[1e30] * EMBEDDING_DIMENSIONS],
        [],  # nothing returned
        RuntimeError(SECRET),
    ],
)
def test_the_startup_check_rejects_bad_embedders_with_fixed_text(
    vectors: list[list[float]] | Exception,
) -> None:
    with pytest.raises(EmbedderStartupError) as exc:
        startup_check(Broken(vectors))

    assert SECRET not in str(exc.value)
    assert exc.value.__cause__ is None
    assert exc.value.__context__ is None or exc.value.__suppress_context__  # not chained


# --- the local embedder ---------------------------------------------------------------------------


def test_threads_are_set_before_the_model_loads_and_before_the_first_inference(
    fake_modules: list[Any], model_dir: Path
) -> None:
    LocalEmbedder.load(model_dir, threads=3, batch_size=16)

    kinds = [event[0] for event in fake_modules]
    assert kinds == ["threads", "load", "encode"]  # encode is the startup probe
    assert fake_modules[0] == ("threads", 3)
    assert fake_modules[1][1] == str(model_dir)
    assert fake_modules[1][2] == "cpu"


def test_the_threads_come_from_the_cpu_quota_unless_set_explicitly(
    fake_modules: list[Any], model_dir: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(config_module, "detect_cpu_quota", lambda: 2)

    build_embedder(settings_for(model_dir))
    assert ("threads", 2) in fake_modules

    fake_modules.clear()
    build_embedder(settings_for(model_dir, embedding_threads=1))
    assert ("threads", 1) in fake_modules
    assert ("threads", 2) not in fake_modules


def test_missing_model_files_fail_before_anything_is_imported(
    fake_modules: list[Any], tmp_path: Path
) -> None:
    with pytest.raises(EmbedderStartupError):
        LocalEmbedder.load(tmp_path / "does-not-exist", threads=1, batch_size=16)

    assert fake_modules == []


def test_an_empty_model_directory_fails(fake_modules: list[Any], tmp_path: Path) -> None:
    empty = tmp_path / "empty"
    empty.mkdir()

    with pytest.raises(EmbedderStartupError):
        LocalEmbedder.load(empty, threads=1, batch_size=16)


def test_a_model_that_cannot_be_loaded_fails_with_fixed_text(
    fake_modules: list[Any], model_dir: Path
) -> None:
    FakeSentenceModel.load_error = OSError(f"corrupt weights {SECRET}")

    with pytest.raises(EmbedderStartupError) as exc:
        LocalEmbedder.load(model_dir, threads=1, batch_size=16)

    assert SECRET not in str(exc.value)
    assert exc.value.__cause__ is None
    assert exc.value.__context__ is None or exc.value.__suppress_context__  # not chained


def test_a_wrong_dimension_fails_before_any_job(fake_modules: list[Any], model_dir: Path) -> None:
    FakeSentenceModel.dimension = 768

    with pytest.raises(EmbedderStartupError):
        LocalEmbedder.load(model_dir, threads=1, batch_size=16)


def test_a_model_that_reports_another_dimension_fails_even_if_its_vectors_look_right(
    fake_modules: list[Any], model_dir: Path
) -> None:
    FakeSentenceModel.reported_dimension = 768

    with pytest.raises(EmbedderStartupError, match="unexpected dimension"):
        LocalEmbedder.load(model_dir, threads=1, batch_size=16)


def test_an_unexpected_sequence_length_fails(fake_modules: list[Any], model_dir: Path) -> None:
    FakeSentenceModel.max_seq_length = 512

    with pytest.raises(EmbedderStartupError):
        LocalEmbedder.load(model_dir, threads=1, batch_size=16)


def test_a_probe_with_an_invalid_vector_fails_the_start(
    fake_modules: list[Any], model_dir: Path
) -> None:
    FakeSentenceModel.vector = [0.0] * EMBEDDING_DIMENSIONS

    with pytest.raises(EmbedderStartupError):
        LocalEmbedder.load(model_dir, threads=1, batch_size=16)


def test_the_probe_text_is_embedded_once_at_start(fake_modules: list[Any], model_dir: Path) -> None:
    LocalEmbedder.load(model_dir, threads=1, batch_size=16)

    assert fake_modules[-1] == ("encode", 1, 16)
    assert PROBE_TEXT


def test_embed_returns_validated_vectors_in_order_in_batches(
    fake_modules: list[Any], model_dir: Path
) -> None:
    local = LocalEmbedder.load(model_dir, threads=1, batch_size=8)
    fake_modules.clear()

    vectors = local.embed(["a", "b", "c"])

    assert [vector.index(1.0) for vector in vectors] == [0, 1, 2]
    assert fake_modules == [("encode", 3, 8)]
    assert local.embed([]) == []


def test_embed_failures_become_a_fixed_error_without_the_text(
    fake_modules: list[Any], model_dir: Path, caplog: pytest.LogCaptureFixture
) -> None:
    local = LocalEmbedder.load(model_dir, threads=1, batch_size=16)
    FakeSentenceModel.encode_error = RuntimeError(f"out of memory while embedding {SECRET}")

    with caplog.at_level(logging.DEBUG), pytest.raises(EmbeddingError) as exc:
        local.embed([SECRET])

    assert SECRET not in str(exc.value)
    assert exc.value.__cause__ is None
    assert exc.value.__context__ is None or exc.value.__suppress_context__  # not chained
    assert SECRET not in caplog.text


@pytest.mark.parametrize(
    "bad",
    [
        [math.nan] * EMBEDDING_DIMENSIONS,
        [math.inf] * EMBEDDING_DIMENSIONS,
        [0.0] * EMBEDDING_DIMENSIONS,
        [1e30] * EMBEDDING_DIMENSIONS,
    ],
)
def test_an_invalid_vector_from_the_model_is_an_embedding_error(
    fake_modules: list[Any], model_dir: Path, bad: list[float]
) -> None:
    local = LocalEmbedder.load(model_dir, threads=1, batch_size=16)
    FakeSentenceModel.vector = bad

    with pytest.raises(EmbeddingError, match="invalid embedding"):
        local.embed(["texto"])


def test_the_returned_vectors_are_the_single_precision_validated_values(
    fake_modules: list[Any], model_dir: Path
) -> None:
    local = LocalEmbedder.load(model_dir, threads=1, batch_size=16)
    FakeSentenceModel.vector = [0.1] * EMBEDDING_DIMENSIONS

    vector = local.embed(["texto"])[0]

    assert vector == validate_embedding([0.1] * EMBEDDING_DIMENSIONS)
    assert vector[0] != 0.1  # the float32 value, not the double: it is what the database stores


def test_token_counts_use_the_tokenizer_with_and_without_special_tokens(
    fake_modules: list[Any], model_dir: Path
) -> None:
    local = LocalEmbedder.load(model_dir, threads=1, batch_size=16)

    assert local.count_tokens("uno dos tres", include_special=False) == 3
    assert local.count_tokens("uno dos tres") == 5
    assert local.count_tokens("uno dos tres", include_special=True) == 5


# --- no fallback ----------------------------------------------------------------------------------


def test_a_failing_local_model_never_falls_back_to_the_fake(
    fake_modules: list[Any], model_dir: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    FakeSentenceModel.load_error = OSError("boom")

    def forbidden(self: FakeEmbedder) -> None:
        raise AssertionError("the fake embedder must not be created")

    monkeypatch.setattr(FakeEmbedder, "__init__", forbidden)

    with pytest.raises(EmbedderStartupError):
        build_embedder(settings_for(model_dir))


def test_the_local_backend_is_the_default(fake_modules: list[Any], model_dir: Path) -> None:
    assert isinstance(build_embedder(settings_for(model_dir)), LocalEmbedder)


def test_the_fake_backend_is_built_only_when_the_settings_allow_it(model_dir: Path) -> None:
    allowed = settings_for(model_dir, app_env="test", embedder_backend="fake")

    assert isinstance(build_embedder(allowed), FakeEmbedder)


def test_the_factory_refuses_a_fake_backend_in_production_even_if_settings_were_bypassed(
    model_dir: Path,
) -> None:
    forged = Settings.model_construct(
        **{
            **settings_for(model_dir).model_dump(),
            "app_env": "production",
            "embedder_backend": "fake",
            "allow_fake_embedder": True,
        }
    )

    with pytest.raises(EmbedderConfigurationError):
        build_embedder(forged)


def test_importing_the_module_does_not_import_the_machine_learning_libraries() -> None:
    source = Path(embedder_module.__file__).read_text(encoding="utf-8")
    top_level = [line for line in source.splitlines() if line.startswith(("import ", "from "))]

    assert not any("torch" in line or "sentence_transformers" in line for line in top_level)
