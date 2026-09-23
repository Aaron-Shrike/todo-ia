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
    bound. Strict typing rejects `"10"`, `true` and `10.5`."""
    return Annotated[int, Field(strict=True, ge=1, le=max_value)]


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
