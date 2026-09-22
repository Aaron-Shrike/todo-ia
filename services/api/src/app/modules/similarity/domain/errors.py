"""Domain-level embedding-provider errors.

Raised by `EmbeddingProvider` implementations (see `similarity/contracts.py`,
Unit 2). Plain, framework-free exceptions — `platform/errors.py` (Unit 6)
maps them to 503 `EMBEDDING_UNAVAILABLE` / 504 `EMBEDDING_TIMEOUT`.
"""

from __future__ import annotations


class EmbeddingUnavailable(Exception):
    """The embedding provider raised, or the model is not loaded."""


class EmbeddingTimeout(Exception):
    """Embedding exceeded `EMBEDDING_TIMEOUT_SECONDS` (or found no free
    concurrency slot within it — see `BoundedEmbeddingProvider`, Unit 8)."""
