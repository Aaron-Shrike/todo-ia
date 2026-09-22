"""Shared pydantic base types for the phrases API layer (Unit 6). Endpoint
request/response models are built in Unit 6b/7 on top of these so the id
serialization rule and the two paginated endpoints' bounds cannot drift.
"""

from __future__ import annotations

from typing import Annotated, Any

from pydantic import Field, PlainSerializer

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
    `settings.phrase_max_length`, injected by the caller."""
    return Annotated[str, Field(strict=True, max_length=max_length * 4)]
