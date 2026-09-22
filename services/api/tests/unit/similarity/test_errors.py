"""Unit tests for similarity domain error types (tasks.md Unit 1 / 1.3).

Plain marker exceptions raised by `EmbeddingProvider` implementations,
mapped to HTTP 503/504 by `platform/errors.py` (Unit 6). Triangulation
skipped: purely structural, no attributes, no branching.
"""

from app.modules.similarity.domain.errors import EmbeddingTimeout, EmbeddingUnavailable


def test_embedding_unavailable_is_an_exception() -> None:
    assert isinstance(EmbeddingUnavailable(), Exception)


def test_embedding_timeout_is_an_exception() -> None:
    assert isinstance(EmbeddingTimeout(), Exception)
