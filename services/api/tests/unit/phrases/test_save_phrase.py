"""Unit tests for `SavePhrase` (tasks.md 3.3, design.md's Concurrency
section). Server-side re-validation: the verdict always comes from
`find_nearest_exact`, never `find_nearest`; a `DuplicateTextConflict` on
`add()` is retried once in a fresh transaction.
"""

from __future__ import annotations

from datetime import UTC, datetime

import pytest

from app.modules.phrases.adapters.in_memory_repository import InMemoryUnitOfWorkFactory
from app.modules.phrases.application.save_phrase import SavePhrase
from app.modules.phrases.contracts import DuplicateTextConflict, NewPhrase, ValidationStatus
from app.modules.phrases.domain.errors import EmptyPhraseText, PhraseTooLong
from app.modules.similarity.adapters.failing import FailingEmbedder
from app.modules.similarity.adapters.fake import FakeEmbedder
from app.modules.similarity.contracts import (
    EmbeddingTimeout,
    EmbeddingUnavailable,
    SimilarityPolicy,
)
from tests.contract_suite.vectors import PROBE, vector_at_distance
from tests.unit.phrases._uow_spies import ConflictRepo, CountingRepo, ProxyUnitOfWorkFactory

_TEXT = "comprar leche"
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


def _saver(factory: object, *, policy: SimilarityPolicy = _POLICY) -> SavePhrase:
    embedder = FakeEmbedder({_TEXT: PROBE})
    return SavePhrase(factory, embedder, policy, phrase_max_length=280, default_page_size=50)  # type: ignore[arg-type]


def test_save_without_validating_when_unique_persists_the_phrase() -> None:
    factory = InMemoryUnitOfWorkFactory()
    save = _saver(factory)
    result = save(_TEXT)
    assert result.conflict is None
    assert result.phrase is not None
    assert result.phrase.validation_status is ValidationStatus.UNIQUE
    assert result.phrase.similarity_score is None
    assert result.phrase.most_similar_phrase_id is None


def test_below_threshold_neighbour_is_recorded_on_a_unique_save() -> None:
    factory = InMemoryUnitOfWorkFactory()
    _seed(factory, ("other", 0.45))  # score 0.55, below threshold
    save = _saver(factory)
    result = save(_TEXT)
    assert result.conflict is None
    assert result.phrase is not None
    assert result.phrase.validation_status is ValidationStatus.UNIQUE
    assert result.phrase.similarity_score == 0.55
    assert result.phrase.most_similar_phrase_id is not None


def test_duplicate_without_confirmation_returns_a_conflict_and_persists_nothing() -> None:
    factory = InMemoryUnitOfWorkFactory()
    _seed(factory, ("existing", 0.05))  # score 0.95, duplicate
    save = _saver(factory)
    result = save(_TEXT)
    assert result.phrase is None
    assert result.conflict is not None
    assert result.conflict.is_duplicate is True
    assert result.conflict.score == 0.95
    with factory(read_only=True) as uow:
        assert len(uow.repo.list_recent(10)) == 1  # only "existing"


def test_duplicate_confirmed_persists_with_the_recorded_metadata() -> None:
    factory = InMemoryUnitOfWorkFactory()
    _seed(factory, ("existing", 0.08))  # score 0.92
    save = _saver(factory)
    result = save(_TEXT, confirm_duplicate=True)
    assert result.conflict is None
    assert result.phrase is not None
    assert result.phrase.validation_status is ValidationStatus.DUPLICATE_CONFIRMED
    assert result.phrase.similarity_score == 0.92


def test_confirm_flag_on_a_non_duplicate_still_saves_as_unique() -> None:
    factory = InMemoryUnitOfWorkFactory()
    save = _saver(factory)
    result = save(_TEXT, confirm_duplicate=True)
    assert result.conflict is None
    assert result.phrase is not None
    assert result.phrase.validation_status is ValidationStatus.UNIQUE


def test_save_never_calls_find_nearest_only_the_exact_scan() -> None:
    inner_factory = InMemoryUnitOfWorkFactory()
    _seed(inner_factory, ("existing", 0.05))
    counting: list[CountingRepo] = []

    def _wrap(repo: object) -> CountingRepo:
        spy = CountingRepo(repo)
        counting.append(spy)
        return spy

    factory = ProxyUnitOfWorkFactory(inner_factory, _wrap)
    save = _saver(factory)
    result = save(_TEXT)  # duplicate -> 409 path
    assert result.conflict is not None
    assert counting[-1].find_nearest_calls == 0
    assert counting[-1].find_nearest_exact_calls == 1
    assert counting[-1].find_matches_calls == 1


def test_duplicate_text_conflict_retries_once_in_a_fresh_uow_then_persists() -> None:
    inner_factory = InMemoryUnitOfWorkFactory()
    remaining: list[int | None] = [1]
    factory = ProxyUnitOfWorkFactory(
        inner_factory,
        lambda repo: ConflictRepo(repo, remaining=remaining, error=DuplicateTextConflict(_TEXT)),
    )
    save = _saver(factory)
    result = save(_TEXT)
    assert result.conflict is None
    assert result.phrase is not None


def test_always_raising_duplicate_conflict_still_returns_409_never_raises() -> None:
    inner_factory = InMemoryUnitOfWorkFactory()
    remaining: list[int | None] = [None]
    factory = ProxyUnitOfWorkFactory(
        inner_factory,
        lambda repo: ConflictRepo(repo, remaining=remaining, error=DuplicateTextConflict(_TEXT)),
    )
    save = _saver(factory)
    result = save(_TEXT)  # must not raise
    assert result.phrase is None
    assert result.conflict is not None
    assert result.conflict.is_duplicate is True


def test_409_payload_carries_the_full_validate_shaped_match_page() -> None:
    factory = InMemoryUnitOfWorkFactory()
    _seed(factory, ("m1", 0.02), ("m2", 0.05), ("m3", 0.08))  # all above threshold
    save = _saver(factory)
    result = save(_TEXT)
    assert result.conflict is not None
    assert len(result.conflict.matches) == 3
    assert result.conflict.has_more is False
    assert result.conflict.most_similar is not None
    assert result.conflict.most_similar.text == "m1"


@pytest.mark.parametrize("error", [EmbeddingUnavailable(), EmbeddingTimeout()])
def test_provider_failure_on_save_propagates_and_persists_nothing(error: Exception) -> None:
    factory = InMemoryUnitOfWorkFactory()
    inner = FakeEmbedder({_TEXT: PROBE})
    failing = FailingEmbedder(inner, fail_times=None, error=error)
    save = SavePhrase(factory, failing, _POLICY, phrase_max_length=280, default_page_size=50)
    with pytest.raises(type(error)):
        save(_TEXT, confirm_duplicate=True)  # confirm MUST NOT bypass validation
    with factory(read_only=True) as uow:
        assert uow.repo.list_recent(10) == []


def test_rejects_empty_text_before_embedding() -> None:
    factory = InMemoryUnitOfWorkFactory()
    embedder = FakeEmbedder({_TEXT: PROBE})
    save = SavePhrase(factory, embedder, _POLICY, phrase_max_length=280, default_page_size=50)
    with pytest.raises(EmptyPhraseText):
        save("   ")
    assert embedder.call_count == 0


def test_rejects_too_long_text_before_embedding() -> None:
    factory = InMemoryUnitOfWorkFactory()
    embedder = FakeEmbedder({_TEXT: PROBE})
    save = SavePhrase(factory, embedder, _POLICY, phrase_max_length=5, default_page_size=50)
    with pytest.raises(PhraseTooLong):
        save("way too long")
    assert embedder.call_count == 0
