"""Unit tests for `ValidatePhrase` (tasks.md 3.1). Stored phrases sit at a
controlled cosine distance from the query vector `PROBE`, via
`tests/contract_suite/vectors.py`'s `vector_at_distance`.
"""

from __future__ import annotations

import random
from datetime import UTC, datetime

import pytest
from tests.contract_suite.vectors import PROBE, vector_at_distance
from tests.unit.phrases._uow_spies import ProxyUnitOfWorkFactory, WrongNearestRepo

from app.modules.phrases.adapters.in_memory_repository import InMemoryUnitOfWorkFactory
from app.modules.phrases.application.validate_phrase import ValidatePhrase
from app.modules.phrases.contracts import Neighbor, NewPhrase, ValidationStatus
from app.modules.phrases.domain.errors import EmptyPhraseText, PhraseTooLong
from app.modules.similarity.adapters.failing import FailingEmbedder
from app.modules.similarity.adapters.fake import FakeEmbedder
from app.modules.similarity.contracts import (
    EmbeddingTimeout,
    EmbeddingUnavailable,
    SimilarityPolicy,
)

_QUERY_TEXT = "query text"
_POLICY = SimilarityPolicy(threshold=0.80)


def _seed(factory: object, *entries: tuple[str, float]) -> None:
    """Add phrases at controlled cosine distances from `PROBE`."""
    with factory() as uow:  # type: ignore[operator]
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


def _validator(
    factory: object, *, max_length: int = 280, policy: SimilarityPolicy = _POLICY
) -> tuple[ValidatePhrase, FakeEmbedder]:
    embedder = FakeEmbedder({_QUERY_TEXT: PROBE})
    return ValidatePhrase(factory, embedder, policy, phrase_max_length=max_length), embedder  # type: ignore[arg-type]


def test_empty_store_returns_null_verdict_and_empty_matches() -> None:
    factory = InMemoryUnitOfWorkFactory()
    validate, _ = _validator(factory)
    result = validate(_QUERY_TEXT, limit=50)
    assert result.is_duplicate is False
    assert result.score is None
    assert result.most_similar is None
    assert result.matches == []
    assert result.has_more is False
    assert result.next_cursor is None


def test_best_below_threshold_reports_score_and_most_similar_with_empty_matches() -> None:
    factory = InMemoryUnitOfWorkFactory()
    _seed(factory, ("worse", 0.60), ("closer", 0.45))  # scores 0.40 and 0.55
    validate, _ = _validator(factory)
    result = validate(_QUERY_TEXT, limit=50)
    assert result.is_duplicate is False
    assert result.score == 0.55
    assert result.most_similar is not None
    assert result.most_similar.text == "closer"
    assert result.matches == []


def test_most_similar_equals_first_match_when_matches_non_empty() -> None:
    factory = InMemoryUnitOfWorkFactory()
    _seed(factory, ("second", 0.15), ("first", 0.05))  # scores 0.85 and 0.95
    validate, _ = _validator(factory)
    result = validate(_QUERY_TEXT, limit=50)
    assert result.is_duplicate is True
    assert result.matches[0].text == "first"
    assert result.most_similar is not None
    assert result.most_similar.text == "first"
    assert result.most_similar.score == result.matches[0].score == 0.95


def test_reconciliation_rule_prefers_matches_zero_over_a_worse_find_nearest_neighbour() -> None:
    inner_factory = InMemoryUnitOfWorkFactory()
    _seed(inner_factory, ("true best", 0.05))  # score 0.95, above threshold
    wrong_neighbor = Neighbor(id=999, text="wrong", distance=0.9)  # score 0.10
    factory = ProxyUnitOfWorkFactory(
        inner_factory, lambda repo: WrongNearestRepo(repo, wrong_neighbor)
    )
    validate, _ = _validator(factory)
    result = validate(_QUERY_TEXT, limit=50)
    assert result.is_duplicate is True
    assert result.most_similar is not None
    assert result.most_similar.text == "true best"
    assert result.score == 0.95


