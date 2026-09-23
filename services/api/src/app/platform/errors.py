"""`DomainError` -> HTTP registry, envelope shape, error response building
(Unit 6, design.md's "API Contract and Error Mapping").

Framework-free by design (no fastapi/starlette import): import-linter's
`forbidden` contracts check the FULL transitive import graph (Unit 2's
apply-progress note), so a domain module importing this file would break
`domain-purity` the moment this file imported fastapi.

Resolves Unit 1's open question ("where does the shared `DomainError` base
live without inverting domain -> platform?"): `EmptyPhraseText`,
`PhraseTooLong`, `EmbeddingUnavailable`, `EmbeddingTimeout` (Unit 1) and
`InvalidCursor` (Unit 2c) deliberately do NOT inherit from `DomainError` --
that would require those domain modules to import this platform module.
Instead `ERROR_REGISTRY` is keyed by CONCRETE exception type, and
`main.py` registers the SAME handler once per key via
`add_exception_handler`; Starlette dispatches by walking
`type(exc).__mro__` against every REGISTERED key (not only base classes),
so N registrations of one function equal design.md's "single
`@app.exception_handler(DomainError)`" without touching any merged domain
file. `DomainError` stays available for future errors to opt into.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass

from app.modules.phrases.domain.cursor import InvalidCursor
from app.modules.phrases.domain.errors import EmptyPhraseText, PhraseTooLong
from app.modules.phrases.domain.list_cursor import InvalidListCursor
from app.modules.similarity.domain.errors import EmbeddingTimeout, EmbeddingUnavailable


class DomainError(Exception):
    """Optional base for FUTURE domain errors; see the module docstring for
    why the errors already shipped by Units 1/2c do not inherit from it."""


@dataclass(frozen=True)
class ErrorMapping:
    status_code: int
    code: str


def error_envelope(
    code: str, message: str, details: dict[str, object] | None = None
) -> dict[str, object]:
    """design.md: `{"error": {"code", "message", "details"?}}`."""
    error: dict[str, object] = {"code": code, "message": message}
    if details is not None:
        error["details"] = details
    return {"error": error}


def _empty_text_details(_exc: Exception) -> dict[str, object]:
    return {"fields": [{"field": "text", "reason": "empty"}]}


def _too_long_details(exc: Exception) -> dict[str, object]:
    assert isinstance(exc, PhraseTooLong)
    return {"fields": [{"field": "text", "reason": "too_long"}], "max_length": exc.max_length}


ERROR_REGISTRY: dict[type[Exception], ErrorMapping] = {
    InvalidCursor: ErrorMapping(400, "INVALID_CURSOR"),
    InvalidListCursor: ErrorMapping(400, "INVALID_CURSOR"),
    EmptyPhraseText: ErrorMapping(422, "VALIDATION_ERROR"),
    PhraseTooLong: ErrorMapping(422, "VALIDATION_ERROR"),
    EmbeddingUnavailable: ErrorMapping(503, "EMBEDDING_UNAVAILABLE"),
    EmbeddingTimeout: ErrorMapping(504, "EMBEDDING_TIMEOUT"),
}

_DETAILS_BUILDERS: dict[type[Exception], Callable[[Exception], dict[str, object]]] = {
    EmptyPhraseText: _empty_text_details,
    PhraseTooLong: _too_long_details,
}

_DEFAULT_MESSAGES: dict[str, str] = {
    "INVALID_CURSOR": "the cursor is malformed or does not match this query",
    "VALIDATION_ERROR": "request validation failed",
    "EMBEDDING_UNAVAILABLE": "the embedding provider is unavailable",
    "EMBEDDING_TIMEOUT": "the embedding provider timed out",
}


def build_error_response(exc: Exception) -> tuple[int, dict[str, object]]:
    """Look up `type(exc)` (exact match -- every registry key is a leaf
    domain exception with no further subclasses) and build `(status_code,
    envelope)`. Raises `KeyError` for an unregistered type; callers only
    invoke this for types they registered a handler for (see `main.py`)."""
    mapping = ERROR_REGISTRY[type(exc)]
    details_builder = _DETAILS_BUILDERS.get(type(exc))
    details = details_builder(exc) if details_builder else None
    message = _DEFAULT_MESSAGES[mapping.code]
    return mapping.status_code, error_envelope(mapping.code, message, details)
