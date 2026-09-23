"""Shared test-vector helpers for repository tests.

Used by both `tests/contract_suite/repository_contract.py` (the adapter-
agnostic contract suite) and `tests/unit/phrases/test_in_memory_repository.py`
(in-memory-specific tests) so the two never drift apart -- the same failure
mode the contract suite itself exists to prevent, applied to its own test
fixtures.

`_DIMENSIONS` matches migration 0001's `vector(384)` column (Unit 5a):
vectors are zero-padded to it, unaffecting cosine distance, so both
adapters share the exact same fixtures via `MatchesContractSuite`.
"""

from __future__ import annotations

import math

from app.modules.similarity.contracts import Vector

_DIMENSIONS = 384


def _pad(head: list[float]) -> list[float]:
    return head + [0.0] * (_DIMENSIONS - len(head))


# Unit probe; `vector_at_distance(d)`'s cosine distance from PROBE is `d`.
PROBE: Vector = _pad([1.0, 0.0])


def vector_at_distance(distance: float) -> list[float]:
    angle = math.acos(1.0 - distance)
    return _pad([math.cos(angle), math.sin(angle)])


# Unit 14 addition: a standard basis vector (cosine similarity exactly 0
# between any two distinct indices, safely under any realistic
# `SIMILARITY_THRESHOLD`), for tests that save several DIFFERENT phrases in
# the same run and need every pairwise score to be unambiguously "not a
# duplicate" -- `vector_at_distance` alone cannot guarantee that for more
# than one non-PROBE vector at a time, since every vector it returns lives
# in the same 2D plane as PROBE.
def orthogonal_vector(index: int) -> Vector:
    vector = [0.0] * _DIMENSIONS
    vector[index] = 1.0
    return vector
