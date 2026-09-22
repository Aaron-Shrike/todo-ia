"""Pure-Python cosine similarity and distance.

The domain's oracle: a framework-free reference the pgvector repository's SQL
(Unit 5a) is tested against within 1e-5 (float32 storage error), per the
"Oracle agreement" scenario. Divides by both norms rather than assuming
inputs are already L2-normalized, so it is correct for arbitrary vectors.
"""

from __future__ import annotations

import math

from .vector import Vector


def cosine_similarity(a: Vector, b: Vector) -> float:
    """Raw cosine similarity between two non-zero vectors of equal length.

    May fall slightly outside [-1, 1] due to float error (e.g.
    1.0000000002). Performs no clamping or rounding — see `SimilarityPolicy`.
    """
    dot_product = sum(x * y for x, y in zip(a, b, strict=True))
    norm_a = math.sqrt(sum(x * x for x in a))
    norm_b = math.sqrt(sum(y * y for y in b))
    if norm_a == 0.0 or norm_b == 0.0:
        return 0.0
    return dot_product / (norm_a * norm_b)


def cosine_distance(a: Vector, b: Vector) -> float:
    """`1 - cosine_similarity(a, b)`, mirroring pgvector's `<=>` operator,
    consumed by `SimilarityPolicy.score` (see `policy.py`)."""
    return 1.0 - cosine_similarity(a, b)
