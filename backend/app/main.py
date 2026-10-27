"""FastAPI application factory."""

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api.v1.router import api_router
from app.core.config import Settings, load_settings
from app.core.database import create_db_engine, create_session_factory
from app.core.handlers import register_exception_handlers
from app.core.logging import configure_logging
from app.core.security_headers import SecureHeadersMiddleware


def create_app(settings: Settings | None = None) -> FastAPI:
    settings = settings or load_settings()
    configure_logging(settings.log_level)

    app = FastAPI(title="AsistenteIA API", version="0.1.0")
    engine = create_db_engine(settings.database_url, settings.db_connect_timeout_seconds)
    app.state.settings = settings
    app.state.session_factory = create_session_factory(engine)

    app.add_middleware(SecureHeadersMiddleware)
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origins or [],
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )
    register_exception_handlers(app)
    app.include_router(api_router, prefix="/api/v1")
    return app


def app_factory() -> FastAPI:
    """Uvicorn entry point: `uvicorn app.main:app_factory --factory`."""
    return create_app()
