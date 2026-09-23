"""Unit tests for the in-memory `PhraseRepository`/`UnitOfWork` beyond what
`tests/contract_suite/repository_contract.py` covers: enum values,
`list_recent`, `DuplicateTextConflict`, transaction buffering
(commit/rollback), `REPEATABLE READ` snapshot isolation and `find_matches`'
`(bucket, id)` keyset basics (tasks.md 2.3/2d.2 -- the deferred contract-
suite scenarios for `find_matches` live in `repository_contract.py`
instead, since they must also bind the future pgvector adapter).
"""

from __future__ import annotations

from datetime import UTC, datetime

import pytest

from app.modules.phrases.adapters.in_memory_repository import InMemoryUnitOfWorkFactory
from app.modules.phrases.contracts import (
    DuplicateTextConflict,
    Isolation,
    MatchCursor,
    NewPhrase,
    ValidationStatus,
)
from app.modules.phrases.domain.errors import PhraseMetadataInvariantViolation
from tests.contract_suite.vectors import PROBE
from tests.contract_suite.vectors import vector_at_distance as _vector_at_distance


def _phrase(
    text: str,
    normalized: str,
    *,
    status: ValidationStatus = ValidationStatus.UNIQUE,
    similarity_score: float | None = None,
    most_similar_phrase_id: int | None = None,
) -> NewPhrase:
    return NewPhrase(
        text=text,
        normalized_text=normalized,
        embedding=[1.0, 0.0],
        similarity_score=similarity_score,
        most_similar_phrase_id=most_similar_phrase_id,
        validation_status=status,
        validated_at=datetime.now(UTC),
    )


def test_validation_status_and_isolation_match_the_db_and_sql_literals() -> None:
    assert ValidationStatus.UNIQUE.value == "unique"
    assert ValidationStatus.DUPLICATE_CONFIRMED.value == "duplicate_confirmed"
    assert Isolation.READ_COMMITTED.value == "READ COMMITTED"
    assert Isolation.REPEATABLE_READ.value == "REPEATABLE READ"


def test_list_recent_returns_newest_first_and_respects_limit() -> None:
    factory = InMemoryUnitOfWorkFactory()
    with factory() as uow:
        uow.repo.add(_phrase("one", "one"))
        uow.repo.add(_phrase("two", "two"))
        uow.repo.add(_phrase("three", "three"))
        uow.commit()

    with factory(read_only=True) as uow:
        recent = uow.repo.list_recent(2)
    assert [p.text for p in recent] == ["three", "two"]


def test_add_raises_duplicate_conflict_unless_confirmed() -> None:
    # ADR-006: the partial unique index excludes duplicate_confirmed rows.
    factory = InMemoryUnitOfWorkFactory()
    with factory() as uow:
        uow.repo.add(_phrase("Comprar leche", "comprar leche"))
        uow.commit()

    with factory() as uow, pytest.raises(DuplicateTextConflict):
        uow.repo.add(_phrase("COMPRAR LECHE", "comprar leche"))

    with factory() as uow:
        # phrases_confirmed_has_neighbor: a duplicate_confirmed row always
        # carries both similarity_score and most_similar_phrase_id.
        confirmed = uow.repo.add(
            _phrase(
                "Comprar leche",
                "comprar leche",
                status=ValidationStatus.DUPLICATE_CONFIRMED,
                similarity_score=0.95,
                most_similar_phrase_id=1,
            )
        )
        uow.commit()
    assert confirmed.validation_status is ValidationStatus.DUPLICATE_CONFIRMED


def test_writes_are_invisible_until_commit_and_discarded_on_rollback() -> None:
    factory = InMemoryUnitOfWorkFactory()

    with factory() as uow:
        uow.repo.add(_phrase("ghost", "ghost"))
        uow.rollback()
    with factory() as uow:
        uow.repo.add(_phrase("also-ghost", "also-ghost"))
        # no commit() -- __exit__ must roll back too.

    with factory(read_only=True) as uow:
        assert uow.repo.list_recent(10) == []


