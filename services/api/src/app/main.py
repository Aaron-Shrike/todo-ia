"""Composition root (Unit 6 + 6b + 8): app factory, middleware ordering,
framework/domain error handlers, the business routers plus `/health`, and
(Unit 8) the production `lifespan` hook that wires a REAL embedding
provider and repository.

`create_app`'s `lifespan` parameter defaults to `None`, so every EXISTING
test (which calls `create_app(settings)` with no lifespan and sets
`app.state.phrases`/`app.state.health` directly -- see `test_
validate_health.py`'s `_client()`, unchanged since Unit 6b) keeps behaving
identically: `TestClient` only ever runs a `lifespan` when used as a
context manager, which no test in this codebase does. Only the module-level
`app` object at the bottom of this file gets the real `_lifespan`.

`_lifespan` is **not exercised end to end in this environment**: no live
Postgres and no real `sentence-transformers` model are available here (see
apply-progress.md's Unit 8 section) -- it is written and covered by the
passthrough-wiring test in `tests/unit/test_main.py`, not run against real
infrastructure in this batch. Its pure SEQUENCING (Unit 8 fix-pass,
reliability CRITICAL finding #2) -- the order of operations, and that a
dimension mismatch short-circuits warmup/wiring/the health flip -- is
extracted to `platform/boot_sequence.py::run_boot_sequence` and IS
unit-tested there with fakes, independent of sqlalchemy/postgres/torch
being installed; `_lifespan` itself is now a thin wrapper supplying the
real I/O callables to that pure core.
"""

from __future__ import annotations

from collections.abc import AsyncIterator, Awaitable, Callable
from contextlib import AbstractAsyncContextManager, asynccontextmanager
from dataclasses import asdict

from fastapi import FastAPI
from fastapi.exceptions import RequestValidationError
from starlette.exceptions import HTTPException as StarletteHTTPException
from starlette.middleware.cors import CORSMiddleware
from starlette.requests import Request
from starlette.responses import JSONResponse
from starlette.types import ASGIApp, Message, Receive, Scope, Send

from app.modules.phrases.api.router import build_phrases_router, build_validate_router
from app.modules.phrases.container import PhrasesContainer, build_phrases_container
from app.modules.similarity.adapters.bounded import BoundedEmbeddingProvider
from app.modules.similarity.adapters.caching import CachingEmbeddingProvider
from app.modules.similarity.adapters.sentence_transformers import load_sentence_transformer
from app.modules.similarity.container import wrap_with_cache
from app.modules.similarity.contracts import EmbeddingProvider, SimilarityPolicy
from app.platform.boot_sequence import run_boot_sequence
from app.platform.embedding_boot import (
    check_database_reachable,
    check_dimension_coherence,
    read_vector_column_dimensions,
)
from app.platform.errors import ERROR_REGISTRY, build_error_response, error_envelope
from app.platform.health import HealthState
from app.platform.health import router as health_router
from app.platform.settings import Settings

_HEALTH_SENTINEL_TEXT = "todo-ia health warmup sentinel"

_FRAMEWORK_CODES = {404: "NOT_FOUND", 405: "METHOD_NOT_ALLOWED"}
_MISSING_TYPES = {"missing"}
_TOO_LONG_TYPES = {"string_too_long"}
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
    if error_type in _TOO_LONG_TYPES:
        return "too_long"
    if error_type in _OUT_OF_RANGE_TYPES:
        return "out_of_range"
    return "invalid_type"


async def _validation_error_handler(
    _request: Request, exc: RequestValidationError
) -> JSONResponse:
    """Covers both field-level pydantic failures and malformed JSON
    (FastAPI wraps `json.JSONDecodeError` as one `json_invalid` error with
    `loc: ("body",)`) -- both are 422 `VALIDATION_ERROR` per design.md. A
    schema-level `max_length` bound (e.g. `raw_phrase_text()`'s raw 4x cap)
    maps to reason `too_long` with a top-level `details.max_length`, taken
    from pydantic's own `ctx.max_length` (design.md line 937: "schema field
    bound -> too_long")."""
    errors = exc.errors()
    fields = [
        {
            "field": ".".join(str(part) for part in error["loc"] if part != "body") or "body",
            "reason": _reason_for(error["type"]),
        }
        for error in errors
    ]
    details: dict[str, object] = {"fields": fields}
    for error in errors:
        if error["type"] in _TOO_LONG_TYPES:
            max_length = error.get("ctx", {}).get("max_length")
            if max_length is not None:
                details["max_length"] = max_length
            break
    return JSONResponse(
        status_code=422,
        content=error_envelope("VALIDATION_ERROR", "request validation failed", details),
    )


