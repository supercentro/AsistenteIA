"""FastAPI application factory."""

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api.v1.router import api_router
from app.core.config import Settings, load_settings
from app.core.database import create_db_engine, create_session_factory
from app.core.error_middleware import UnhandledErrorMiddleware
from app.core.handlers import register_exception_handlers
from app.core.logging import configure_logging
from app.core.rate_limit import RateLimiter
from app.core.security import PasswordService
from app.core.security_headers import SecureHeadersMiddleware
from app.core.upload_guard import MULTIPART_OVERHEAD_BYTES, UploadBodyGuard, UploadSlots


def create_app(
    settings: Settings | None = None, password_service: PasswordService | None = None
) -> FastAPI:
    settings = settings or load_settings()
    configure_logging(settings.log_level)

    app = FastAPI(title="AsistenteIA API", version="0.1.0")
    engine = create_db_engine(
        settings.database_url,
        settings.db_connect_timeout_seconds,
        statement_timeout_seconds=settings.db_statement_timeout_api_seconds,
        idle_in_transaction_timeout_seconds=settings.db_idle_in_transaction_timeout_seconds,
    )
    app.state.settings = settings
    app.state.session_factory = create_session_factory(engine)
    app.state.password_service = password_service or PasswordService()
    app.state.login_rate_limiter = RateLimiter(
        settings.login_rate_limit, "login", "Too many login attempts. Try again later."
    )
    app.state.register_rate_limiter = RateLimiter(
        settings.register_rate_limit, "register", "Too many registrations. Try again later."
    )

    app.state.upload_rate_limiter = RateLimiter(
        settings.upload_rate_limit, "upload", "Too many uploads. Try again later."
    )
    app.state.upload_slots = UploadSlots(settings.upload_max_in_flight)

    # Innermost: it wraps `receive` of the upload route only (limit and deadlines on the bytes
    # actually received); the endpoint turns its refusals into the 413 and 408 answers.
    app.add_middleware(
        UploadBodyGuard,
        max_body_bytes=settings.max_upload_mb * 1024 * 1024 + MULTIPART_OVERHEAD_BYTES,
        body_timeout_seconds=settings.upload_body_timeout_seconds,
        idle_seconds=settings.upload_body_idle_seconds,
    )
    app.add_middleware(SecureHeadersMiddleware)
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origins or [],
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
        # Browsers only expose safelisted headers: the frontend needs Retry-After of a 429 (TD-021).
        expose_headers=["Retry-After"],
    )
    app.add_middleware(UnhandledErrorMiddleware)  # added last: outermost
    register_exception_handlers(app)
    app.include_router(api_router, prefix="/api/v1")
    return app


def app_factory() -> FastAPI:
    """Uvicorn entry point: `uvicorn app.main:app_factory --factory`."""
    return create_app()
