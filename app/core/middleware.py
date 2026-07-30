"""HTTP middleware: correlation ids, access logging and hardened headers."""

from __future__ import annotations

import time
import uuid
from collections.abc import Awaitable, Callable

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import Response

from app.core.logging import correlation_id, get_logger

logger = get_logger("http")
REQUEST_ID_HEADER = "X-Request-ID"

_SECURITY_HEADERS = {
    "X-Content-Type-Options": "nosniff",
    "X-Frame-Options": "DENY",
    "Referrer-Policy": "no-referrer",
    "Content-Security-Policy": "default-src 'none'; frame-ancestors 'none'",
    "Permissions-Policy": "geolocation=(), microphone=(), camera=()",
}


class CorrelationMiddleware(BaseHTTPMiddleware):
    async def dispatch(
        self, request: Request, call_next: Callable[[Request], Awaitable[Response]]
    ) -> Response:
        cid = request.headers.get(REQUEST_ID_HEADER) or uuid.uuid4().hex
        token = correlation_id.set(cid)
        start = time.perf_counter()
        try:
            response = await call_next(request)
        finally:
            correlation_id.reset(token)
        elapsed = round((time.perf_counter() - start) * 1000, 2)
        response.headers[REQUEST_ID_HEADER] = cid
        logger.info(
            "request_completed",
            method=request.method,
            path=request.url.path,
            status_code=response.status_code,
            duration_ms=elapsed,
        )
        return response


class SecurityHeadersMiddleware(BaseHTTPMiddleware):
    async def dispatch(
        self, request: Request, call_next: Callable[[Request], Awaitable[Response]]
    ) -> Response:
        response = await call_next(request)
        for header, value in _SECURITY_HEADERS.items():
            response.headers.setdefault(header, value)
        return response
