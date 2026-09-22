"""Shared test-vector helpers for repository tests.

Used by both `tests/contract_suite/repository_contract.py` (the adapter-
agnostic contract suite) and `tests/unit/phrases/test_in_memory_repository.py`
(in-memory-specific tests) so the two never drift apart -- the same failure
mode the contract suite itself exists to prevent, applied to its own test
fixtures.
"""

from __future__ import annotations

import math

from app.modules.similarity.contracts import Vector

# Unit probe; `vector_at_distance(d)` builds a unit 2D vector whose cosine
# distance from PROBE is exactly `d` (up to float64 precision).
PROBE: Vector = [1.0, 0.0]


def vector_at_distance(distance: float) -> list[float]:
    angle = math.acos(1.0 - distance)
    return [math.cos(angle), math.sin(angle)]