def create_app(
    settings: Settings,
    *,
    lifespan: Callable[[FastAPI], AbstractAsyncContextManager[None]] | None = None,
) -> FastAPI:
    app = FastAPI(lifespan=lifespan)

    app.add_exception_handler(StarletteHTTPException, _http_exception_handler)  # type: ignore[arg-type]
    app.add_exception_handler(RequestValidationError, _validation_error_handler)  # type: ignore[arg-type]
    for exc_type in ERROR_REGISTRY:
        handler: Callable[[Request, Exception], Awaitable[JSONResponse]] = _domain_error_handler
        app.add_exception_handler(exc_type, handler)  # type: ignore[arg-type]

    app.include_router(
        build_validate_router(
            phrase_max_length=settings.phrase_max_length,
            matches_page_size=settings.matches_page_size,
        )
    )
    app.include_router(
        build_phrases_router(
            phrase_max_length=settings.phrase_max_length,
            matches_page_size=settings.matches_page_size,
        )
    )
    app.include_router(health_router)
    # Not ready until `lifespan` (Unit 8, real deployments only) runs;
    # `app.state.phrases` is deliberately left unset (a hit on
    # `/phrases/validate` 500s until then). Every test sets both directly,
    # bypassing this -- `lifespan` never runs unless `TestClient` is used
    # as a context manager, which no test in this codebase does.
    app.state.health = HealthState(
        check_database=lambda: False,
        model_ready=False,
        dimensions=settings.embedding_dimensions,
        embedding_model=settings.embedding_model,
        embedding_cache=lambda: None,
    )

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


