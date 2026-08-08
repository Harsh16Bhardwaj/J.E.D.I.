"""Request correlation, safe access logging, and private-response hardening."""

import logging
import re
from time import perf_counter
from uuid import uuid4

from fastapi import Request
from fastapi.responses import JSONResponse
from starlette.middleware.base import BaseHTTPMiddleware, RequestResponseEndpoint
from starlette.responses import Response
from starlette.types import ASGIApp, Receive, Scope, Send

logger = logging.getLogger("jedi.requests")
request_id_pattern = re.compile(r"^[A-Za-z0-9._-]{1,128}$")


class ServicePrefixMiddleware:
    """Mount the same FastAPI routes locally and below Vercel's public prefix."""

    def __init__(self, app: ASGIApp, prefix: str = "/svc/ml") -> None:
        self.app = app
        self.prefix = prefix.rstrip("/")

    async def __call__(
        self,
        scope: Scope,
        receive: Receive,
        send: Send,
    ) -> None:
        path = scope.get("path", "")
        if scope["type"] in {"http", "websocket"} and (
            path == self.prefix or path.startswith(f"{self.prefix}/")
        ):
            scope = dict(scope)
            scope["root_path"] = f"{scope.get('root_path', '')}{self.prefix}"
            scope["path"] = path[len(self.prefix) :] or "/"
            scope["raw_path"] = scope["path"].encode("utf-8")
        await self.app(scope, receive, send)


class RequestContextMiddleware(BaseHTTPMiddleware):
    """Attach request IDs and log metadata while excluding sensitive content."""

    async def dispatch(
        self, request: Request, call_next: RequestResponseEndpoint
    ) -> Response:
        supplied_id = request.headers.get("X-Request-ID", "")
        request_id = (
            supplied_id if request_id_pattern.fullmatch(supplied_id) else uuid4().hex
        )
        request.state.request_id = request_id
        started = perf_counter()

        try:
            response = await call_next(request)
        except Exception as exception:
            logger.error(
                "request_failed method=%s path=%s request_id=%s error_type=%s",
                request.method,
                request.url.path,
                request_id,
                type(exception).__name__,
            )
            response = JSONResponse(
                status_code=500,
                content={
                    "error": {
                        "code": "INTERNAL_ERROR",
                        "message": "Unexpected server error.",
                        "requestId": request_id,
                    }
                },
            )

        response.headers["X-Request-ID"] = request_id
        response.headers["X-Content-Type-Options"] = "nosniff"
        if request.url.path.startswith(("/api/", "/internal/")):
            response.headers["Cache-Control"] = "no-store"

        duration_ms = (perf_counter() - started) * 1000
        logger.info(
            "request method=%s path=%s status=%s duration_ms=%.2f request_id=%s",
            request.method,
            request.url.path,
            response.status_code,
            duration_ms,
            request_id,
        )
        return response
