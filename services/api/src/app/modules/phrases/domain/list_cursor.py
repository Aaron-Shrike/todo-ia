"""Opaque wire cursor codec for `GET /phrases`'s pagination — distinct from
`domain/cursor.py`'s `CursorEnvelope` (that one binds a comparison form and
threshold to a `find_matches` page sequence; this list has neither: it is
always the same `(created_at, id)` DESC ordering for everyone, so the wire
cursor only needs to carry a keyset position).

`base64url({"v":1, "ca":<ISO 8601 created_at>, "i":<id>})` — opaque to
clients, same strictness rules as the matches cursor (no tolerated garbage,
exactly these keys, a finite/valid value per field) — any violation is
`400 INVALID_CURSOR` (`InvalidListCursor`, mapped at the API layer to the
same error code the matches cursor uses, since both mean "the pagination
you're continuing no longer makes sense, restart").
"""

from __future__ import annotations

import base64
import binascii
import json
import re
from dataclasses import dataclass
from datetime import datetime

CURSOR_VERSION = 1

_INT64_MAX = 2**63 - 1
_REQUIRED_KEYS = frozenset({"v", "ca", "i"})
_BASE64URL_PATTERN = re.compile(r"^[A-Za-z0-9_-]*$")
_MAX_ENCODED_LENGTH = 512  # generous fixed bound: payload is a fixed shape, never user-sized


class InvalidListCursor(Exception):
    """Any cursor decode/validation failure — the caller maps this to
    `400 INVALID_CURSOR`, same as `domain.cursor.InvalidCursor`."""


@dataclass(frozen=True)
class ListCursorEnvelope:
    v: int
    created_at: datetime
    id: int


def encode_list_cursor(*, created_at: datetime, id: int, v: int = CURSOR_VERSION) -> str:
    """Encode a cursor for a `list_page` continuation. Trusted internal
    input (the repository's own `Phrase.created_at`/`Phrase.id`) —
    validation is `decode_list_cursor`'s job, not this direction's."""
    payload = {"v": v, "ca": created_at.isoformat(), "i": id}
    raw = json.dumps(payload, separators=(",", ":")).encode("utf-8")
    return base64.urlsafe_b64encode(raw).decode("ascii").rstrip("=")


def decode_list_cursor(raw: str) -> ListCursorEnvelope:
    """Strictly decode and validate a wire cursor. Raises
    `InvalidListCursor` on any violation."""
    if len(raw) > _MAX_ENCODED_LENGTH:
        raise InvalidListCursor("cursor exceeds the maximum encoded length")

    decoded_bytes = _decode_base64url(raw)
    payload = _parse_json_object(decoded_bytes)

    keys = set(payload.keys())
    if keys != _REQUIRED_KEYS:
        raise InvalidListCursor("cursor payload has missing or extra keys")

    v = payload["v"]
    if v != CURSOR_VERSION:
        raise InvalidListCursor("unsupported cursor version")

    ca = payload["ca"]
    if not isinstance(ca, str):
        raise InvalidListCursor("cursor field 'ca' must be a string")
    try:
        created_at = datetime.fromisoformat(ca)
    except ValueError as exc:
        raise InvalidListCursor("cursor field 'ca' must be an ISO 8601 timestamp") from exc

    i = payload["i"]
    if isinstance(i, bool) or not isinstance(i, int):
        raise InvalidListCursor("cursor field 'i' must be an integer")
    if not (1 <= i <= _INT64_MAX):
        raise InvalidListCursor("cursor field 'i' must be a positive int64")

    return ListCursorEnvelope(v=v, created_at=created_at, id=i)


def _decode_base64url(raw: str) -> bytes:
    if not _BASE64URL_PATTERN.fullmatch(raw):
        raise InvalidListCursor("cursor is not valid base64url")
    padded = raw + "=" * (-len(raw) % 4)
    try:
        return base64.urlsafe_b64decode(padded)
    except (binascii.Error, ValueError) as exc:
        raise InvalidListCursor("cursor is not valid base64url") from exc


def _reject_non_finite_constant(constant: str) -> float:
    raise InvalidListCursor(f"cursor payload contains a non-finite literal: {constant}")


def _parse_json_object(raw_bytes: bytes) -> dict[str, object]:
    try:
        text = raw_bytes.decode("utf-8")
    except UnicodeDecodeError as exc:
        raise InvalidListCursor("cursor payload is not valid utf-8") from exc
    try:
        payload = json.loads(text, parse_constant=_reject_non_finite_constant)
    except json.JSONDecodeError as exc:
        raise InvalidListCursor("cursor payload is not valid json") from exc
    if not isinstance(payload, dict):
        raise InvalidListCursor("cursor payload must be a JSON object")
    return payload
