"""Composition root for the `similarity` embedding provider (tasks.md 6b.1).
Real `sentence_transformers` wiring (design.md's "Efficiency" stack) is
Unit 8's job -- not built here. Tests build a `FakeEmbedder`/
`FailingEmbedder` directly and wrap it with `wrap_with_cache` below, the
one piece of wiring independent of which concrete provider it wraps.
"""

from __future__ import annotations

from typing import cast

from app.modules.similarity.adapters.caching import CachingEmbeddingProvider
from app.modules.similarity.contracts import EmbeddingProvider


def wrap_with_cache(provider: EmbeddingProvider, *, capacity: int) -> EmbeddingProvider:
    """D10: outermost cache; `capacity=0` is the kill switch."""
    if capacity <= 0:
        return provider
    # `model_id` is a read-only `@property` on CachingEmbeddingProvider,
    # narrower than the Protocol's settable-variable member per mypy, but
    # structurally fine at runtime (read-only access is all callers do).
    return cast(EmbeddingProvider, CachingEmbeddingProvider(provider, capacity=capacity))
