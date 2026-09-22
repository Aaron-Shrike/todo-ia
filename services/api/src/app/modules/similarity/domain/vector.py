"""`Vector`: an ordered sequence of floats produced by an `EmbeddingProvider`
(see `similarity/contracts.py`, Unit 2). `EMBEDDING_DIMENSIONS` is a config
concern (Unit 6), not enforced here."""

from __future__ import annotations

from collections.abc import Sequence

Vector = Sequence[float]
