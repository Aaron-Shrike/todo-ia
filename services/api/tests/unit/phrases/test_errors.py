"""Unit tests for phrase domain error types (tasks.md Unit 1 / 1.3).

Plain marker exceptions consumed by the application layer (Unit 3) and
mapped to HTTP by `platform/errors.py` (Unit 6). Triangulation skipped for
`EmptyPhraseText`: purely structural, no attributes, no branching.
"""

from app.modules.phrases.domain.errors import EmptyPhraseText, PhraseTooLong


def test_empty_phrase_text_is_an_exception() -> None:
    assert isinstance(EmptyPhraseText(), Exception)


def test_phrase_too_long_carries_the_configured_limit() -> None:
    assert PhraseTooLong(max_length=280).max_length == 280
    assert "280" in str(PhraseTooLong(max_length=280))


def test_phrase_too_long_reflects_a_different_configured_limit() -> None:
    # Triangulation: a different max_length proves it is not hardcoded.
    assert PhraseTooLong(max_length=50).max_length == 50
