"""Cache-interplay tests across the three Unit 3 use cases (tasks.md 3.4,
design.md "Efficiency: the embedding cache"). Proves the cache's ONLY
observable effect is fewer forward passes -- every verdict, match page and
save still issues a live repository query, and the response is unaffected
by cache state.
"""

from __future__ import annotations

from datetime import UTC, datetime

from tests.contract_suite.vectors import PROBE, vector_at_distance
from tests.unit.phrases._uow_spies import CountingRepo, ProxyUnitOfWorkFactory

from app.modules.phrases.adapters.in_memory_repository import InMemoryUnitOfWorkFactory
from app.modules.phrases.application.list_matches import ListMatches
from app.modules.phrases.application.save_phrase import SavePhrase
from app.modules.phrases.application.validate_phrase import ValidatePhrase
from app.modules.phrases.contracts import NewPhrase, ValidationStatus
from app.modules.similarity.adapters.caching import CachingEmbeddingProvider
from app.modules.similarity.adapters.fake import FakeEmbedder
from app.modules.similarity.contracts import SimilarityPolicy

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


def test_validate_then_save_share_one_embedding_call() -> None:
    factory = InMemoryUnitOfWorkFactory()
    inner = FakeEmbedder({_TEXT: PROBE})
    cached = CachingEmbeddingProvider(inner, capacity=8)
    validate = ValidatePhrase(factory, cached, _POLICY, phrase_max_length=280)
    save = SavePhrase(factory, cached, _POLICY, phrase_max_length=280, default_page_size=50)

    validate(_TEXT, limit=50)
    save(_TEXT)

    assert inner.call_count == 1


def test_three_match_pages_keep_the_embedding_call_count_at_one() -> None:
    factory = InMemoryUnitOfWorkFactory()
    _seed(factory, *[(f"p{i}", 0.001 + i * 0.0015) for i in range(120)])  # all above threshold
    inner = FakeEmbedder({_TEXT: PROBE})
    cached = CachingEmbeddingProvider(inner, capacity=8)
    validate = ValidatePhrase(factory, cached, _POLICY, phrase_max_length=280)
    list_matches = ListMatches(factory, cached, _POLICY, phrase_max_length=280)

    page1 = validate(_TEXT, limit=50)
    assert page1.next_cursor is not None
    page2 = list_matches(_TEXT, cursor=page1.next_cursor, limit=50)
    assert page2.next_cursor is not None
    list_matches(_TEXT, cursor=page2.next_cursor, limit=50)

    assert inner.call_count == 1


def test_repository_counters_prove_every_page_issues_a_live_query() -> None:
    inner_factory = InMemoryUnitOfWorkFactory()
    _seed(inner_factory, *[(f"p{i}", 0.001 + i * 0.0015) for i in range(120)])
    counters: list[CountingRepo] = []

    def _wrap(repo: object) -> CountingRepo:
        spy = CountingRepo(repo)
        counters.append(spy)
        return spy

    factory = ProxyUnitOfWorkFactory(inner_factory, _wrap)
    inner = FakeEmbedder({_TEXT: PROBE})
    cached = CachingEmbeddingProvider(inner, capacity=8)
    validate = ValidatePhrase(factory, cached, _POLICY, phrase_max_length=280)
    list_matches = ListMatches(factory, cached, _POLICY, phrase_max_length=280)

    page1 = validate(_TEXT, limit=50)
    assert page1.next_cursor is not None
    list_matches(_TEXT, cursor=page1.next_cursor, limit=50)

    find_matches_calls = sum(c.find_matches_calls for c in counters)
    assert find_matches_calls == 2  # one per page, cache or not
    assert counters[0].find_nearest_calls == 1  # validate's single find_nearest


def test_validation_response_is_identical_cold_warm_and_disabled_cache() -> None:
    def _fresh_factory() -> InMemoryUnitOfWorkFactory:
        factory = InMemoryUnitOfWorkFactory()
        _seed(factory, ("existing", 0.05))
        return factory

    inner = FakeEmbedder({_TEXT: PROBE})

    cold_cache = CachingEmbeddingProvider(inner, capacity=8)
    validate_cold = ValidatePhrase(_fresh_factory(), cold_cache, _POLICY, phrase_max_length=280)
    cold = validate_cold(_TEXT, limit=50)

    warm_cache = CachingEmbeddingProvider(inner, capacity=8)
    warm_cache.embed(_TEXT)  # pre-warm
    validate_warm = ValidatePhrase(_fresh_factory(), warm_cache, _POLICY, phrase_max_length=280)
    warm = validate_warm(_TEXT, limit=50)

    disabled_cache = CachingEmbeddingProvider(inner, capacity=0)
    validate_disabled = ValidatePhrase(
        _fresh_factory(), disabled_cache, _POLICY, phrase_max_length=280
    )
    disabled = validate_disabled(_TEXT, limit=50)

    assert cold == warm == disabled
