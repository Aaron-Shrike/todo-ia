"""Shared pydantic base types for the phrases API layer (Unit 6, extended
7b.2 with the OpenAPI error-response helpers). Endpoint request/response
models are built in Unit 6b/7/7b on top of these so the id serialization
rule and the two paginated endpoints' bounds cannot drift.
"""

from __future__ import annotations

from typing import Annotated, Any

from pydantic import AfterValidator, BaseModel, Field, PlainSerializer
from pydantic_core import PydanticCustomError

PhraseId = Annotated[int, PlainSerializer(str, return_type=str, when_used="json")]
"""design.md D14: `BIGINT` internally, decimal string on the wire, typed
`string` and documented opaque in OpenAPI. Stays a plain `int` for internal
Python use; only JSON serialization renders it as a string."""


def page_limit(max_value: int) -> Any:
    """Strict-int type bounded to `[1, max_value]` -- design.md's shared
    `PageLimit` rule. `max_value` is `settings.matches_page_size`, injected
    by the caller (Unit 6b/7) so the two paginated endpoints share one
    bound. Strict typing rejects `"10"`, `true` and `10.5` -- for a JSON
    request BODY field, where a numeric-string value is a real distinction
    the client could make. NOT for a query parameter -- see `query_limit`."""
    return Annotated[int, Field(strict=True, ge=1, le=max_value)]


def query_limit(max_value: int) -> Any:
    """Int type bounded to `[1, max_value]` for a QUERY parameter (`GET
    /phrases`'s `?limit=`). Deliberately NOT `strict=True`: every query
    value arrives as text on the wire, so "strict" would reject `?limit=10`
    itself (there is no non-string form a query value could take, unlike a
    JSON body field) -- FastAPI's own lenient str->int coercion for query
    params still rejects `?limit=abc` or `?limit=10.5` as a real 422, it
    just isn't fooled into treating "the value came from a URL" as "the
    client sent the wrong JSON type"."""
    return Annotated[int, Field(ge=1, le=max_value)]


def raw_phrase_text(max_length: int) -> Any:
    """Strict-str type capped at `4 * max_length` code points -- the raw,
    pre-normalization cap, so an oversized payload fails on the schema
    before normalization/`embed()` ever runs. `max_length` is
    `settings.phrase_max_length`, injected by the caller.

    Enforced via a custom validator, NOT `Field(max_length=...)`: pydantic's
    built-in `string_too_long` error reports the RAW `4x` bound in
    `ctx.max_length`, but design.md's error registry and the api-contract
    spec's "Raw length cap" scenario both require `details.max_length` to be
    the SEMANTIC `PHRASE_MAX_LENGTH` (e.g. 280, not 1120) -- the same value
    the domain-level `PhraseTooLong` error reports. Raising our own
    `string_too_long`-typed `PydanticCustomError` with that ctx keeps
    `main.py`'s generic `_TOO_LONG_TYPES` mapping unchanged while reporting
    the value the client actually needs."""
    raw_cap = max_length * 4

    def _check_raw_cap(value: str) -> str:
        if len(value) > raw_cap:
            raise PydanticCustomError(
                "string_too_long",
                "String should have at most {max_length} characters",
                {"max_length": max_length},
            )
        return value

    return Annotated[str, Field(strict=True), AfterValidator(_check_raw_cap)]


def query_score() -> Any:
    """Bounded `[0, 1]` float type for `GET /phrases`' `min_score` query
    param (design.md's `query_score`, Unit 2 D-less shorthand). `min_score`
    has no caller-supplied max like `query_limit`/`page_limit` -- the bound
    is always `[0, 1]` (a similarity score), so it takes no argument.
    `allow_inf_nan=False` rejects `min_score=nan` with the same
    `out_of_range` reason `main.py._reason_for` already gives `ge`/`le`
    violations, instead of surfacing as a separate `finite_number` error
    type main.py's mapping does not recognize."""
    return Annotated[float, Field(ge=0, le=1, allow_inf_nan=False)]


def query_text(max_length: int) -> Any:
    """Optional string type for `GET /phrases`' `q` query parameter, capped
    at `max_length` (`settings.phrase_max_length`) directly. Unlike
    `raw_phrase_text`'s pre-normalization `4x` raw cap for a saved/embedded
    JSON body field, `q` is only ever compared against `normalized_text` --
    never stored, never embedded -- so its own raw length already IS the
    semantic bound the api-contract spec's "q over the length cap" scenario
    documents. Raises the same `string_too_long`-typed `PydanticCustomError`
    as `raw_phrase_text` so `main.py`'s generic `too_long` mapping (and its
    `details.max_length` extraction) applies unchanged."""

    def _check_length(value: str) -> str:
        if len(value) > max_length:
            raise PydanticCustomError(
                "string_too_long",
                "String should have at most {max_length} characters",
                {"max_length": max_length},
            )
        return value

    return Annotated[str, AfterValidator(_check_length)]


class ErrorDetail(BaseModel):
    """Mirrors `platform.errors.error_envelope`'s inner `"error"` object --
    a SEPARATE pydantic model (not imported from `platform.errors`, which
    is framework-free by design), used only to describe the shape in the
    generated OpenAPI document (tasks.md 7b.2)."""

    code: str
    message: str
    details: dict[str, object] | None = None


class ErrorEnvelope(BaseModel):
    """`{"error": {code, message, details?}}` -- design.md's error envelope."""

    error: ErrorDetail


def error_responses(*pairs: tuple[int, str]) -> dict[int | str, dict[str, Any]]:
    """One `responses=` dict entry per `(status_code, code)` pair, for a
    route decorator's `responses=` kwarg. The `code` string is embedded
    LITERALLY in each response's `description` (not just its schema) so the
    api-contract spec's "Every code documented" scenario -- every code in
    `ERROR_REGISTRY` appears in the OpenAPI document -- can be asserted by a
    plain text search over the generated document, with no per-status
    schema needed (every error response shares the one `ErrorEnvelope`
    shape)."""
    return {
        status: {"model": ErrorEnvelope, "description": f"Error envelope; `error.code` = `{code}`."}
        for status, code in pairs
    }