def test_repeatable_read_does_not_see_a_write_committed_after_it_opened() -> None:
    factory = InMemoryUnitOfWorkFactory()
    with factory() as uow:
        uow.repo.add(_phrase("before", "before"))
        uow.commit()

    with factory(isolation=Isolation.REPEATABLE_READ, read_only=True) as snapshot_uow:
        with factory() as writer_uow:
            writer_uow.repo.add(_phrase("after", "after"))
            writer_uow.commit()
        assert [p.text for p in snapshot_uow.repo.list_recent(10)] == ["before"]

    with factory(read_only=True) as fresh_uow:
        assert {p.text for p in fresh_uow.repo.list_recent(10)} == {"before", "after"}


def test_lock_for_write_is_a_no_op() -> None:
    with InMemoryUnitOfWorkFactory()() as uow:
        uow.repo.lock_for_write()  # must not raise
        uow.commit()


def test_read_committed_sees_a_write_committed_after_it_opened() -> None:
    # Converse of test_repeatable_read_does_not_see_a_write_committed_after_it_opened:
    # READ_COMMITTED's `read_view` is a live method reference (`self._store.snapshot`),
    # not a frozen closure, so every call re-reads the current store.
    factory = InMemoryUnitOfWorkFactory()
    with factory() as uow:
        uow.repo.add(_phrase("before", "before"))
        uow.commit()

    with factory(isolation=Isolation.READ_COMMITTED, read_only=True) as live_uow:
        assert [p.text for p in live_uow.repo.list_recent(10)] == ["before"]
        with factory() as writer_uow:
            writer_uow.repo.add(_phrase("after", "after"))
            writer_uow.commit()
        # Same still-open UnitOfWork, same repo -- sees the write committed
        # by the OTHER transaction after this one opened.
        assert {p.text for p in live_uow.repo.list_recent(10)} == {"before", "after"}


def test_add_rejects_a_new_phrase_that_breaks_the_paired_metadata_invariant() -> None:
    # phrases_metadata_paired: similarity_score and most_similar_phrase_id
    # must be NULL together or non-NULL together.
    factory = InMemoryUnitOfWorkFactory()
    unpaired = NewPhrase(
        text="orphan score",
        normalized_text="orphan score",
        embedding=[1.0, 0.0],
        similarity_score=0.9,
        most_similar_phrase_id=None,
        validation_status=ValidationStatus.UNIQUE,
        validated_at=datetime.now(UTC),
    )
    with factory() as uow, pytest.raises(PhraseMetadataInvariantViolation):
        uow.repo.add(unpaired)


def test_add_rejects_a_confirmed_duplicate_without_a_neighbour() -> None:
    # phrases_confirmed_has_neighbor: a duplicate_confirmed row always
    # carries both similarity_score and most_similar_phrase_id.
    factory = InMemoryUnitOfWorkFactory()
    unconfirmed_neighbor = NewPhrase(
        text="confirmed but blind",
        normalized_text="confirmed but blind",
        embedding=[1.0, 0.0],
        similarity_score=None,
        most_similar_phrase_id=None,
        validation_status=ValidationStatus.DUPLICATE_CONFIRMED,
        validated_at=datetime.now(UTC),
    )
    with factory() as uow, pytest.raises(PhraseMetadataInvariantViolation):
        uow.repo.add(unconfirmed_neighbor)


