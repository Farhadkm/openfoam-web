"""Minimal HTTP request logging for FastAPI services (trace-correlated via OTel logging)."""

from __future__ import annotations

import logging
import time

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import Response

from shared.http_body_logging import _is_health_path, read_and_log_response

if False:  # TYPE_CHECKING
    from fastapi import FastAPI

logger = logging.getLogger("forge.request")


class RequestLoggingMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next) -> Response:
        start = time.perf_counter()
        method = request.method
        path = request.url.path
        log_request = not _is_health_path(path)
        if log_request:
            logger.info("request %s %s", method, path)
        try:
            response = await call_next(request)
        except Exception:
            if log_request:
                duration_ms = (time.perf_counter() - start) * 1000
                logger.exception(
                    "request failed %s %s duration_ms=%.1f",
                    method,
                    path,
                    duration_ms,
                )
            raise
        if log_request:
            duration_ms = (time.perf_counter() - start) * 1000
            logger.info(
                "request %s %s status=%s duration_ms=%.1f",
                method,
                path,
                response.status_code,
                duration_ms,
            )
        return await read_and_log_response(logger, request, response)


def install_request_logging(app: FastAPI) -> None:
    """Attach request start/end logging middleware (idempotent)."""
    if getattr(app.state, "forge_request_logging", False):
        return
    app.add_middleware(RequestLoggingMiddleware)
    app.state.forge_request_logging = True
