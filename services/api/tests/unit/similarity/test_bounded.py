"""Unit tests for `BoundedEmbeddingProvider` (tasks.md 8.1, design.md
"Embedding timeout and concurrency bound"). A controllable slow fake blocks
on a `threading.Event` -- no `time.sleep` anywhere -- so every scenario is
deterministic: acquiring the concurrency slot within `EMBEDDING_TIMEOUT_
SECONDS` fails fast with `EmbeddingTimeout`, a still-held slot rejects the
next call without ever reaching the inner provider, releasing the event
frees the slot for a later call, and a timed-out attempt is never cached
by the (separately tested) `CachingEmbeddingProvider` wrapped around it.
"""

from __future__ import annotations

import threading
from collections.abc import Iterator
from concurrent.futures import ThreadPoolExecutor

import pytest

from app.modules.similarity.adapters.bounded import BoundedEmbeddingProvider
from app.modules.similarity.adapters.caching import CachingEmbeddingProvider
from app.modules.similarity.adapters.failing import FailingEmbedder
from app.modules.similarity.adapters.fake import FakeEmbedder
from app.modules.similarity.contracts import EmbeddingTimeout, EmbeddingUnavailable, Vector

_FAST_TIMEOUT = 0.2  # generous enough for a done-callback to run, still fast for a test


class _BlockingEmbedder:
    """Blocks `embed()` on a `threading.Event` until released -- simulates a
    stuck model forward pass without sleeping."""

    def __init__(self, vector: Vector, *, release: threading.Event) -> None:
        self.model_id = "blocking@0000000000000000000000000000000000000000"
        self.dimensions = len(vector)
        self._vector = vector
        self._release = release
        self.call_count = 0

    def embed(self, text: str) -> Vector:
        self.call_count += 1
        self._release.wait()
        return self._vector

    def check_ready(self) -> None:
        return None


@pytest.fixture
def release() -> Iterator[threading.Event]:
    event = threading.Event()
    yield event
    # Always unblock any lingering worker thread, even on assertion failure,
    # so a stuck `embed()` call never hangs the test process at exit.
    event.set()


def test_embed_times_out_when_no_slot_is_free_within_the_timeout(
    release: threading.Event,
) -> None:
    inner = _BlockingEmbedder([1.0, 0.0], release=release)
    provider = BoundedEmbeddingProvider(inner, timeout_seconds=0.05, max_concurrency=1)

    with pytest.raises(EmbeddingTimeout):
        provider.embed("hola")


def test_a_held_slot_rejects_the_next_call_without_reaching_the_inner_provider(
    release: threading.Event,
) -> None:
    inner = _BlockingEmbedder([1.0, 0.0], release=release)
    provider = BoundedEmbeddingProvider(inner, timeout_seconds=0.05, max_concurrency=1)

    with pytest.raises(EmbeddingTimeout):
        provider.embed("first")  # occupies the only slot; still running
    with pytest.raises(EmbeddingTimeout):
        provider.embed("second")  # slot still held -> fails fast

    # "second" never reached the inner provider -- no extra work was queued.
    assert inner.call_count == 1


def test_releasing_the_event_frees_the_slot_for_a_later_call(
    release: threading.Event,
) -> None:
    inner = _BlockingEmbedder([0.6, 0.8], release=release)
    provider = BoundedEmbeddingProvider(inner, timeout_seconds=_FAST_TIMEOUT, max_concurrency=1)

    with pytest.raises(EmbeddingTimeout):
        provider.embed("first")

    release.set()

    assert provider.embed("second") == [0.6, 0.8]
    assert inner.call_count == 2


def test_a_timed_out_result_is_never_cached(release: threading.Event) -> None:
    inner = _BlockingEmbedder([0.6, 0.8], release=release)
    bounded = BoundedEmbeddingProvider(inner, timeout_seconds=_FAST_TIMEOUT, max_concurrency=1)
    cache = CachingEmbeddingProvider(bounded, capacity=10)

    with pytest.raises(EmbeddingTimeout):
        cache.embed("hola")
    assert cache.stats.size == 0  # the timed-out attempt inserted nothing

    release.set()

    assert cache.embed("hola") == [0.6, 0.8]
    assert cache.stats.size == 1


