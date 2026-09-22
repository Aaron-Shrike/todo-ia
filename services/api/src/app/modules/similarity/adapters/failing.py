"""`EmbeddingProvider` doubles that fail on demand (tasks.md 2.2): raises
for the first `fail_times` calls (one-shot at 1, permanent at `None`, never
at `0`), then delegates to `inner`.
"""

from __future__ import annotations

from app.modules.similarity.contracts import EmbeddingProvider, EmbeddingUnavailable, Vector


class FailingEmbedder:
    def __init__(
        self,
        inner: EmbeddingProvider,
        *,
        fail_times: int | None = None,
        error: Exception | None = None,
    ) -> None:
        self._inner = inner
        self._fail_times = fail_times
        self._error = error if error is not None else EmbeddingUnavailable()
        self.model_id = inner.model_id
        self.dimensions = inner.dimensions
        self.call_count = 0

    def embed(self, text: str) -> Vector:
        self.call_count += 1
        if self._is_down(self.call_count):
            raise self._error
        return self._inner.embed(text)

    def check_ready(self) -> None:
        # Reflects the SAME configured failure mode `embed()` uses, without
        # consuming a call: a `FailingEmbedder` still inside its failure
        # window must report itself unhealthy, not silently delegate to a
        # healthy `inner`. `self.call_count + 1` asks "would the NEXT
        # `embed()` call fail", so `embed()`'s own call-counting semantics
        # stay untouched by readiness checks.
        if self._is_down(self.call_count + 1):
            raise self._error
        self._inner.check_ready()

    def _is_down(self, attempt: int) -> bool:
        return self._fail_times is None or attempt <= self._fail_times
