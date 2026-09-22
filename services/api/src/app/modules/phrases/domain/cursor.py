"""Opaque wire cursor codec (tasks.md Unit 2c / 2c.1, design.md's "Cursor
format" section).

`base64url({"v":1, "t":<comparison form>, "d":<raw distance>, "i":<id>,
"th":<threshold>})` — opaque to clients (OpenAPI documents it as such;
clients MUST NOT parse it). Pure, framework-free (domain layer): the
encoded-length cap is parameterized by `max_length`, never read from
settings directly — `max_encoded_length(PHRASE_MAX_LENGTH)` lets the
caller (Unit 3's `ListMatches`, wired from `platform/settings.py` in
Unit 6) derive the bound without this module importing pydantic-settings.

**Distinct from `phrases.contracts.MatchCursor`.** This module's
`CursorEnvelope` carries the full wire envelope (`v`, `t`, `d`, `i`, `th`)
validated here, strictly, before anything is embedded (design.md: "decode
-> validate fields -> compare t and th -> embed -> query"). Only AFTER the
`t` (comparison-form binding) and `th` (threshold binding) checks pass does
the calling use case (Unit 3, not yet built) construct the narrower
`MatchCursor(distance=envelope.d, id=envelope.i)` that
`PhraseRepository.find_matches` actually consumes — see `phrases/contracts.py`'s
`MatchCursor` docstring, which names this module as the validator of `t`/`th`
by design. The two names are deliberately different (`CursorEnvelope` here,
`MatchCursor` there) precisely so they can't be confused for each other.

**Strict validation, per rule** (design.md, verbatim): base64url with no
tolerated garbage; a JSON *object* (parse with `NaN`/`Infinity` literals
rejected); exactly the five keys; `v` equals the supported version; `t` is
a string; `d` is a finite number in `[0, 2]`; `i` is a positive integer
that fits int64 (booleans rejected); `th` is a finite number in `[0, 1]`;
the encoded length does not exceed `max_length`. **Any** violation raises
`InvalidCursor` — the caller (Unit 3/API layer) maps it to `400
INVALID_CURSOR`.
"""

from __future__ import annotations

import base64
import binascii
import json
import math
import re
from dataclasses import dataclass

CURSOR_VERSION = 1

_INT64_MAX = 2**63 - 1
_MAX_DISTANCE = 2.0  # design.md: 'd' is a finite number in [0, 2]
_MAX_THRESHOLD = 1.0  # design.md: 'th' is a finite number in [0, 1]

_REQUIRED_KEYS = frozenset({"v", "t", "d", "i", "th"})

# base64url alphabet only (no '+', '/', whitespace, or other stray bytes);
# padding is normalized by this module, so callers never send '='.
_BASE64URL_PATTERN = re.compile(r"^[A-Za-z0-9_-]*$")


class InvalidCursor(Exception):
    """Any cursor decode/validation failure — design.md: "**Any**
    violation — malformed, wrong type, out of range, extra or missing key,
    oversized — is `400 INVALID_CURSOR`"."""


@dataclass(frozen=True)
class CursorEnvelope:
    """The fully decoded, validated wire cursor. `t` is the comparison
    form (design.md: "the same string that keys the cache and feeds
    `embed()`"); `d` is the RAW distance of the last delivered row (never a
    rounded score); `i` is an integer id even though the API serializes ids
    as strings (the cursor is opaque, no client ever sees it); `th` is the
    threshold the page sequence was opened with, carried so a threshold
    change mid-scroll cannot corrupt paging."""

    v: int
    t: str
    d: float
    i: int
    th: float


def max_encoded_length(phrase_max_length: int) -> int:
    """design.md "Cursor format": `4 * ceil((12 * PHRASE_MAX_LENGTH + 128) / 3)`
    characters — worst-case casefold expansion x UTF-8 width, base64-inflated."""
    return 4 * math.ceil((12 * phrase_max_length + 128) / 3)


