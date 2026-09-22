"""Shared `PhraseRepository`/`UnitOfWork` contract suite (tasks.md 2.3/2d.3;
design.md: "a shared contract test suite ... so the fast fake cannot drift
from the real one"). Subclass `RepositoryContractSuite`, override the
`uow_factory` fixture. Only in-memory is registered in Unit 2/2d; pgvector
registers in Unit 5a/5b. Not `test_*.py` on purpose -- a shared base,
collected only through subclasses.

`find_matches` keyset scenarios (Complete ordered match set / Page
consistency requirements, `specs/semantic-validation/spec.md`): bit-
identical tie across a page boundary, displayed-tie ordering by raw
distance, 500-match paging, perturbed-vector paging on a fixture away from
grid edges -- restored here per tasks.md's Unit 2d (the review-budget
deferral this note used to point at from Unit 2 is now resolved).
"""

from __future__ import annotations

from datetime import UTC, datetime

import pytest
from tests.contract_suite.vectors import PROBE
from tests.contract_suite.vectors import vector_at_distance as _vector_at_distance

from app.modules.phrases.contracts import (
    Isolation,
    MatchCursor,
    NewPhrase,
    UnitOfWorkFactory,
    ValidationStatus,
)
from app.modules.similarity.contracts import Vector


def _new_phrase(text: str, embedding: Vector) -> NewPhrase:
    return NewPhrase(
        text=text,
        normalized_text=text,
        embedding=embedding,
        similarity_score=None,
        most_similar_phrase_id=None,
        validation_status=ValidationStatus.UNIQUE,
        validated_at=datetime.now(UTC),
    )


def _seed(uow_factory: UnitOfWorkFactory, phrases: list[NewPhrase]) -> list[int]:
    ids: list[int] = []
    with uow_factory() as uow:
        for phrase in phrases:
            ids.append(uow.repo.add(phrase).id)
        uow.commit()
    return ids


