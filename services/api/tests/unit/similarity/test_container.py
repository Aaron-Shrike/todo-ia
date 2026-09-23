"""Unit tests for the `similarity` composition root's Unit 8 additions
(tasks.md 8.2): the fixed wiring order (ST -> bounded -> caching, outermost)
and the `model_id` format. `build_embedding_provider` takes an
already-built inner provider (a `FakeEmbedder` here) rather than loading a
real model itself, so the WIRING ORDER is unit-testable without
`sentence_transformers`/`torch` installed.
"""

from __future__ import annotations

from app.modules.similarity.adapters.bounded import BoundedEmbeddingProvider
from app.modules.similarity.adapters.caching import CachingEmbeddingProvider
from app.modules.similarity.adapters.fake import FakeEmbedder
from app.modules.similarity.container import build_embedding_provider, build_model_id
from app.platform.settings import Settings


def test_build_model_id_joins_model_and_revision_with_at() -> None:
    assert build_model_id(model="org/checkpoint", revision="a" * 40) == (
        "org/checkpoint@" + "a" * 40
    )


def _settings(**overrides: object) -> Settings:
    return Settings(
        database_url="postgresql+psycopg://test:test@localhost:5432/test", **overrides
    )


def test_the_wired_provider_caches_repeated_calls_through_the_bounded_layer() -> None:
    inner = FakeEmbedder({"hola": [0.1, 0.2]})
    settings = _settings(
        embedding_timeout_seconds=1.0, embedding_max_concurrency=2, embedding_cache_size=10
    )

    provider = build_embedding_provider(inner, settings=settings)

    assert provider.embed("hola") == [0.1, 0.2]
    assert provider.embed("hola") == [0.1, 0.2]
    # A cache hit never reaches the inner (bounded-wrapped) provider again.
    assert inner.call_count == 1
    assert isinstance(provider, CachingEmbeddingProvider)


def test_embedding_cache_size_zero_bypasses_the_cache_kill_switch() -> None:
    # Triangulation: a distinct settings value (cache disabled) must
    # produce a genuinely different wiring, not a hardcoded cache wrapper.
    inner = FakeEmbedder({"hola": [0.1, 0.2]})
    settings = _settings(
        embedding_timeout_seconds=1.0, embedding_max_concurrency=2, embedding_cache_size=0
    )

    provider = build_embedding_provider(inner, settings=settings)

    provider.embed("hola")
    provider.embed("hola")

    # No cache installed -> every call reaches the inner provider again.
    assert inner.call_count == 2
    assert not isinstance(provider, CachingEmbeddingProvider)


def test_the_wired_provider_still_forwards_model_id_and_dimensions() -> None:
    inner = FakeEmbedder({"hola": [0.1, 0.2, 0.3]}, model_id="fake@rev")
    settings = _settings(embedding_cache_size=0)

    provider = build_embedding_provider(inner, settings=settings)

    assert provider.model_id == "fake@rev"
    assert provider.dimensions == 3


def test_timeout_and_concurrency_are_threaded_to_the_bounded_layer_not_swapped() -> None:
    # Reliability suggestion #10: the previous tests only ever asserted
    # `model_id`/`dimensions` forwarding and cache hit/miss counts through a
    # non-blocking `FakeEmbedder` -- a bug that SWAPPED
    # `timeout_seconds`/`max_concurrency` in `build_embedding_provider`
    # would pass every existing test unnoticed. `embedding_cache_size=0`
    # bypasses the cache so the returned provider IS the
    # `BoundedEmbeddingProvider` itself, not wrapped.
    inner = FakeEmbedder({"hola": [0.1, 0.2]})
    settings = _settings(
        embedding_timeout_seconds=7.5, embedding_max_concurrency=3, embedding_cache_size=0
    )

    provider = build_embedding_provider(inner, settings=settings)

    assert isinstance(provider, BoundedEmbeddingProvider)
    assert provider._timeout_seconds == 7.5
    # `ThreadPoolExecutor(max_workers=...)` and `BoundedSemaphore(...)` both
    # observably carry the concurrency bound they were constructed with.
    assert provider._executor._max_workers == 3
    assert provider._semaphore._initial_value == 3
