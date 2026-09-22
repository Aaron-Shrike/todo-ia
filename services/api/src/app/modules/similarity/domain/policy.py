"""Similarity decision policy: clamped/rounded scoring and threshold decision.

Turns a raw cosine distance into the 4-decimal score every response,
comparison and persisted row uses (design.md D13, "Score rounding is the
contract, not a formatting step").
"""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal

ROUNDING_DECIMALS = 4
ROUNDING_UNIT = 1e-4  # domain constant, deliberately NOT configuration (D13)


@dataclass(frozen=True)
class SimilarityPolicy:
    """Decides duplicates from a `SIMILARITY_THRESHOLD` in [0, 1].

    Threshold *validation* is owned by `platform/settings.py` (Unit 6); this
    class assumes `threshold` already lies within [0, 1].
    """

    threshold: float

    def score(self, raw_distance: float) -> float:
        """Clamp `1 - raw_distance` to [0, 1], then round to 4 decimals (D13)."""
        clamped = min(1.0, max(0.0, 1.0 - raw_distance))
        return round(clamped, ROUNDING_DECIMALS)

    def is_duplicate(self, score: float) -> bool:
        """Threshold decision on an already clamped, rounded `score`.

        Compared as `Decimal(str(x))` so a threshold with more than 4
        decimals (e.g. 0.80005) is exact, not subject to binary-float error.
        """
        return Decimal(str(score)) >= Decimal(str(self.threshold))

    def includes(self, raw_distance: float) -> bool:
        """`is_duplicate(score(raw_distance))` — the predicate every caller
        (validate's verdict, `find_matches`'s row filter) applies."""
        return self.is_duplicate(self.score(raw_distance))

    def max_distance(self) -> float:
        """Widened SQL bound (D13): `1 - threshold + ROUNDING_UNIT`, `2.0` at
        `threshold == 0` (a clamped score of 0 admits every phrase). A
        deliberate SUPERSET of `includes()`: SQL over-selects, the
        application is the sole arbiter."""
        if self.threshold == 0.0:
            return 2.0
        return 1.0 - self.threshold + ROUNDING_UNIT
