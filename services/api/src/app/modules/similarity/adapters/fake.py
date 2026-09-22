"""`EmbeddingProvider` test double keyed on a lookup table (tasks.md 2.2).
`call_count` proves how many times the model was actually invoked (D10's
efficiency claims). Tied texts get the SAME vector object, so a distance
tie is genuinely equal, not merely equal after rounding.
"""

from __future__ import annotations

from app.modules.similarity.contracts import Vector


class FakeEmbedder:
    def __init__(
        self,
        vectors: dict[str, Vector],
        *,
        model_id: str = "fake@0000000000000000000000000000000000000000",
        dimensions: int | None = None,
    ) -> None:
        self._vectors = vectors
        self.model_id = model_id
        self.dimensions = dimensions if dimensions is not None else _infer_dimensions(vectors)
        self.call_count = 0

    def embed(self, text: str) -> Vector:
        self.call_count += 1
        return self._vectors[text]

    def check_ready(self) -> None:
        return None


def _infer_dimensions(vectors: dict[str, Vector]) -> int:
    return len(next(iter(vectors.values()))) if vectors else 0