def test_a_raw_inner_exception_becomes_embedding_unavailable() -> None:
    class _BrokenEmbedder:
        model_id = "broken@0000000000000000000000000000000000000000"
        dimensions = 2

        def embed(self, text: str) -> Vector:
            raise RuntimeError("torch blew up")

        def check_ready(self) -> None:
            return None

    provider = BoundedEmbeddingProvider(_BrokenEmbedder(), timeout_seconds=1.0, max_concurrency=1)

    with pytest.raises(EmbeddingUnavailable):
        provider.embed("x")


def test_an_inner_embedding_unavailable_propagates_unchanged() -> None:
    failing = FailingEmbedder(FakeEmbedder({"x": [1.0, 0.0]}), fail_times=None)
    provider = BoundedEmbeddingProvider(failing, timeout_seconds=1.0, max_concurrency=1)

    with pytest.raises(EmbeddingUnavailable):
        provider.embed("x")


def test_model_id_and_dimensions_are_forwarded_from_the_inner_provider() -> None:
    inner = FakeEmbedder({"a": [1.0, 0.0, 0.0]}, model_id="fake@rev")
    provider = BoundedEmbeddingProvider(inner, timeout_seconds=1.0, max_concurrency=1)

    assert provider.model_id == "fake@rev"
    assert provider.dimensions == 3
    assert provider.embed("a") == [1.0, 0.0, 0.0]


def test_check_ready_delegates_to_the_inner_provider() -> None:
    failing = FailingEmbedder(FakeEmbedder({"a": [1.0]}), fail_times=None)
    provider = BoundedEmbeddingProvider(failing, timeout_seconds=1.0, max_concurrency=1)

    with pytest.raises(EmbeddingUnavailable):
        provider.check_ready()


def test_a_submit_failure_does_not_leak_the_semaphore_permit() -> None:
    # Fix-pass finding #1 (resilience CRITICAL): the semaphore was only
    # released via `future.add_done_callback`, attached AFTER `executor.
    # submit()` succeeded -- if `submit()` itself raises (e.g. the executor
    # was already shut down), the already-acquired permit used to leak
    # permanently. Shutting down a REAL `ThreadPoolExecutor` before calling
    # `embed()` is the design-suggested, deterministic way to make
    # `submit()` raise without mocking.
    inner = FakeEmbedder({"a": [1.0, 0.0]})
    provider = BoundedEmbeddingProvider(inner, timeout_seconds=1.0, max_concurrency=1)
    provider._executor.shutdown(wait=True)  # submit() now raises RuntimeError

    with pytest.raises(RuntimeError):
        provider.embed("a")

    # The permit must have been released despite `submit()` raising above --
    # proved BEHAVIOURALLY: swap in a working executor and confirm a later
    # `embed()` call can still acquire the (otherwise still-held) slot,
    # exactly as the design's "later requests fail fast" contract promises
    # for a HELD slot -- this call must NOT fail fast.
    provider._executor = ThreadPoolExecutor(max_workers=1)
    assert provider.embed("a") == [1.0, 0.0]


def test_close_shuts_down_the_executor_so_a_later_embed_call_is_rejected() -> None:
    # Reliability suggestion #11: `BoundedEmbeddingProvider` never exposed a
    # way to shut down its `ThreadPoolExecutor` -- `close()` does, and
    # `main.py`'s lifespan `finally` block calls it alongside `engine.
    # dispose()`.
    inner = FakeEmbedder({"a": [1.0, 0.0]})
    provider = BoundedEmbeddingProvider(inner, timeout_seconds=1.0, max_concurrency=1)

    provider.close()

    with pytest.raises(RuntimeError):
        provider.embed("a")
