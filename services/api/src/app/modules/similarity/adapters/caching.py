"""Bounded LRU cache decorator over `EmbeddingProvider` (D10 / ADR-011,
tasks.md 2b.1).

Implements `EmbeddingProvider` and wraps another one, so `domain` and
`application` never learn a cache exists -- installing or removing it is one
line in the composition root (`similarity/container.py`, Unit 8).

Key: `(inner.model_id, comparison_form)`, read FRESH on every call (not
frozen at construction) so a single cache instance correctly distinguishes
two models for the exact same text -- this is what "Model identifier in key"
(semantic-validation spec) actually pins down.

`capacity=0` is the kill switch (`EMBEDDING_CACHE_SIZE=0`): every call
bypasses the store entirely and this degenerates to a pure passthrough: no
stats are touched, nothing is ever stored. Every other test in this codebase
must still pass with the cache disabled this way.

Failures (`EmbeddingUnavailable` / `EmbeddingTimeout`) are NEVER cached: they
propagate untouched and nothing is inserted, so a provider that fails once
and recovers succeeds on the very next call (no negative caching).

Lock discipline: `threading.Lock` protects ONLY `OrderedDict` mutation/
ordering. The inner `embed()` call (the actual model forward pass) always
runs OUTSIDE the lock, so two threads racing on the same miss both compute
it and the second insert just overwrites an identical value -- accepted
(see design.md "Lock discipline") because `embed` is pure and holding a lock
across the forward pass would serialize the whole API.

Footprint: measured ~12.7 KB/entry (~6.2x design.md's original ~2 KB
estimate) via `tracemalloc` over a 512-entry fill -- `Vector` is a boxed
`list[float]`, not a packed float32 buffer. See design.md's "Efficiency: the
embedding cache" table for the full writeup and the Unit 8 follow-up (ADR-011
decides whether the real `sentence_transformers` adapter changes this).
"""

from __future__ import annotations

import logging
import threading
from collections import OrderedDict
from dataclasses import dataclass

from app.modules.similarity.contracts import EmbeddingProvider, Vector

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class CacheStats:
    """Snapshot of the cache's counters, exposed via `GET /health` (Unit 6b)."""

    hits: int = 0
    misses: int = 0
    evictions: int = 0
    size: int = 0
    capacity: int = 0


class CachingEmbeddingProvider:
    def __init__(self, inner: EmbeddingProvider, *, capacity: int) -> None:
        self._inner = inner
        self._capacity = capacity
        self._store: OrderedDict[tuple[str, str], Vector] = OrderedDict()
        self._lock = threading.Lock()
        self._hits = 0
        self._misses = 0
        self._evictions = 0
        self._logged_first_eviction = False
        self.dimensions = inner.dimensions

    @property
    def model_id(self) -> str:
        # Forwards to `inner` live (not cached at construction) -- see the
        # module docstring's "Key" note; this is what lets the same cache
        # instance observe a model change without being rebuilt.
        return self._inner.model_id

    def embed(self, text: str) -> Vector:
        if self._capacity <= 0:
            return self._inner.embed(text)

        key = (self._inner.model_id, text)
        with self._lock:
            if key in self._store:
                self._store.move_to_end(key)
                self._hits += 1
                return self._store[key]
            self._misses += 1

        logger.debug("embedding.cache.miss key_len=%d", len(text))
        vector = self._inner.embed(text)

        with self._lock:
            self._store[key] = vector
            self._store.move_to_end(key)
            if len(self._store) > self._capacity:
                self._store.popitem(last=False)
                self._evictions += 1
                if not self._logged_first_eviction:
                    self._logged_first_eviction = True
                    logger.info("embedding.cache.eviction capacity=%d", self._capacity)
        return vector

    def check_ready(self) -> None:
        self._inner.check_ready()

    def clear(self) -> None:
        """Drop all cached entries. Counters (`hits`/`misses`/`evictions`) are
        monotonic and NOT reset -- they track lifetime activity, same as the
        Prometheus-style counters design.md models them as."""
        with self._lock:
            self._store.clear()

    def close(self) -> None:
        """Reliability suggestion #11: forwards to `self._inner.close()` if
        the wrapped provider has one -- `BoundedEmbeddingProvider` is the
        one adapter in the stack that owns a resource (a `ThreadPool
        Executor`) needing explicit shutdown; a plain inner with no
        `close()` (e.g. `FakeEmbedder` in tests) is a no-op here. Duck-typed
        via `getattr` rather than a `close()` member on `similarity.
        contracts.EmbeddingProvider`'s published Protocol, which every
        OTHER adapter would then need to implement for no reason."""
        close = getattr(self._inner, "close", None)
        if callable(close):
            close()

    @property
    def stats(self) -> CacheStats:
        with self._lock:
            return CacheStats(
                hits=self._hits,
                misses=self._misses,
                evictions=self._evictions,
                size=len(self._store),
                capacity=self._capacity,
            )
