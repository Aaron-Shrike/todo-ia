"""Timeout + concurrency bound over an inner `EmbeddingProvider` (tasks.md
8.1, design.md "Embedding timeout and concurrency bound"). Sits INSIDE the
cache in the composition order (`similarity/container.py`, Unit 8: ST ->
bounded -> caching), so a cache hit never touches the executor.

Honest limit (design.md, verbatim): a running model forward pass is not
cancellable. After a caller times out, the worker thread keeps running
until it finishes and keeps its concurrency slot -- the semaphore is
released by the FUTURE's own done-callback, never by the timed-out caller,
so a stuck model saturates the bound and later requests fail fast with
`EmbeddingTimeout` instead of piling up threads. The late result is
discarded: never returned to any caller, and therefore -- since the outer
`CachingEmbeddingProvider` only inserts on a value its own `embed()` call
actually returned -- never cached.

Exception translation: a `concurrent.futures.TimeoutError` on `future.
result()` becomes `EmbeddingTimeout`; any inner exception that is NOT
already an `EmbeddingUnavailable`/`EmbeddingTimeout` becomes
`EmbeddingUnavailable` (design.md "any inner exception becomes/propagates
as EmbeddingUnavailable") -- an already-typed domain error from the inner
provider (e.g. `FailingEmbedder`) passes through unchanged.
"""

from __future__ import annotations

import threading
from concurrent.futures import Future, ThreadPoolExecutor
from concurrent.futures import TimeoutError as FutureTimeoutError

from app.modules.similarity.contracts import (
    EmbeddingProvider,
    EmbeddingTimeout,
    EmbeddingUnavailable,
    Vector,
)


class BoundedEmbeddingProvider:
    def __init__(
        self, inner: EmbeddingProvider, *, timeout_seconds: float, max_concurrency: int
    ) -> None:
        self._inner = inner
        self._timeout_seconds = timeout_seconds
        self._executor = ThreadPoolExecutor(max_workers=max_concurrency)
        self._semaphore = threading.BoundedSemaphore(max_concurrency)
        self.model_id = inner.model_id
        self.dimensions = inner.dimensions

    def embed(self, text: str) -> Vector:
        if not self._semaphore.acquire(timeout=self._timeout_seconds):
            raise EmbeddingTimeout

        try:
            future: Future[Vector] = self._executor.submit(self._inner.embed, text)
        except Exception:
            # Fix-pass finding #1 (resilience CRITICAL): the permit was
            # already acquired above but the done-callback below never gets
            # attached if `submit()` itself raises (e.g. the executor was
            # shut down, or thread creation failed under resource
            # pressure) -- release it HERE before re-raising, or it leaks
            # permanently and cumulatively shrinks the concurrency bound.
            self._semaphore.release()
            raise
        # Released when the WORKER finishes, not when this caller times out
        # below -- a stuck forward pass keeps its slot until it actually
        # completes (see module docstring's "Honest limit").
        future.add_done_callback(lambda _future: self._semaphore.release())

        try:
            return future.result(timeout=self._timeout_seconds)
        except FutureTimeoutError as exc:
            raise EmbeddingTimeout from exc
        except (EmbeddingUnavailable, EmbeddingTimeout):
            raise
        except Exception as exc:
            raise EmbeddingUnavailable from exc

    def check_ready(self) -> None:
        self._inner.check_ready()

    def close(self) -> None:
        """Reliability suggestion #11: shuts down the owned `ThreadPool
        Executor` -- never called automatically by this class itself.
        `main.py`'s lifespan `finally` block calls this alongside `engine.
        dispose()` so the executor's threads are not left running past
        application shutdown. `cancel_futures=True` drops anything still
        queued (not yet started); `wait=False` never blocks shutdown on a
        stuck forward pass (see the module docstring's "Honest limit")."""
        self._executor.shutdown(wait=False, cancel_futures=True)
