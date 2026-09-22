"""Unit tests for `phrases/domain/cursor.py` (tasks.md Unit 2c / 2c.1).

Scenarios from design.md's "Cursor format" section: the opaque wire cursor
`base64url({"v":1,"t":<comparison form>,"d":<raw distance>,"i":<id>,
"th":<threshold>})`. One test per validation rule, per the task table; every
violation raises `InvalidCursor` — design.md: "**Any** violation —
malformed, wrong type, out of range, extra or missing key, oversized — is
`400 INVALID_CURSOR`."

This module stays framework-free (domain layer): the encoded-length cap is
parameterized by `max_length`, not read from settings (Unit 6 owns
`platform/settings.py` and will pass `max_encoded_length(PHRASE_MAX_LENGTH)`
in).
"""

from __future__ import annotations

import base64
import json
import math

import pytest

from app.modules.phrases.domain.cursor import (
    CURSOR_VERSION,
    CursorEnvelope,
    InvalidCursor,
    decode_cursor,
    encode_cursor,
    max_encoded_length,
)

_DEFAULT_MAX_LENGTH = max_encoded_length(280)  # PHRASE_MAX_LENGTH default, per .env.example


def _b64url(raw_bytes: bytes) -> str:
    return base64.urlsafe_b64encode(raw_bytes).decode("ascii").rstrip("=")


def _cursor_bytes(payload: dict) -> bytes:
    # allow_nan=True so the NaN/Infinity test rows can produce the literal
    # (non-standard) JSON tokens design.md says decoding MUST reject.
    return json.dumps(payload, allow_nan=True).encode("utf-8")


def _valid_payload(**overrides: object) -> dict:
    payload = {"v": CURSOR_VERSION, "t": "comprar leche", "d": 0.2001, "i": 42, "th": 0.8}
    payload.update(overrides)
    return payload


def test_round_trip_encode_then_decode_preserves_every_field() -> None:
    encoded = encode_cursor(t="comprar leche", d=0.2001, i=42, th=0.8)
    decoded = decode_cursor(encoded, max_length=_DEFAULT_MAX_LENGTH)
    assert decoded == CursorEnvelope(v=CURSOR_VERSION, t="comprar leche", d=0.2001, i=42, th=0.8)


def test_round_trip_with_different_values_proves_it_is_not_hardcoded() -> None:
    encoded = encode_cursor(t="otra frase distinta", d=1.5, i=999, th=0.0)
    decoded = decode_cursor(encoded, max_length=_DEFAULT_MAX_LENGTH)
    assert decoded == CursorEnvelope(
        v=CURSOR_VERSION, t="otra frase distinta", d=1.5, i=999, th=0.0
    )


def test_bad_base64url_is_rejected() -> None:
    with pytest.raises(InvalidCursor):
        decode_cursor("not!!valid==base64 url***", max_length=_DEFAULT_MAX_LENGTH)


def test_non_object_json_payload_is_rejected() -> None:
    encoded = _b64url(json.dumps([1, 2, 3]).encode("utf-8"))
    with pytest.raises(InvalidCursor):
        decode_cursor(encoded, max_length=_DEFAULT_MAX_LENGTH)


def test_nan_literal_at_the_top_level_is_rejected() -> None:
    encoded = _b64url(b"NaN")
    with pytest.raises(InvalidCursor):
        decode_cursor(encoded, max_length=_DEFAULT_MAX_LENGTH)


def test_infinity_literal_in_a_field_is_rejected() -> None:
    raw = b'{"v":1,"t":"x","d":Infinity,"i":1,"th":0.5}'
    encoded = _b64url(raw)
    with pytest.raises(InvalidCursor):
        decode_cursor(encoded, max_length=_DEFAULT_MAX_LENGTH)


def test_wrong_version_is_rejected() -> None:
    encoded = _b64url(_cursor_bytes(_valid_payload(v=2)))
    with pytest.raises(InvalidCursor):
        decode_cursor(encoded, max_length=_DEFAULT_MAX_LENGTH)


def test_non_string_t_is_rejected() -> None:
    encoded = _b64url(_cursor_bytes(_valid_payload(t=123)))
    with pytest.raises(InvalidCursor):
        decode_cursor(encoded, max_length=_DEFAULT_MAX_LENGTH)


