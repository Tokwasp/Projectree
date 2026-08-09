"""Small operational middleware for the internal review API."""

from __future__ import annotations

import logging
import re
import time
import uuid

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse

from .dependencies import get_settings

logger = logging.getLogger(__name__)

_REQUEST_ID = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._:-]{0,127}$")


class RequestBodyTooLarge(Exception):
    pass


class RequestBodyLimitMiddleware:
    """Count streamed chunks so requests cannot bypass Content-Length limits."""

    def __init__(self, app):
        self.app = app

    async def __call__(self, scope, receive, send):
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        limit = get_settings().api.max_request_body_bytes
        received = 0

        async def limited_receive():
            nonlocal received
            message = await receive()
            if message["type"] == "http.request":
                received += len(message.get("body", b""))
                if received > limit:
                    raise RequestBodyTooLarge
            return message

        try:
            await self.app(scope, limited_receive, send)
        except RequestBodyTooLarge:
            request_id = str(uuid.uuid4())
            response = _error(
                413,
                "REQUEST_BODY_TOO_LARGE",
                f"request body exceeds the {limit}-byte limit",
                request_id,
            )
            await response(scope, receive, send)


def _request_id(request: Request) -> str:
    supplied = request.headers.get("X-Request-Id", "").strip()
    if supplied and _REQUEST_ID.fullmatch(supplied):
        return supplied
    return str(uuid.uuid4())


def _error(status_code: int, code: str, message: str, request_id: str):
    return JSONResponse(
        status_code=status_code,
        content={
            "error": {
                "code": code,
                "message": message,
                "requestId": request_id,
            }
        },
        headers={"X-Request-Id": request_id},
    )


def install_http_middleware(app: FastAPI) -> None:
    @app.middleware("http")
    async def request_safety_and_logging(request: Request, call_next):
        request_id = _request_id(request)
        started = time.perf_counter()
        content_length = request.headers.get("content-length")
        if content_length is not None:
            try:
                body_size = int(content_length)
            except ValueError:
                return _error(
                    400,
                    "INVALID_CONTENT_LENGTH",
                    "Content-Length must be an integer",
                    request_id,
                )
            if body_size < 0:
                return _error(
                    400,
                    "INVALID_CONTENT_LENGTH",
                    "Content-Length must not be negative",
                    request_id,
                )
            limit = get_settings().api.max_request_body_bytes
            if body_size > limit:
                return _error(
                    413,
                    "REQUEST_BODY_TOO_LARGE",
                    f"request body exceeds the {limit}-byte limit",
                    request_id,
                )

        try:
            response = await call_next(request)
        except RequestBodyTooLarge:
            raise
        except Exception:
            logger.exception(
                "unhandled request failure request_id=%s method=%s path=%s",
                request_id,
                request.method,
                request.url.path,
            )
            return _error(
                500,
                "INTERNAL_ERROR",
                "an unexpected server error occurred",
                request_id,
            )

        response.headers["X-Request-Id"] = request_id
        response.headers["X-Content-Type-Options"] = "nosniff"
        duration_ms = (time.perf_counter() - started) * 1000
        logger.info(
            "request completed request_id=%s method=%s path=%s status=%d "
            "duration_ms=%.1f",
            request_id,
            request.method,
            request.url.path,
            response.status_code,
            duration_ms,
        )
        return response

    # Added last so it is the outer ASGI layer and can catch the sentinel raised
    # by the wrapped receive channel before the generic 500 handler sees it.
    app.add_middleware(RequestBodyLimitMiddleware)


__all__ = [
    "RequestBodyLimitMiddleware",
    "RequestBodyTooLarge",
    "install_http_middleware",
]
