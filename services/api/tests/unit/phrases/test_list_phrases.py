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


def _seed_one(
    factory: InMemoryUnitOfWorkFactory,
    *,
    text: str,
    normalized_text: str | None = None,
    status: ValidationStatus = ValidationStatus.UNIQUE,
    score: float | None = None,
) -> None:
    with factory() as uow:
        uow.repo.add(
            NewPhrase(
                text=text,
                normalized_text=normalized_text if normalized_text is not None else text,
                embedding=vector_at_distance(0.05),
                similarity_score=score,
                most_similar_phrase_id=(1 if score is not None else None),
                validation_status=status,
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


# --- design.md D2: `q` normalization + `ListFilters` construction --------


def test_status_filter_is_passed_through_to_the_repository() -> None:
    factory = InMemoryUnitOfWorkFactory()
    _seed_one(factory, text="a", status=ValidationStatus.UNIQUE)
    _seed_one(factory, text="b", status=ValidationStatus.DUPLICATE_CONFIRMED, score=0.9)
    list_phrases = ListPhrases(factory)
    view = list_phrases(limit=10, cursor=None, status=ValidationStatus.DUPLICATE_CONFIRMED)
    assert [p.text for p in view.items] == ["b"]
    assert view.total == 1


def test_none_status_means_no_filter() -> None:
    factory = InMemoryUnitOfWorkFactory()
    _seed_one(factory, text="a", status=ValidationStatus.UNIQUE)
    _seed_one(factory, text="b", status=ValidationStatus.DUPLICATE_CONFIRMED, score=0.9)
    list_phrases = ListPhrases(factory)
    view = list_phrases(limit=10, cursor=None, status=None)
    assert view.total == 2


def test_q_is_normalized_to_comparison_form_before_filtering() -> None:
    # `comparison_form(display_form("LECHE"))` == "leche" (D2) -- proves
    # ListPhrases, not the repository, does the casefolding.
    factory = InMemoryUnitOfWorkFactory()
    _seed_one(factory, text="tengo leche fresca", normalized_text="tengo leche fresca")
    _seed_one(factory, text="agua", normalized_text="agua")
    list_phrases = ListPhrases(factory)
    view = list_phrases(limit=10, cursor=None, q="LECHE")
    assert [p.text for p in view.items] == ["tengo leche fresca"]
    assert view.total == 1


@pytest.mark.parametrize("blank", ["", "   ", None])
def test_blank_or_none_q_is_treated_as_absent(blank: str | None) -> None:
    factory = InMemoryUnitOfWorkFactory()
    _seed_one(factory, text="a")
    _seed_one(factory, text="b")
    list_phrases = ListPhrases(factory)
    view = list_phrases(limit=10, cursor=None, q=blank)
    assert view.total == 2


def test_min_score_filter_excludes_null_scores() -> None:
    factory = InMemoryUnitOfWorkFactory()
    _seed_one(
        factory, text="confirmed", status=ValidationStatus.DUPLICATE_CONFIRMED, score=0.9
    )
    _seed_one(factory, text="unique", status=ValidationStatus.UNIQUE, score=None)
    list_phrases = ListPhrases(factory)
    view = list_phrases(limit=10, cursor=None, min_score=0.5)
    assert [p.text for p in view.items] == ["confirmed"]
    assert view.total == 1


def test_none_min_score_means_no_filter() -> None:
    factory = InMemoryUnitOfWorkFactory()
    _seed_one(
        factory, text="confirmed", status=ValidationStatus.DUPLICATE_CONFIRMED, score=0.9
    )
    _seed_one(factory, text="unique", status=ValidationStatus.UNIQUE, score=None)
    list_phrases = ListPhrases(factory)
    view = list_phrases(limit=10, cursor=None, min_score=None)
    assert view.total == 2


def test_filters_combine_with_and() -> None:
    """A row matching `status` and `min_score` but NOT `q` must be excluded
    -- proves `ListPhrases` builds ONE combined `ListFilters` (D1, AND
    semantics), not three independently-applied filters."""
    factory = InMemoryUnitOfWorkFactory()
    _seed_one(
        factory,
        text="tengo leche fresca",
        normalized_text="tengo leche fresca",
        status=ValidationStatus.DUPLICATE_CONFIRMED,
        score=0.9,
    )
    _seed_one(
        factory,
        text="tengo agua fresca",
        normalized_text="tengo agua fresca",
        status=ValidationStatus.DUPLICATE_CONFIRMED,
        score=0.9,
    )
    list_phrases = ListPhrases(factory)
    view = list_phrases(
        limit=10,
        cursor=None,
        status=ValidationStatus.DUPLICATE_CONFIRMED,
        q="LECHE",
        min_score=0.5,
    )
    assert [p.text for p in view.items] == ["tengo leche fresca"]
    assert view.total == 1