def encode_cursor(*, t: str, d: float, i: int, th: float, v: int = CURSOR_VERSION) -> str:
    """Encode a cursor for a `find_matches` page continuation. Trusted
    internal input (the repository's own `Match.distance`/`Match.id` and
    the use case's own `t`/`th`) — validation is `decode_cursor`'s job, not
    this direction's."""
    payload = {"v": v, "t": t, "d": d, "i": i, "th": th}
    raw = json.dumps(payload, separators=(",", ":")).encode("utf-8")
    return base64.urlsafe_b64encode(raw).decode("ascii").rstrip("=")


def decode_cursor(raw: str, *, max_length: int) -> CursorEnvelope:
    """Strictly decode and validate a wire cursor. Raises `InvalidCursor`
    on any violation — see this module's docstring for the full rule list.
    Cheap checks (length, base64, JSON shape) run before any field
    validation, so a malformed cursor is rejected before the caller ever
    calls `embed()` (design.md's zero-forward-pass guarantee)."""
    if len(raw) > max_length:
        raise InvalidCursor("cursor exceeds the maximum encoded length")

    decoded_bytes = _decode_base64url(raw)
    payload = _parse_json_object(decoded_bytes)

    keys = set(payload.keys())
    if keys != _REQUIRED_KEYS:
        raise InvalidCursor("cursor payload has missing or extra keys")

    v = payload["v"]
    if v != CURSOR_VERSION:
        raise InvalidCursor("unsupported cursor version")

    t = payload["t"]
    if not isinstance(t, str):
        raise InvalidCursor("cursor field 't' must be a string")

    d = _require_finite_number(payload["d"], field="d")
    if not (0.0 <= d <= _MAX_DISTANCE):
        raise InvalidCursor("cursor field 'd' is out of range [0, 2]")

    i = payload["i"]
    if isinstance(i, bool) or not isinstance(i, int):
        raise InvalidCursor("cursor field 'i' must be an integer")
    if not (1 <= i <= _INT64_MAX):
        raise InvalidCursor("cursor field 'i' must be a positive int64")

    th = _require_finite_number(payload["th"], field="th")
    if not (0.0 <= th <= _MAX_THRESHOLD):
        raise InvalidCursor("cursor field 'th' is out of range [0, 1]")

    return CursorEnvelope(v=v, t=t, d=d, i=i, th=th)


def _decode_base64url(raw: str) -> bytes:
    if not _BASE64URL_PATTERN.fullmatch(raw):
        raise InvalidCursor("cursor is not valid base64url")
    padded = raw + "=" * (-len(raw) % 4)
    try:
        return base64.urlsafe_b64decode(padded)
    except (binascii.Error, ValueError) as exc:
        raise InvalidCursor("cursor is not valid base64url") from exc


def _reject_non_finite_constant(constant: str) -> float:
    # json.loads' parse_constant hook fires for the non-standard NaN /
    # Infinity / -Infinity literals it otherwise accepts silently.
    raise InvalidCursor(f"cursor payload contains a non-finite literal: {constant}")


def _parse_json_object(raw_bytes: bytes) -> dict[str, object]:
    try:
        text = raw_bytes.decode("utf-8")
    except UnicodeDecodeError as exc:
        raise InvalidCursor("cursor payload is not valid utf-8") from exc
    try:
        payload = json.loads(text, parse_constant=_reject_non_finite_constant)
    except json.JSONDecodeError as exc:
        raise InvalidCursor("cursor payload is not valid json") from exc
    if not isinstance(payload, dict):
        raise InvalidCursor("cursor payload must be a JSON object")
    return payload


def _require_finite_number(value: object, *, field: str) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise InvalidCursor(f"cursor field '{field}' must be a number")
    number = float(value)
    if math.isnan(number) or math.isinf(number):
        raise InvalidCursor(f"cursor field '{field}' must be finite")
    return number
