"""Unit 6.2: `phrases/api/schemas.py` shared base types."""

from __future__ import annotations

import pytest
from pydantic import BaseModel, ValidationError

from app.modules.phrases.api.schemas import (
    PhraseId,
    page_limit,
    query_score,
    query_text,
    raw_phrase_text,
)

pytestmark = pytest.mark.unit


class _IdModel(BaseModel):
    id: PhraseId


def test_id_serializes_to_a_decimal_string_on_the_wire() -> None:
    model = _IdModel(id=9007199254740993)  # > Number.MAX_SAFE_INTEGER
    assert model.model_dump(mode="json") == {"id": "9007199254740993"}


def test_id_stays_an_int_for_internal_python_use() -> None:
    model = _IdModel(id=42)
    assert model.id == 42
    assert isinstance(model.id, int)


class _LimitModel(BaseModel):
    limit: page_limit(50)  # type: ignore[valid-type]


@pytest.mark.parametrize("value", [1, 50])
def test_page_limit_boundary_values_accepted(value: int) -> None:
    assert _LimitModel(limit=value).limit == value


@pytest.mark.parametrize("value", [0, 51, "10", True, 10.5])
def test_page_limit_rejects_out_of_range_and_non_strict_values(value: object) -> None:
    with pytest.raises(ValidationError):
        _LimitModel(limit=value)


class _TextModel(BaseModel):
    text: raw_phrase_text(280)  # type: ignore[valid-type]


def test_raw_phrase_text_accepts_up_to_four_times_max_length() -> None:
    assert _TextModel(text="a" * 1120).text == "a" * 1120


def test_raw_phrase_text_rejects_one_over_the_raw_cap() -> None:
    with pytest.raises(ValidationError):
        _TextModel(text="a" * 1121)


def test_raw_phrase_text_error_reports_the_semantic_max_length_not_the_raw_cap() -> None:
    """The error's `ctx.max_length` must be `PHRASE_MAX_LENGTH` (280), not
    the raw `4x` bound (1120) pydantic would report by default -- this is
    what `main.py`'s generic `too_long` mapping surfaces as
    `details.max_length` (design.md's "Raw length cap" scenario)."""
    with pytest.raises(ValidationError) as exc_info:
        _TextModel(text="a" * 1121)
    (error,) = exc_info.value.errors()
    assert error["type"] == "string_too_long"
    assert error["ctx"]["max_length"] == 280


def test_raw_phrase_text_rejects_non_string() -> None:
    with pytest.raises(ValidationError):
        _TextModel(text=123)


class _ScoreModel(BaseModel):
    min_score: query_score()  # type: ignore[valid-type]


@pytest.mark.parametrize("value", [0.0, 0.5, 1.0])
def test_query_score_boundary_values_accepted(value: float) -> None:
    assert _ScoreModel(min_score=value).min_score == value


@pytest.mark.parametrize("value", [-0.1, 1.1])
def test_query_score_rejects_out_of_range_values(value: float) -> None:
    with pytest.raises(ValidationError):
        _ScoreModel(min_score=value)


def test_query_score_rejects_nan() -> None:
    with pytest.raises(ValidationError):
        _ScoreModel(min_score=float("nan"))


class _QueryTextModel(BaseModel):
    q: query_text(280)  # type: ignore[valid-type]


def test_query_text_accepts_up_to_the_semantic_max_length() -> None:
    assert _QueryTextModel(q="a" * 280).q == "a" * 280


def test_query_text_rejects_one_over_the_semantic_max_length() -> None:
    with pytest.raises(ValidationError):
        _QueryTextModel(q="a" * 281)


def test_query_text_error_reports_the_semantic_max_length() -> None:
    """Unlike `raw_phrase_text`, `query_text` has no 4x raw cap -- `q` is
    only ever compared against `normalized_text`, never stored, so its own
    raw length IS the semantic bound (api-contract spec's "q over the
    length cap" scenario)."""
    with pytest.raises(ValidationError) as exc_info:
        _QueryTextModel(q="a" * 281)
    (error,) = exc_info.value.errors()
    assert error["type"] == "string_too_long"
    assert error["ctx"]["max_length"] == 280
