"""Embedder is loaded at API startup and injected via app.state (task 10.1)."""

from unittest.mock import MagicMock, patch

import pytest

from app.core.config import Settings


def _settings() -> Settings:
    return Settings(
        database_url="postgresql+psycopg://u:p@h/d",
        jwt_secret="Zq8!vN3#rT6&wK1@mX9$pL4^bC7*dF2_hG5+yJ0",
        cors_origins=["http://localhost:3000"],
        embedder_backend="fake",
        app_env="test",
    )


def test_create_app_stores_the_embedder_on_app_state() -> None:
    from app.main import create_app

    app = create_app(_settings())

    assert hasattr(app.state, "embedder")
    assert app.state.embedder is not None


def test_create_app_fails_fast_when_embedder_cannot_be_built() -> None:
    from app.main import create_app

    settings = _settings()
    with (
        patch(
            "app.main.build_embedder",
            side_effect=RuntimeError("model files missing"),
        ),
        pytest.raises(RuntimeError, match="model files missing"),
    ):
        create_app(settings)


def test_chat_deps_uses_the_preloaded_embedder_not_a_new_one() -> None:
    """The chat dependency factory must accept an embedder argument."""
    from app.api.chat_deps import build_rag_service

    db = MagicMock()
    settings = _settings()
    embedder = MagicMock()

    service = build_rag_service(db=db, settings=settings, embedder=embedder)

    assert service._embedder is embedder