def test_property_most_similar_equals_matches_zero_over_random_corpora() -> None:
    rng = random.Random(20240930)
    for trial in range(5):
        factory = InMemoryUnitOfWorkFactory()
        entries = [(f"p{trial}-{i}", rng.uniform(0.0, 0.4)) for i in range(15)]
        _seed(factory, *entries)
        validate, _ = _validator(factory)
        result = validate(_QUERY_TEXT, limit=50)
        if result.matches:
            top = result.matches[0]
            assert result.most_similar is not None
            assert (result.most_similar.id, result.most_similar.score) == (top.id, top.score)


def test_statelessness_nothing_persisted_after_validate() -> None:
    factory = InMemoryUnitOfWorkFactory()
    _seed(factory, ("existing", 0.05))
    validate, _ = _validator(factory)
    validate(_QUERY_TEXT, limit=50)
    with factory(read_only=True) as uow:
        assert len(uow.repo.list_recent(10)) == 1  # only the seeded phrase


def test_threshold_zero_admits_everything_but_only_first_page_is_returned() -> None:
    factory = InMemoryUnitOfWorkFactory()
    entries = [(f"p{i}", i * 0.003) for i in range(500)]
    _seed(factory, *entries)
    validate, _ = _validator(factory, policy=SimilarityPolicy(threshold=0.0))
    result = validate(_QUERY_TEXT, limit=50)
    assert result.is_duplicate is True
    assert len(result.matches) == 50
    assert result.has_more is True
    assert result.next_cursor is not None


def test_threshold_changed_via_env_reflects_the_injected_policy() -> None:
    # semantic-validation spec, "Threshold changed via env": a non-default policy
    # (SIMILARITY_THRESHOLD=0.95) and a best score of 0.90 -> not a duplicate, and the
    # VERDICT'S OWN `threshold` field reports 0.95, not a hardcoded default.
    factory = InMemoryUnitOfWorkFactory()
    _seed(factory, ("closest", 0.10))  # score 0.90
    validate, _ = _validator(factory, policy=SimilarityPolicy(threshold=0.95))
    result = validate(_QUERY_TEXT, limit=50)
    assert result.threshold == 0.95
    assert result.is_duplicate is False
    assert result.score == 0.90
    assert result.most_similar is not None
    assert result.most_similar.score == 0.90
    assert result.matches == []


@pytest.mark.parametrize("error", [EmbeddingUnavailable(), EmbeddingTimeout()])
def test_provider_failure_propagates_and_nothing_persists(error: Exception) -> None:
    factory = InMemoryUnitOfWorkFactory()
    inner = FakeEmbedder({_QUERY_TEXT: PROBE})
    failing = FailingEmbedder(inner, fail_times=None, error=error)
    validate = ValidatePhrase(factory, failing, _POLICY, phrase_max_length=280)
    with pytest.raises(type(error)):
        validate(_QUERY_TEXT, limit=50)
    with factory(read_only=True) as uow:
        assert uow.repo.list_recent(10) == []


def test_rejects_empty_text_before_embedding() -> None:
    factory = InMemoryUnitOfWorkFactory()
    validate, embedder = _validator(factory)
    with pytest.raises(EmptyPhraseText):
        validate("   \t\n", limit=50)
    assert embedder.call_count == 0


def test_rejects_too_long_text_before_embedding() -> None:
    factory = InMemoryUnitOfWorkFactory()
    validate, embedder = _validator(factory, max_length=5)
    with pytest.raises(PhraseTooLong) as excinfo:
        validate("way too long", limit=50)
    assert excinfo.value.max_length == 5
    assert embedder.call_count == 0


def test_widened_bound_admits_a_borderline_row_that_the_tail_rule_then_excludes() -> None:
    # A: score 0.90, a clear match. B: raw cosine 0.79994 -> score 0.7999, admitted by the
    # widened SQL bound (max_distance = 0.2001 at t = 0.80) but excluded by the exact Decimal
    # comparison. C: makes the repo's own `+1` probe report `has_more=True`, which the tail
    # rule must override to False once B truncates the page.
    factory = InMemoryUnitOfWorkFactory()
    _seed(factory, ("A", 0.10), ("B", 0.20006), ("C", 0.20008))
    validate, _ = _validator(factory)
    result = validate(_QUERY_TEXT, limit=2)
    assert [m.text for m in result.matches] == ["A"]
    assert result.has_more is False
    assert result.next_cursor is None
