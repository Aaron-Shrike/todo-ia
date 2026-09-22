"""Unit tests for `ListMatches` (tasks.md 3.2, design.md's Cursor format:
"decode -> validate fields -> compare t and th -> embed -> query").
"""

from __future__ import annotations

from datetime import UTC, datetime

import pytest
from tests.contract_suite.vectors import PROBE, vector_at_distance

from app.modules.phrases.adapters.in_memory_repository import InMemoryUnitOfWorkFactory
from app.modules.phrases.application.list_matches import ListMatches
from app.modules.phrases.contracts import NewPhrase, ValidationStatus
from app.modules.phrases.domain.cursor import InvalidCursor, encode_cursor
from app.modules.similarity.adapters.caching import CachingEmbeddingProvider
from app.modules.similarity.adapters.fake import FakeEmbedder
from app.modules.similarity.contracts import SimilarityPolicy

_QUERY_TEXT = "query text"
_POLICY = SimilarityPolicy(threshold=0.80)


def _seed(factory: InMemoryUnitOfWorkFactory, *entries: tuple[str, float]) -> None:
    with factory() as uow:
        for text, distance in entries:
            uow.repo.add(
                NewPhrase(
                    text=text,
                    normalized_text=text,
                    embedding=vector_at_distance(distance),
                    similarity_score=None,
                    most_similar_phrase_id=None,
                    validation_status=ValidationStatus.UNIQUE,
                    validated_at=datetime.now(UTC),
                )
            )
        uow.commit()


def test_returns_the_next_page_after_a_valid_cursor() -> None:
    factory = InMemoryUnitOfWorkFactory()
    _seed(factory, ("first", 0.05), ("second", 0.10), ("third", 0.15))
    embedder = FakeEmbedder({_QUERY_TEXT: PROBE})
    list_matches = ListMatches(factory, embedder, _POLICY, phrase_max_length=280)
    cursor = encode_cursor(t=_QUERY_TEXT, d=0.05, i=1, th=0.80)
    page = list_matches(_QUERY_TEXT, cursor=cursor, limit=50)
    assert [m.text for m in page.matches] == ["second", "third"]
    assert page.has_more is False


def test_malformed_cursor_rejected_before_embedding() -> None:
    factory = InMemoryUnitOfWorkFactory()
    embedder = FakeEmbedder({_QUERY_TEXT: PROBE})
    list_matches = ListMatches(factory, embedder, _POLICY, phrase_max_length=280)
    with pytest.raises(InvalidCursor):
        list_matches(_QUERY_TEXT, cursor="not-a-cursor!!", limit=50)
    assert embedder.call_count == 0


def test_cursor_bound_to_a_different_text_is_rejected_before_embedding() -> None:
    factory = InMemoryUnitOfWorkFactory()
    embedder = FakeEmbedder({_QUERY_TEXT: PROBE})
    list_matches = ListMatches(factory, embedder, _POLICY, phrase_max_length=280)
    cursor = encode_cursor(t="a different comparison form", d=0.1, i=1, th=0.80)
    with pytest.raises(InvalidCursor):
        list_matches(_QUERY_TEXT, cursor=cursor, limit=50)
    assert embedder.call_count == 0


def test_cursor_bound_to_a_different_threshold_is_rejected_before_embedding() -> None:
    factory = InMemoryUnitOfWorkFactory()
    embedder = FakeEmbedder({_QUERY_TEXT: PROBE})
    list_matches = ListMatches(factory, embedder, _POLICY, phrase_max_length=280)
    cursor = encode_cursor(t=_QUERY_TEXT, d=0.1, i=1, th=0.90)
    with pytest.raises(InvalidCursor):
        list_matches(_QUERY_TEXT, cursor=cursor, limit=50)
    assert embedder.call_count == 0


def test_embedding_is_reused_across_pages_with_a_warm_cache() -> None:
    factory = InMemoryUnitOfWorkFactory()
    _seed(factory, ("a", 0.05), ("b", 0.10), ("c", 0.15))
    inner = FakeEmbedder({_QUERY_TEXT: PROBE})
    cached = CachingEmbeddingProvider(inner, capacity=8)
    list_matches = ListMatches(factory, cached, _POLICY, phrase_max_length=280)

    cursor = encode_cursor(t=_QUERY_TEXT, d=0.05, i=1, th=0.80)
    page2 = list_matches(_QUERY_TEXT, cursor=cursor, limit=1)
    assert page2.next_cursor is not None
    list_matches(_QUERY_TEXT, cursor=page2.next_cursor, limit=1)

    assert inner.call_count == 1
