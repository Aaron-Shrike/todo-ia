"""Published boundary of `similarity` (tasks.md 2.1).

`phrases` MAY import ONLY this module, never `similarity.domain`/
`.adapters` (`import-linter`'s `phrases-only-similarity-contracts`
contract -- see `.importlinter`'s `ignore_imports` note on that contract
for the re-export edges below).

`cosine_distance` is re-exported beyond design.md's literal "PUBLISHED:
EmbeddingProvider, Vector, SimilarityPolicy, errors" list:
`phrases/adapters/in_memory_repository.py` needs it for `find_nearest`
"using the domain cosine" (design.md), and the boundary above forbids it
from reaching `similarity.domain.cosine` directly.

`KEY_EPSILON` (design.md's own code sample, D16's keyset tolerance grid) is
now in `__all__`: Unit 2d wires its consumer, `find_matches`'s
`(bucket, id)` ordering, in `phrases/adapters/in_memory_repository.py`.
"""

from __future__ import annotations

from typing import Protocol

from .domain.cosine import cosine_distance
from .domain.errors import EmbeddingTimeout, EmbeddingUnavailable
from .domain.policy import ROUNDING_DECIMALS, ROUNDING_UNIT, SimilarityPolicy
from .domain.vector import Vector

KEY_EPSILON = 1e-6  # keyset tolerance grid (D16), domain constant

__all__ = [
    "KEY_EPSILON",
    "ROUNDING_DECIMALS",
    "ROUNDING_UNIT",
    "EmbeddingProvider",
    "EmbeddingTimeout",
    "EmbeddingUnavailable",
    "SimilarityPolicy",
    "Vector",
    "cosine_distance",
]


class EmbeddingProvider(Protocol):
    """Swappable embedding port (ADR-002's microservice seam: the decision
    record on why only embedding generation, not similarity search, can be
    extracted to its own service)."""

    model_id: str  # "<model>@<revision sha>" -- part of the cache key
    # (D10: the design decision to place a bounded LRU cache over this port,
    # keyed on (model_id, comparison_form), so identical text is embedded
    # once).
    dimensions: int

    def embed(self, text: str) -> Vector:
        """PRE: `text` already normalized. POST: L2-normalized, `len ==
        dimensions`."""
        ...

    def check_ready(self) -> None:
        """Raises `EmbeddingUnavailable` if the provider cannot serve."""
        ...
