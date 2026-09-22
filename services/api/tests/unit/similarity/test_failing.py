"""Unit tests for `FailingEmbedder` (tasks.md 2.2)."""

from __future__ import annotations

import pytest

from app.modules.similarity.adapters.failing import FailingEmbedder
from app.modules.similarity.adapters.fake import FakeEmbedder
from app.modules.similarity.contracts import EmbeddingTimeout, EmbeddingUnavailable


def test_permanent_mode_always_raises_and_never_delegates() -> None:
    inner = FakeEmbedder({"x": [1.0, 0.0]})
    embedder = FailingEmbedder(inner)
    with pytest.raises(EmbeddingUnavailable):
        embedder.embed("x")
    with pytest.raises(EmbeddingUnavailable):
        embedder.embed("x")
    assert inner.call_count == 0


def test_one_shot_mode_fails_once_then_delegates() -> None:
    inner = FakeEmbedder({"x": [1.0, 0.0]}, model_id="fake@rev")
    embedder = FailingEmbedder(inner, fail_times=1)
    with pytest.raises(EmbeddingUnavailable):
        embedder.embed("x")
    assert embedder.embed("x") == [1.0, 0.0]
    assert inner.call_count == 1
    assert embedder.model_id == "fake@rev"
    assert embedder.dimensions == 2


def test_custom_error_delegates_on_embed() -> None:
    inner = FakeEmbedder({"x": [1.0]})
    embedder = FailingEmbedder(inner, error=EmbeddingTimeout())
    with pytest.raises(EmbeddingTimeout):
        embedder.embed("x")


def test_check_ready_reflects_permanent_failure_mode() -> None:
    # A permanently-failing double must never report itself healthy: every
    # embed() call raises forever, so check_ready() must too.
    inner = FakeEmbedder({"x": [1.0, 0.0]})
    embedder = FailingEmbedder(inner)
    with pytest.raises(EmbeddingUnavailable):
        embedder.check_ready()
    with pytest.raises(EmbeddingUnavailable):
        embedder.embed("x")
    with pytest.raises(EmbeddingUnavailable):
        embedder.check_ready()


def test_check_ready_reflects_one_shot_failure_window_then_recovers() -> None:
    # Before the one allowed failure has been consumed, check_ready() must
    # report the same "down" state the next embed() call would hit.
    inner = FakeEmbedder({"x": [1.0, 0.0]})
    embedder = FailingEmbedder(inner, fail_times=1, error=EmbeddingTimeout())
    with pytest.raises(EmbeddingTimeout):
        embedder.check_ready()

    with pytest.raises(EmbeddingTimeout):
        embedder.embed("x")

    # The failure window is now exhausted -- embed() delegates, and
    # check_ready() must agree the double has recovered.
    embedder.check_ready()  # must not raise
    assert embedder.embed("x") == [1.0, 0.0]


@pytest.mark.parametrize("fail_times", [0])
def test_fail_times_zero_never_fails_and_delegates_immediately(fail_times: int) -> None:
    # Per this module's own docstring, `fail_times` counts how many of the
    # FIRST calls raise; `0` means zero calls raise, i.e. immediate,
    # permanent delegation to `inner` from the very first call -- distinct
    # from `fail_times=None` (permanent failure) and `fail_times=1` (one
    # failure then delegation).
    inner = FakeEmbedder({"x": [1.0, 0.0]})
    embedder = FailingEmbedder(inner, fail_times=fail_times)
    embedder.check_ready()  # must not raise -- never "down"
    assert embedder.embed("x") == [1.0, 0.0]
    assert inner.call_count == 1
    embedder.check_ready()  # still healthy after a real call
    assert embedder.embed("x") == [1.0, 0.0]
    assert inner.call_count == 2