def test_find_matches_filters_by_max_distance_and_orders_by_bucket_then_id() -> None:
    # `_phrase()` always embeds at [1.0, 0.0] (distance 0 from PROBE), so
    # these seeds use explicit distance-controlled `NewPhrase`s instead.
    factory = InMemoryUnitOfWorkFactory()
    with factory() as uow:
        near = NewPhrase(
            text="near",
            normalized_text="near",
            embedding=_vector_at_distance(0.05),
            similarity_score=None,
            most_similar_phrase_id=None,
            validation_status=ValidationStatus.UNIQUE,
            validated_at=datetime.now(UTC),
        )
        mid = NewPhrase(
            text="mid",
            normalized_text="mid",
            embedding=_vector_at_distance(0.15),
            similarity_score=None,
            most_similar_phrase_id=None,
            validation_status=ValidationStatus.UNIQUE,
            validated_at=datetime.now(UTC),
        )
        far = NewPhrase(
            text="far",
            normalized_text="far",
            embedding=_vector_at_distance(0.90),  # excluded: above max_distance
            similarity_score=None,
            most_similar_phrase_id=None,
            validation_status=ValidationStatus.UNIQUE,
            validated_at=datetime.now(UTC),
        )
        uow.repo.add(near)
        uow.repo.add(mid)
        uow.repo.add(far)
        uow.commit()

    with factory(read_only=True) as uow:
        page = uow.repo.find_matches(PROBE, max_distance=0.2, limit=10, cursor=None)

    assert [match.text for match in page.items] == ["near", "mid"]
    assert page.has_more is False
    assert page.next_cursor is None


def test_count_matches_reports_the_full_count_independent_of_limit() -> None:
    factory = InMemoryUnitOfWorkFactory()
    with factory() as uow:
        for i, distance in enumerate((0.05, 0.10, 0.15, 0.90)):
            uow.repo.add(
                NewPhrase(
                    text=f"p{i}",
                    normalized_text=f"p{i}",
                    embedding=_vector_at_distance(distance),
                    similarity_score=None,
                    most_similar_phrase_id=None,
                    validation_status=ValidationStatus.UNIQUE,
                    validated_at=datetime.now(UTC),
                )
            )
        uow.commit()

    with factory(read_only=True) as uow:
        total = uow.repo.count_matches(PROBE, max_distance=0.2)  # excludes the 0.90 phrase
        page = uow.repo.find_matches(PROBE, max_distance=0.2, limit=1, cursor=None)

    assert total == 3
    assert len(page.items) == 1  # `limit` bounds the page, not `count_matches`


def test_find_matches_limit_plus_one_probe_and_cursor_continuation() -> None:
    factory = InMemoryUnitOfWorkFactory()
    with factory() as uow:
        for i, distance in enumerate([0.01, 0.02, 0.03], start=1):
            uow.repo.add(
                NewPhrase(
                    text=f"p{i}",
                    normalized_text=f"p{i}",
                    embedding=_vector_at_distance(distance),
                    similarity_score=None,
                    most_similar_phrase_id=None,
                    validation_status=ValidationStatus.UNIQUE,
                    validated_at=datetime.now(UTC),
                )
            )
        uow.commit()

    with factory(read_only=True) as uow:
        page1 = uow.repo.find_matches(PROBE, max_distance=1.0, limit=2, cursor=None)
        assert [m.text for m in page1.items] == ["p1", "p2"]
        assert page1.has_more is True
        assert page1.next_cursor is not None
        assert isinstance(page1.next_cursor, MatchCursor)
        assert page1.next_cursor.id == page1.items[-1].id

        page2 = uow.repo.find_matches(
            PROBE, max_distance=1.0, limit=2, cursor=page1.next_cursor
        )
        assert [m.text for m in page2.items] == ["p3"]
        assert page2.has_more is False
        assert page2.next_cursor is None


def test_add_accepts_a_valid_paired_neighbor_on_a_unique_row() -> None:
    # Valid case: a `unique` row MAY carry a below-threshold neighbour, as
    # long as score and neighbour are a pair.
    factory = InMemoryUnitOfWorkFactory()
    paired = NewPhrase(
        text="below threshold",
        normalized_text="below threshold",
        embedding=[1.0, 0.0],
        similarity_score=0.55,
        most_similar_phrase_id=1,
        validation_status=ValidationStatus.UNIQUE,
        validated_at=datetime.now(UTC),
    )
    with factory() as uow:
        row = uow.repo.add(paired)
        uow.commit()
    assert row.similarity_score == 0.55
    assert row.most_similar_phrase_id == 1