class RepositoryContractSuite:
    @pytest.fixture
    def uow_factory(self) -> UnitOfWorkFactory:
        raise NotImplementedError("subclasses must override the `uow_factory` fixture")

    def test_find_nearest_on_an_empty_store_returns_none(
        self, uow_factory: UnitOfWorkFactory
    ) -> None:
        with uow_factory(isolation=Isolation.REPEATABLE_READ, read_only=True) as uow:
            assert uow.repo.find_nearest(PROBE) is None
            assert uow.repo.find_nearest_exact(PROBE) is None

    def test_find_nearest_returns_a_below_threshold_neighbour(
        self, uow_factory: UnitOfWorkFactory
    ) -> None:
        _seed(uow_factory, [_new_phrase("far", _vector_at_distance(1.9))])
        with uow_factory(read_only=True) as uow:
            neighbor = uow.repo.find_nearest(PROBE)
            exact = uow.repo.find_nearest_exact(PROBE)
        assert neighbor is not None and exact is not None
        assert neighbor.text == exact.text == "far"
        assert neighbor.distance == pytest.approx(1.9, abs=1e-9)

    def test_find_nearest_tie_breaks_on_lowest_id(self, uow_factory: UnitOfWorkFactory) -> None:
        ids = _seed(
            uow_factory,
            [
                _new_phrase("second", _vector_at_distance(0.4)),
                _new_phrase("first", _vector_at_distance(0.4)),
            ],
        )
        with uow_factory(read_only=True) as uow:
            neighbor = uow.repo.find_nearest(PROBE)
            exact = uow.repo.find_nearest_exact(PROBE)
        assert neighbor is not None and exact is not None
        assert neighbor.id == exact.id == min(ids)

    def test_add_inside_a_read_only_unit_of_work_raises_immediately(
        self, uow_factory: UnitOfWorkFactory
    ) -> None:
        # Fail-fast at the statement, matching a real Postgres `BEGIN READ
        # ONLY` transaction: the write must be rejected as soon as `add()`
        # is called, not only if the caller happens to call `commit()` with
        # pending writes -- the common read-only pattern never commits.
        with uow_factory(read_only=True) as uow:
            with pytest.raises(Exception):  # noqa: B017 -- adapter-specific error type
                uow.repo.add(_new_phrase("nope", PROBE))

    def test_bit_identical_ties_split_cleanly_across_a_page_boundary(
        self, uow_factory: UnitOfWorkFactory
    ) -> None:
        # spec's "Tie scores across a page boundary": 5 matches with
        # bit-identical embeddings (equal raw distance -> the SAME bucket),
        # ids 1..5, limit=2 -> pages [1,2], [3,4], [5]: none repeated, none
        # skipped, ordered purely by id inside the tied bucket.
        tied_vector = _vector_at_distance(0.10)
        ids = _seed(uow_factory, [_new_phrase(f"tied-{i}", tied_vector) for i in range(1, 6)])
        assert ids == sorted(ids)  # ids assigned in insertion order, as the assertion below assumes

        collected: list[int] = []
        cursor: MatchCursor | None = None
        with uow_factory(read_only=True) as uow:
            page = uow.repo.find_matches(PROBE, max_distance=1.0, limit=2, cursor=None)
            collected.extend(m.id for m in page.items)
            assert page.has_more is True
            cursor = page.next_cursor

            page = uow.repo.find_matches(PROBE, max_distance=1.0, limit=2, cursor=cursor)
            collected.extend(m.id for m in page.items)
            assert page.has_more is True
            cursor = page.next_cursor

            page = uow.repo.find_matches(PROBE, max_distance=1.0, limit=2, cursor=cursor)
            collected.extend(m.id for m in page.items)
            assert page.has_more is False
            assert page.next_cursor is None

        assert collected == ids  # [1,2],[3,4],[5] concatenated, none repeated or skipped

    def test_displayed_ties_are_ordered_by_raw_distance(
        self, uow_factory: UnitOfWorkFactory
    ) -> None:
        # spec's "Displayed ties are ordered by raw distance": raw scores
        # 0.90001 (id "a") and 0.90004 (id "b") both round to the displayed
        # 0.9000, but "b" (the smaller raw distance, higher raw score) MUST
        # precede "a" -- the keyset orders on the UNROUNDED distance.
        ids = _seed(
            uow_factory,
            [
                _new_phrase("a", _vector_at_distance(1 - 0.90001)),
                _new_phrase("b", _vector_at_distance(1 - 0.90004)),
            ],
        )
        with uow_factory(read_only=True) as uow:
            page = uow.repo.find_matches(PROBE, max_distance=1.0, limit=10, cursor=None)
        assert [m.text for m in page.items] == ["b", "a"]
        assert [m.id for m in page.items] == sorted(ids, reverse=True)  # "b" inserted second

    def test_500_matches_page_through_completely_with_no_gaps_or_repeats(
        self, uow_factory: UnitOfWorkFactory
    ) -> None:
        # spec's "Paging beyond the former approximate-index window":
        # 500 matches above threshold, page size 50 -> 10 pages, 500
        # distinct ids, none missing, none repeated.
        distances = [0.001 + i * 0.0013 for i in range(500)]  # spread, away from grid edges
        phrases = [_new_phrase(f"m{i}", _vector_at_distance(d)) for i, d in enumerate(distances)]
        ids = _seed(uow_factory, phrases)

        collected: list[int] = []
        cursor: MatchCursor | None = None
        pages = 0
        with uow_factory(read_only=True) as uow:
            while True:
                page = uow.repo.find_matches(PROBE, max_distance=1.0, limit=50, cursor=cursor)
                pages += 1
                collected.extend(m.id for m in page.items)
                cursor = page.next_cursor
                if not page.has_more:
                    break

        assert pages == 10
        assert len(collected) == 500
        assert len(set(collected)) == 500  # none repeated
        assert set(collected) == set(ids)  # none missing

    def test_perturbed_vector_paging_does_not_repeat_or_skip(
        self, uow_factory: UnitOfWorkFactory
    ) -> None:
        # design.md: "a perturbed-vector test pages a fixture to the end
        # with each page's query vector perturbed by one float32 ulp per
        # component"; fixture distances stay away from grid edges (D16) so
        # the test is deterministic. This models re-embedding the same
        # query text on a later page (cache eviction / another worker)
        # producing a vector that differs by a tiny numerical drift.
        distances = [0.011, 0.024, 0.037, 0.049, 0.062, 0.078, 0.091]
        phrases = [
            _new_phrase(f"p{i}", _vector_at_distance(d)) for i, d in enumerate(distances, start=1)
        ]
        ids = _seed(uow_factory, phrases)

        def _perturb(vector: Vector, eps: float = 1e-7) -> Vector:
            return [component + eps for component in vector]

        collected: list[int] = []
        cursor: MatchCursor | None = None
        first_page = True
        with uow_factory(read_only=True) as uow:
            while True:
                query_vector = PROBE if first_page else _perturb(PROBE)
                first_page = False
                page = uow.repo.find_matches(query_vector, max_distance=1.0, limit=3, cursor=cursor)
                collected.extend(m.id for m in page.items)
                cursor = page.next_cursor
                if not page.has_more:
                    break

        assert collected == ids  # none repeated, none skipped, order preserved
