"""Composition root (Unit 6): app factory, middleware ordering, framework
and domain error handlers. No business router yet -- Unit 6b adds the first.
"""

from __future__ import annotations

from collections.abc import Awaitable, Callable

from fastapi import FastAPI
from fastapi.exceptions import RequestValidationError
from starlette.exceptions import HTTPException as StarletteHTTPException
from starlette.middleware.cors import CORSMiddleware
from starlette.requests import Request
from starlette.responses import JSONResponse
from starlette.types import ASGIApp, Message, Receive, Scope, Send

from app.platform.errors import ERROR_REGISTRY, build_error_response, error_envelope
from app.platform.settings import Settings

_FRAMEWORK_CODES = {404: "NOT_FOUND", 405: "METHOD_NOT_ALLOWED"}
_MISSING_TYPES = {"missing"}
_OUT_OF_RANGE_TYPES = {"greater_than", "greater_than_equal", "less_than", "less_than_equal"}


class BodySizeLimitMiddleware:
    """413 `PAYLOAD_TOO_LARGE` before any JSON parsing: reject on
    `Content-Length` when present, else drain+count the body up front and
    replay it downstream through a substitute `receive`. Known limitation:
    a mid-stream `http.disconnect` before any body is folded into an empty
    replayed body (no streaming endpoint exists yet)."""

    def __init__(self, app: ASGIApp, *, max_bytes: int) -> None:
        self._app = app
        self._max_bytes = max_bytes

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self._app(scope, receive, send)
            return

        for key, value in scope.get("headers") or []:
            if key == b"content-length" and int(value) > self._max_bytes:
                await self._reject(scope, receive, send)
                return

        chunks: list[bytes] = []
        total = 0
        more_body = True
        while more_body:
            message = await receive()
            if message["type"] != "http.request":
                more_body = False
                break
            chunk = message.get("body") or b""
            total += len(chunk)
            if total > self._max_bytes:
                await self._reject(scope, receive, send)
                return
            chunks.append(chunk)
            more_body = bool(message.get("more_body", False))

        body = b"".join(chunks)
        replayed = False

        async def replay_receive() -> Message:
            nonlocal replayed
            if not replayed:
                replayed = True
                return {"type": "http.request", "body": body, "more_body": False}
            return await receive()

        await self._app(scope, replay_receive, send)

    async def _reject(self, scope: Scope, receive: Receive, send: Send) -> None:
        response = JSONResponse(
            status_code=413,
            content=error_envelope("PAYLOAD_TOO_LARGE", "request body exceeds MAX_REQUEST_BYTES"),
        )
        await response(scope, receive, send)


class CatchAllMiddleware:
    """Any exception with no registered handler -> 500 `INTERNAL_ERROR`, no
    stack trace. Hand-rolled ASGI middleware, NOT
    `@app.exception_handler(Exception)`: Starlette's own unhandled-exception
    layer (`ServerErrorMiddleware`) is always OUTERMOST and unreachable via
    `add_middleware`, so a response it built would skip `CORSMiddleware`
    entirely. This middleware sits INSIDE `CORSMiddleware` instead (see
    `create_app`), so its `send()` is the wrapped callable CORS handed down.
    Settled by this unit's contract test (design.md's "from memory" item)."""

    def __init__(self, app: ASGIApp) -> None:
        self._app = app

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self._app(scope, receive, send)
            return

        response_started = False

        async def send_wrapper(message: Message) -> None:
            nonlocal response_started
            if message["type"] == "http.response.start":
                response_started = True
            await send(message)

        try:
            await self._app(scope, receive, send_wrapper)
        except Exception:
            if response_started:
                raise  # A response is already in flight; surface the real bug.
            response = JSONResponse(
                status_code=500,
                content=error_envelope("INTERNAL_ERROR", "an unexpected error occurred"),
            )
            await response(scope, receive, send)


async def _domain_error_handler(_request: Request, exc: Exception) -> JSONResponse:
    status_code, envelope = build_error_response(exc)
    return JSONResponse(status_code=status_code, content=envelope)


async def _http_exception_handler(_request: Request, exc: StarletteHTTPException) -> JSONResponse:
    code = _FRAMEWORK_CODES.get(exc.status_code, "INTERNAL_ERROR")
    message = str(exc.detail) if exc.detail else code
    return JSONResponse(status_code=exc.status_code, content=error_envelope(code, message))


def _reason_for(error_type: str) -> str:
    if error_type in _MISSING_TYPES:
        return "required"
    if error_type in _OUT_OF_RANGE_TYPES:
        return "out_of_range"
    return "invalid_type"


async def _validation_error_handler(
    _request: Request, exc: RequestValidationError
) -> JSONResponse:
    """Covers both field-level pydantic failures and malformed JSON
    (FastAPI wraps `json.JSONDecodeError` as one `json_invalid` error with
    `loc: ("body",)`) -- both are 422 `VALIDATION_ERROR` per design.md."""
    fields = [
        {
            "field": ".".join(str(part) for part in error["loc"] if part != "body") or "body",
            "reason": _reason_for(error["type"]),
        }
        for error in exc.errors()
    ]
    return JSONResponse(
        status_code=422,
        content=error_envelope("VALIDATION_ERROR", "request validation failed", {"fields": fields}),
    )


def create_app(settings: Settings) -> FastAPI:
    app = FastAPI()

    app.add_exception_handler(StarletteHTTPException, _http_exception_handler)  # type: ignore[arg-type]
    app.add_exception_handler(RequestValidationError, _validation_error_handler)  # type: ignore[arg-type]
    for exc_type in ERROR_REGISTRY:
        handler: Callable[[Request, Exception], Awaitable[JSONResponse]] = _domain_error_handler
        app.add_exception_handler(exc_type, handler)  # type: ignore[arg-type]

    # `add_middleware` PREPENDS, so the LAST call ends up OUTERMOST (see
    # CatchAllMiddleware's docstring) -- CORS MUST be added last.
    app.add_middleware(CatchAllMiddleware)
    app.add_middleware(BodySizeLimitMiddleware, max_bytes=settings.max_request_bytes)
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origins,
        allow_methods=["GET", "POST", "OPTIONS"],
        allow_headers=["Content-Type"],
        allow_credentials=False,
    )
    return app


# design.md: Settings instantiated before the app is created (fail-fast). mypy can't
# see pydantic-settings fills required fields (e.g. database_url) from the environment.
settings = Settings()  # type: ignore[call-arg]
app = create_app(settings)
