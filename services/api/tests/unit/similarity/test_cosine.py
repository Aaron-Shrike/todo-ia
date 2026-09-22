"""Unit tests for the pure-Python cosine similarity/distance oracle.

Scenarios from `specs/semantic-validation/spec.md`'s "Cosine similarity"
requirement (tasks.md Unit 1 / 1.2): Identical, Orthogonal, Oracle agreement
(pure-Python side). Clamping/rounding/threshold decision live in
`test_policy.py`.
"""

import math

from app.modules.similarity.domain.cosine import cosine_distance, cosine_similarity


def test_identical_vectors_score_one() -> None:
    vector = (0.6, 0.8, 0.0)
    assert cosine_similarity(vector, vector) == 1.0
    assert cosine_distance(vector, vector) == 0.0


def test_orthogonal_vectors_score_zero() -> None:
    a, b = (1.0, 0.0), (0.0, 1.0)
    assert cosine_similarity(a, b) == 0.0
    assert cosine_distance(a, b) == 1.0


def test_oracle_agrees_with_the_dot_product_for_l2_normalized_vectors() -> None:
    # EmbeddingProvider.embed() returns L2-normalized vectors, for which
    # cosine similarity collapses to the plain dot product — the "Oracle
    # agreement" scenario's pure-Python side (pgvector side: Unit 5a).
    raw_a, raw_b = (3.0, 4.0), (5.0, 12.0)
    norm_a = math.sqrt(sum(x * x for x in raw_a))
    norm_b = math.sqrt(sum(x * x for x in raw_b))
    a = tuple(x / norm_a for x in raw_a)
    b = tuple(x / norm_b for x in raw_b)
    dot_product = sum(x * y for x, y in zip(a, b, strict=True))
    assert math.isclose(cosine_similarity(a, b), dot_product, rel_tol=1e-12)
