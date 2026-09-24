"""Composition root for the `similarity` embedding provider (tasks.md 6b.1,
extended 8.2 with the production stack order: ST -> bounded -> caching, and
the `model_id` format). Real `sentence_transformers` model LOADING lives in
`adapters/sentence_transformers.py::load_sentence_transformer` (the only
place that imports the third-party package); this file only WIRES an
already-built inner provider, so the wiring order itself is unit-testable
with a `FakeEmbedder` and no real model install.
"""

from __future__ import annotations

from typing import cast

from app.modules.similarity.adapters.bounded import BoundedEmbeddingProvider
from app.modules.similarity.adapters.caching import CachingEmbeddingProvider
from app.modules.similarity.contracts import EmbeddingProvider
from app.platform.settings import Settings


def wrap_with_cache(provider: EmbeddingProvider, *, capacity: int) -> EmbeddingProvider:
    """D10: outermost cache; `capacity=0` is the kill switch."""
    if capacity <= 0:
        return provider
    # `model_id` is a read-only `@property` on CachingEmbeddingProvider,
    # narrower than the Protocol's settable-variable member per mypy, but
    # structurally fine at runtime (read-only access is all callers do).
    return cast(EmbeddingProvider, CachingEmbeddingProvider(provider, capacity=capacity))


def build_model_id(*, model: str, revision: str) -> str:
    """design.md D10: `"<EMBEDDING_MODEL>@<EMBEDDING_MODEL_REVISION>"` --
    half of the cache key, and the value `GET /health`'s `embedding_model`
    reports is the bare `model` (see `main.py`'s lifespan, Unit 8) while
    THIS joined form is what `similarity.contracts.EmbeddingProvider.
    model_id` carries."""
    return f"{model}@{revision}"


def build_embedding_provider(base: EmbeddingProvider, *, settings: Settings) -> EmbeddingProvider:
    """Wires the fixed order design.md names: `base` (already constructed
    by the caller -- see `adapters/sentence_transformers.py::
    load_sentence_transformer` for the production case) -> `Bounded
    EmbeddingProvider` -> the cache (outermost; skipped when
    `EMBEDDING_CACHE_SIZE=0`, `wrap_with_cache`'s kill switch). Takes an
    already-built `base` instead of loading a model itself, so this
    function -- and therefore the wiring ORDER -- is unit-testable with a
    `FakeEmbedder`, no real model load required."""
    bounded: EmbeddingProvider = BoundedEmbeddingProvider(
        base,
        timeout_seconds=settings.embedding_timeout_seconds,
        max_concurrency=settings.embedding_max_concurrency,
    )
    return wrap_with_cache(bounded, capacity=settings.embedding_cache_size)
