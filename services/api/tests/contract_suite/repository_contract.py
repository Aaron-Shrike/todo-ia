"""Shared `PhraseRepository`/`UnitOfWork` contract suite (tasks.md 2.3;
design.md: "a shared contract test suite ... so the fast fake cannot drift
from the real one"). Subclass `RepositoryContractSuite`, override the
`uow_factory` fixture. Only in-memory is registered in Unit 2; pgvector
registers in Unit 5a/5b. Not `test_*.py` on purpose -- a shared base,
collected only through subclasses.

`find_matches` review-budget deferral: see `phrases/contracts.py`'s module
docstring (single source of truth for that note).
"""

from __future__ import annotations

import math
from datetime import UTC, datetime

import pytest

from app.modules.phrases.contracts import Isolation, NewPhrase, UnitOfWorkFactory, ValidationStatus
from app.modules.similarity.contracts import Vector

# Unit probe; `_vector_at_distance(d)` builds a unit 2D vector whose cosine
# distance from PROBE is exactly `d` (up to float64 precision).
PROBE: Vector = [1.0, 0.0]


def _vector_at_distance(distance: float) -> list[float]:
    angle = math.acos(1.0 - distance)
    return [math.cos(angle), math.sin(angle)]


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
