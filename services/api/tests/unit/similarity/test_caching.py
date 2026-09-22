"""Unit tests for `CachingEmbeddingProvider` (tasks.md 2b.1, D10 / ADR-011).

Covers semantic-validation's "Embedding reuse within a bounded window" and
"Embedding cache is a pure optimization" requirements at the decorator level:
call counting, LRU (not FIFO) eviction, failures never cached, bit-identical
results after `clear()`, thread-safety under concurrent access, and the
`capacity=0` kill switch.
"""

from __future__ import annotations

import threading

import pytest

from app.modules.similarity.adapters.caching import CacheStats, CachingEmbeddingProvider
from app.modules.similarity.adapters.failing import FailingEmbedder
from app.modules.similarity.adapters.fake import FakeEmbedder
from app.modules.similarity.contracts import EmbeddingUnavailable


def test_repeated_calls_for_the_same_text_hit_the_cache_once() -> None:
    inner = FakeEmbedder({"comprar leche": [0.6, 0.8]})
    cache = CachingEmbeddingProvider(inner, capacity=10)

    assert cache.embed("comprar leche") == [0.6, 0.8]
    assert cache.embed("comprar leche") == [0.6, 0.8]

    assert inner.call_count == 1
    assert cache.stats == CacheStats(hits=1, misses=1, evictions=0, size=1, capacity=10)


def test_distinct_texts_each_miss_the_cache() -> None:
    inner = FakeEmbedder({"a": [1.0, 0.0], "b": [0.0, 1.0]})
    cache = CachingEmbeddingProvider(inner, capacity=10)

    cache.embed("a")
    cache.embed("b")

    assert inner.call_count == 2
    assert cache.stats.size == 2


def test_call_counting_differs_by_model_id_because_it_is_part_of_the_key() -> None:
    # The cache key is (provider.model_id, comparison_form) -- design.md D10.
    # Reading `inner.model_id` fresh on every call (rather than freezing it
    # at construction) is what makes the same cache instance correctly
    # distinguish two models for the exact same text.
    inner = FakeEmbedder({"hola": [1.0, 0.0]}, model_id="model-a@rev")
    cache = CachingEmbeddingProvider(inner, capacity=10)

    cache.embed("hola")
    inner.model_id = "model-b@rev"
    cache.embed("hola")

    assert inner.call_count == 2
    assert cache.stats.size == 2


def test_lru_eviction_keeps_the_recently_touched_entry_not_fifo() -> None:
    # size=2: insert A, B; touch A (hit); insert C -> LRU evicts B (the
    # least-recently-used entry), NOT A (which FIFO would have evicted as
    # the oldest insertion).
    inner = FakeEmbedder({"a": [1.0], "b": [2.0], "c": [3.0]})
    cache = CachingEmbeddingProvider(inner, capacity=2)

    cache.embed("a")  # miss 1 -> store: [a]
    cache.embed("b")  # miss 2 -> store: [a, b]
    cache.embed("a")  # hit    -> store order becomes: [b, a]
    cache.embed("c")  # miss 3 -> evicts b (LRU)          -> store: [a, c]

    assert inner.call_count == 3
    assert cache.stats.evictions == 1
    assert cache.stats.size == 2

    # a survived the eviction: still a hit, call count stays put. Checked
    # BEFORE touching b below, since re-inserting b would itself evict the
    # then-least-recently-used entry and disturb this assertion.
    cache.embed("a")
    assert inner.call_count == 3

    # b was evicted: requesting it again is a fresh miss.
    cache.embed("b")
    assert inner.call_count == 4


def test_a_one_shot_failure_is_never_cached_so_the_embedder_is_called_twice() -> None:
    inner = FakeEmbedder({"x": [1.0, 0.0]})
    failing = FailingEmbedder(inner, fail_times=1)
    cache = CachingEmbeddingProvider(failing, capacity=10)

    with pytest.raises(EmbeddingUnavailable):
        cache.embed("x")
    assert failing.call_count == 1

    # The failed attempt inserted nothing, so this is a genuine cache miss
    # that reaches the embedder again -- not a replay of a cached failure.
    assert cache.embed("x") == [1.0, 0.0]
    assert failing.call_count == 2
    # Both the failed attempt and the successful retry are genuine cache
    # misses (the key was absent from the store both times); only the
    # second one ends up stored, hence size=1.
    assert cache.stats == CacheStats(hits=0, misses=2, evictions=0, size=1, capacity=10)


def test_result_is_bit_identical_before_and_after_clear() -> None:
    inner = FakeEmbedder({"a": [0.1, 0.2, 0.97]})
    cache = CachingEmbeddingProvider(inner, capacity=10)

    before = cache.embed("a")
    cache.clear()
    after = cache.embed("a")

    assert before == after
    assert inner.call_count == 2  # clear() forces a real recomputation
    assert cache.stats.size == 1


def test_concurrent_access_never_exceeds_capacity() -> None:
    texts = [f"text-{i}" for i in range(200)]
    inner = FakeEmbedder({text: [float(i)] for i, text in enumerate(texts)})
    cache = CachingEmbeddingProvider(inner, capacity=50)

    def worker(offset: int) -> None:
        for i in range(200):
            cache.embed(texts[(i + offset) % len(texts)])

    threads = [threading.Thread(target=worker, args=(offset,)) for offset in (0, 37, 101, 173)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join()

    assert cache.stats.size <= 50
    assert cache.stats.capacity == 50


def test_capacity_zero_bypasses_the_store_entirely() -> None:
    inner = FakeEmbedder({"a": [1.0, 0.0]})
    cache = CachingEmbeddingProvider(inner, capacity=0)

    cache.embed("a")
    cache.embed("a")

    assert inner.call_count == 2
    assert cache.stats == CacheStats(hits=0, misses=0, evictions=0, size=0, capacity=0)