@asynccontextmanager
async def _lifespan(app: FastAPI, settings: Settings) -> AsyncIterator[None]:
    """Unit 8 production startup, restructured in the Unit 8 fix-pass
    (reliability CRITICAL finding #2). The pure SEQUENCING decision --
    load the model, check the `phrases.embedding` column's typmod against
    the loaded provider and `EMBEDDING_DIMENSIONS` (a mismatch ABORTS boot,
    short-circuiting everything after it -- `EmbeddingDimensionMismatch`
    propagates out of `run_boot_sequence`, which FastAPI/uvicorn surfaces
    as a failed startup, a non-zero exit), warm the model with one
    fixed-sentinel embed, then wire the real `PgVectorUnitOfWorkFactory`
    (closing the gap `main.py`'s Unit 6b docstring named: "until Unit 8
    wires a real container") and flip `app.state.health` to ready -- now
    lives in `platform/boot_sequence.py::run_boot_sequence`, unit-tested
    THERE with fakes and no sqlalchemy/postgres/torch installed. This
    function is the THIN wrapper that supplies the REAL I/O callables
    (`create_engine`, `load_sentence_transformer`, `PgVectorUnitOfWork
    Factory`) that pure core needs.

    `create_engine`/`PgVectorUnitOfWorkFactory` are imported HERE, lazily,
    not at module level (same pattern as `adapters/sentence_transformers.
    py::load_sentence_transformer`): `pgvector_repository.py` imports
    `sqlalchemy` at module level, and this dev venv does not have
    `sqlalchemy` installed (see apply-progress.md's Unit 8 section) -- a
    top-level import here would break every test that imports `app.main`,
    which is nearly all of them. No test in this codebase triggers this
    function (`TestClient` only runs `lifespan` as a context manager, which
    none of them do), so the lazy import is never attempted during a test
    run in this environment.

    **Not exercised end to end in this batch**: no live Postgres and no
    real model are available here -- this function's OWN wiring is
    written and covered by `tests/unit/test_main.py`'s passthrough-wiring
    test only; the SEQUENCING it delegates to is covered by `tests/unit/
    platform/test_boot_sequence.py`.
    """
    from sqlalchemy import create_engine

    from app.modules.phrases.adapters.pgvector_repository import PgVectorUnitOfWorkFactory

    engine = create_engine(settings.database_url)
    # Captured by `_load_model` below so the `finally` block can shut its
    # `ThreadPoolExecutor` down on exit (Unit 8 fix-pass, reliability
    # suggestion #11) -- held separately from the (possibly cache-wrapped)
    # provider `run_boot_sequence` passes around, since only THIS concrete
    # layer owns a resource needing explicit shutdown.
    bounded_provider: BoundedEmbeddingProvider | None = None

    def _load_model() -> EmbeddingProvider:
        nonlocal bounded_provider
        base = load_sentence_transformer(settings)
        bounded_provider = BoundedEmbeddingProvider(
            base,
            timeout_seconds=settings.embedding_timeout_seconds,
            max_concurrency=settings.embedding_max_concurrency,
        )
        return wrap_with_cache(bounded_provider, capacity=settings.embedding_cache_size)

    def _check_dimensions(provider: EmbeddingProvider) -> None:
        with engine.connect() as connection:
            typmod = read_vector_column_dimensions(connection, table="phrases", column="embedding")
        check_dimension_coherence(
            typmod=typmod,
            provider_dimensions=provider.dimensions,
            configured_dimensions=settings.embedding_dimensions,
        )

    def _warmup(provider: EmbeddingProvider) -> None:
        provider.embed(_HEALTH_SENTINEL_TEXT)  # one forward pass

    def _build_container(provider: EmbeddingProvider) -> PhrasesContainer:
        uow_factory = PgVectorUnitOfWorkFactory(
            engine, ef_search=settings.hnsw_ef_search, lock_timeout_ms=settings.lock_timeout_ms
        )
        container = build_phrases_container(
            embedder=provider,
            # `PgVectorUnitOfWork.repo: PgVectorPhraseRepository` vs. the
            # `UnitOfWork` Protocol's `repo: PhraseRepository` -- mypy
            # treats a Protocol's mutable attribute as INVARIANT (it could
            # be read OR written through the Protocol type), so a concrete
            # subtype-typed attribute never structurally satisfies it, even
            # though `PgVectorPhraseRepository` fully implements
            # `PhraseRepository` at runtime. Pre-existing since Unit 5b;
            # this is the first `src/` (not test) call site to assign
            # `PgVectorUnitOfWorkFactory` to a `UnitOfWorkFactory`-typed
            # parameter, so it is the first to surface it.
            uow_factory=uow_factory,  # type: ignore[arg-type]
            policy=SimilarityPolicy(threshold=settings.similarity_threshold),
            phrase_max_length=settings.phrase_max_length,
            matches_page_size=settings.matches_page_size,
        )

        def _cache_snapshot() -> dict[str, int] | None:
            return (
                asdict(provider.stats) if isinstance(provider, CachingEmbeddingProvider) else None
            )

        app.state.health = HealthState(
            check_database=lambda: check_database_reachable(engine),
            model_ready=True,
            dimensions=provider.dimensions,
            embedding_model=settings.embedding_model,
            embedding_cache=_cache_snapshot,
        )
        return container

    try:
        app.state.phrases = run_boot_sequence(
            load_model=_load_model,
            check_dimensions=_check_dimensions,
            warmup=_warmup,
            build_container=_build_container,
        )
        yield
    finally:
        if bounded_provider is not None:
            bounded_provider.close()  # Unit 8 fix-pass, reliability suggestion #11
        engine.dispose()


# design.md: Settings instantiated before the app is created (fail-fast). mypy can't
# see pydantic-settings fills required fields (e.g. database_url) from the environment.
settings = Settings()  # type: ignore[call-arg]
app = create_app(settings, lifespan=lambda app: _lifespan(app, settings))
