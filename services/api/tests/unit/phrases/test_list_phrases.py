"""Unit tests for `ListPhrases` (`GET /phrases`, keyset-paginated newest
first). Mirrors `phrase-management`'s "List phrases" scenarios (Newest
first, Empty list) at the use-case layer; the HTTP-shape scenarios
(pagination walk, limit bounds, cursor errors) live in
`tests/contract/test_phrases_endpoints.py`.
"""

from __future__ import annotations

from datetime import UTC, datetime

import pytest

from app.modules.phrases.adapters.in_memory_repository import InMemoryUnitOfWorkFactory
from app.modules.phrases.application.list_phrases import ListPhrases
from app.modules.phrases.contracts import NewPhrase, ValidationStatus
from app.modules.phrases.domain.list_cursor import InvalidListCursor
from tests.contract_suite.vectors import vector_at_distance


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


def test_empty_store_returns_an_empty_page() -> None:
    factory = InMemoryUnitOfWorkFactory()
    list_phrases = ListPhrases(factory)
    view = list_phrases(limit=200, cursor=None)
    assert view.items == []
    assert view.total == 0
    assert view.next_cursor is None
    assert view.has_more is False


def test_newest_first() -> None:
    factory = InMemoryUnitOfWorkFactory()
    _seed(factory, ("a", 0.05), ("b", 0.10), ("c", 0.15))
    list_phrases = ListPhrases(factory)
    view = list_phrases(limit=200, cursor=None)
    assert [p.text for p in view.items] == ["c", "b", "a"]
    assert view.total == 3
    assert view.has_more is False


def test_page_smaller_than_total_sets_has_more_and_next_cursor() -> None:
    factory = InMemoryUnitOfWorkFactory()
    _seed(factory, *[(f"p{i}", 0.05 + i * 0.001) for i in range(5)])
    list_phrases = ListPhrases(factory)
    view = list_phrases(limit=2, cursor=None)
    assert [p.text for p in view.items] == ["p4", "p3"]
    assert view.total == 5
    assert view.has_more is True
    assert view.next_cursor is not None


def test_cursor_continues_where_the_previous_page_stopped() -> None:
    factory = InMemoryUnitOfWorkFactory()
    _seed(factory, *[(f"p{i}", 0.05 + i * 0.001) for i in range(5)])
    list_phrases = ListPhrases(factory)
    first = list_phrases(limit=2, cursor=None)
    second = list_phrases(limit=2, cursor=first.next_cursor)
    assert [p.text for p in second.items] == ["p2", "p1"]
    assert second.has_more is True
    third = list_phrases(limit=2, cursor=second.next_cursor)
    assert [p.text for p in third.items] == ["p0"]
    assert third.has_more is False
    assert third.next_cursor is None


def test_malformed_cursor_raises_invalid_list_cursor() -> None:
    factory = InMemoryUnitOfWorkFactory()
    list_phrases = ListPhrases(factory)
    with pytest.raises(InvalidListCursor):
        list_phrases(limit=10, cursor="not-a-cursor")
