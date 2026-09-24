"""Unit 6.2: `platform/errors.py`'s registry and envelope shape. HTTP-level
wiring (framework handlers, middleware order, CORS) is exercised end to end
by `tests/contract/test_framework_errors.py` (task 6.3); this file only
proves the framework-free registry/envelope logic in isolation.
"""

from __future__ import annotations

import pytest

from app.modules.phrases.domain.cursor import InvalidCursor
from app.modules.phrases.domain.errors import EmptyPhraseText, PhraseTooLong
from app.modules.similarity.domain.errors import EmbeddingTimeout, EmbeddingUnavailable
from app.platform.errors import build_error_response, error_envelope

pytestmark = pytest.mark.unit


def test_envelope_shape_without_details() -> None:
    assert error_envelope("SOME_CODE", "a message") == {
        "error": {"code": "SOME_CODE", "message": "a message"}
    }


def test_envelope_shape_with_details() -> None:
    envelope = error_envelope("SOME_CODE", "a message", {"k": "v"})
    assert envelope["error"]["details"] == {"k": "v"}  # type: ignore[index]


@pytest.mark.parametrize(
    ("exc", "status_code", "code"),
    [
        (InvalidCursor("bad"), 400, "INVALID_CURSOR"),
        (EmptyPhraseText(), 422, "VALIDATION_ERROR"),
        (PhraseTooLong(max_length=280), 422, "VALIDATION_ERROR"),
        (EmbeddingUnavailable(), 503, "EMBEDDING_UNAVAILABLE"),
        (EmbeddingTimeout(), 504, "EMBEDDING_TIMEOUT"),
    ],
)
def test_registry_mapping(exc: Exception, status_code: int, code: str) -> None:
    resolved_status, envelope = build_error_response(exc)
    assert resolved_status == status_code
    assert envelope["error"]["code"] == code  # type: ignore[index]


def test_empty_phrase_text_details() -> None:
    _, envelope = build_error_response(EmptyPhraseText())
    assert envelope["error"]["details"] == {  # type: ignore[index]
        "fields": [{"field": "text", "reason": "empty"}]
    }


def test_phrase_too_long_details_carry_max_length() -> None:
    _, envelope = build_error_response(PhraseTooLong(max_length=280))
    assert envelope["error"]["details"] == {  # type: ignore[index]
        "fields": [{"field": "text", "reason": "too_long"}],
        "max_length": 280,
    }


def test_unregistered_type_raises_key_error() -> None:
    with pytest.raises(KeyError):
        build_error_response(ValueError("not a registered domain error"))