def test_negative_d_is_rejected() -> None:
    encoded = _b64url(_cursor_bytes(_valid_payload(d=-0.0001)))
    with pytest.raises(InvalidCursor):
        decode_cursor(encoded, max_length=_DEFAULT_MAX_LENGTH)


def test_d_over_two_is_rejected() -> None:
    encoded = _b64url(_cursor_bytes(_valid_payload(d=2.0001)))
    with pytest.raises(InvalidCursor):
        decode_cursor(encoded, max_length=_DEFAULT_MAX_LENGTH)


def test_d_as_a_string_is_rejected() -> None:
    encoded = _b64url(_cursor_bytes(_valid_payload(d="0.5")))
    with pytest.raises(InvalidCursor):
        decode_cursor(encoded, max_length=_DEFAULT_MAX_LENGTH)


def test_i_equal_to_zero_is_rejected() -> None:
    encoded = _b64url(_cursor_bytes(_valid_payload(i=0)))
    with pytest.raises(InvalidCursor):
        decode_cursor(encoded, max_length=_DEFAULT_MAX_LENGTH)


def test_negative_i_is_rejected() -> None:
    encoded = _b64url(_cursor_bytes(_valid_payload(i=-1)))
    with pytest.raises(InvalidCursor):
        decode_cursor(encoded, max_length=_DEFAULT_MAX_LENGTH)


def test_i_over_int64_max_is_rejected() -> None:
    encoded = _b64url(_cursor_bytes(_valid_payload(i=2**63)))
    with pytest.raises(InvalidCursor):
        decode_cursor(encoded, max_length=_DEFAULT_MAX_LENGTH)


def test_i_as_a_boolean_is_rejected() -> None:
    raw = b'{"v":1,"t":"x","d":0.2,"i":true,"th":0.5}'
    encoded = _b64url(raw)
    with pytest.raises(InvalidCursor):
        decode_cursor(encoded, max_length=_DEFAULT_MAX_LENGTH)


def test_th_below_zero_is_rejected() -> None:
    encoded = _b64url(_cursor_bytes(_valid_payload(th=-0.0001)))
    with pytest.raises(InvalidCursor):
        decode_cursor(encoded, max_length=_DEFAULT_MAX_LENGTH)


def test_th_above_one_is_rejected() -> None:
    encoded = _b64url(_cursor_bytes(_valid_payload(th=1.0001)))
    with pytest.raises(InvalidCursor):
        decode_cursor(encoded, max_length=_DEFAULT_MAX_LENGTH)


def test_th_non_finite_is_rejected() -> None:
    raw = b'{"v":1,"t":"x","d":0.2,"i":1,"th":NaN}'
    encoded = _b64url(raw)
    with pytest.raises(InvalidCursor):
        decode_cursor(encoded, max_length=_DEFAULT_MAX_LENGTH)


def test_missing_key_is_rejected() -> None:
    payload = _valid_payload()
    del payload["th"]
    encoded = _b64url(_cursor_bytes(payload))
    with pytest.raises(InvalidCursor):
        decode_cursor(encoded, max_length=_DEFAULT_MAX_LENGTH)


def test_extra_key_is_rejected() -> None:
    encoded = _b64url(_cursor_bytes(_valid_payload(extra="unexpected")))
    with pytest.raises(InvalidCursor):
        decode_cursor(encoded, max_length=_DEFAULT_MAX_LENGTH)


def test_oversized_cursor_is_rejected() -> None:
    encoded = encode_cursor(t="x" * 10_000, d=0.2, i=1, th=0.5)
    with pytest.raises(InvalidCursor):
        decode_cursor(encoded, max_length=_DEFAULT_MAX_LENGTH)


def test_max_encoded_length_matches_design_formula() -> None:
    # design.md "Cursor format": 4 * ceil((12 * PHRASE_MAX_LENGTH + 128) / 3)
    assert max_encoded_length(280) == 4 * math.ceil((12 * 280 + 128) / 3)
    # Triangulate with a different PHRASE_MAX_LENGTH to prove it is a real formula.
    assert max_encoded_length(4000) == 4 * math.ceil((12 * 4000 + 128) / 3)
