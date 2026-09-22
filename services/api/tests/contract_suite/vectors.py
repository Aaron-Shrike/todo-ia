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
