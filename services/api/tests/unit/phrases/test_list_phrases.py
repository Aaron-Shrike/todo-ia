"""Unit tests for `ListPhrases` (tasks.md 7b.1, design.md's "Request
shapes": `GET /phrases` takes no parameters, is not paginated and is
hard-capped at `PHRASES_LIST_LIMIT`). Mirrors `phrase-management`'s "List
phrases" scenarios (Newest first, Empty list) at the use-case layer; the
HTTP-shape scenarios (incl. Metadata exposed and Hard cap) live in
`tests/contract/test_phrases_endpoints.py`.
"""

from __future__ import annotations

from datetime import UTC, datetime

from app.modules.phrases.adapters.in_memory_repository import InMemoryUnitOfWorkFactory
from app.modules.phrases.application.list_phrases import ListPhrases
from app.modules.phrases.contracts import NewPhrase, ValidationStatus
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


def test_empty_store_returns_an_empty_list() -> None:
    factory = InMemoryUnitOfWorkFactory()
    list_phrases = ListPhrases(factory, limit=200)
    assert list_phrases() == []


def test_newest_first() -> None:
    factory = InMemoryUnitOfWorkFactory()
    _seed(factory, ("a", 0.05), ("b", 0.10), ("c", 0.15))
    list_phrases = ListPhrases(factory, limit=200)
    assert [p.text for p in list_phrases()] == ["c", "b", "a"]


def test_hard_capped_at_the_configured_limit() -> None:
    factory = InMemoryUnitOfWorkFactory()
    _seed(factory, *[(f"p{i}", 0.05 + i * 0.001) for i in range(5)])
    list_phrases = ListPhrases(factory, limit=2)
    assert [p.text for p in list_phrases()] == ["p4", "p3"]
