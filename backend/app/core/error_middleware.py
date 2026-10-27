"""Outermost safety net for unexpected exceptions.

Starlette re-raises after its generic 500 handler, and the server then logs a full traceback whose
exception text may contain request data (SQL rows, emails, hashes). This middleware answers the 500
itself so nothing propagates, and logs only the exception type, method and path.
"""

import logging

from starlette.responses import JSONResponse
from starlette.types import ASGIApp, Message, Receive, Scope, Send

from app.core.security_headers import apply_secure_headers

logger = logging.getLogger(__name__)


class UnhandledErrorMiddleware:
    def __init__(self, app: ASGIApp) -> None:
        self.app = app

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        response_started = False

        async def tracking_send(message: Message) -> None:
            nonlocal response_started
            if message["type"] == "http.response.start":
                response_started = True
            await send(message)

        try:
            await self.app(scope, receive, tracking_send)
        except Exception as exc:
            logger.error(
                "unhandled exception type=%s method=%s path=%s",
                type(exc).__name__,
                scope.get("method"),
                scope.get("path"),
            )
            if response_started:
                return
            response = JSONResponse(
                status_code=500,
                content={"code": "INTERNAL_ERROR", "message": "Internal server error"},
            )
            apply_secure_headers(response)
            await response(scope, receive, send)
