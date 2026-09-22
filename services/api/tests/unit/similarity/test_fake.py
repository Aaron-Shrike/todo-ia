"""Unit tests for `FakeEmbedder` (tasks.md 2.2)."""

from __future__ import annotations

import pytest

from app.modules.similarity.adapters.fake import FakeEmbedder


def test_embed_returns_the_configured_vector_and_counts_calls() -> None:
    embedder = FakeEmbedder({"comprar leche": [0.6, 0.8]})
    assert embedder.embed("comprar leche") == [0.6, 0.8]
    assert embedder.call_count == 1
    embedder.embed("comprar leche")
    assert embedder.call_count == 2


def test_tied_texts_share_the_exact_same_vector_object() -> None:
    tied = [0.1, 0.2, 0.97]
    embedder = FakeEmbedder({"a": tied, "b": tied})
    assert embedder.embed("a") is tied
    assert embedder.embed("b") is tied


def test_embed_raises_for_an_unconfigured_text() -> None:
    with pytest.raises(KeyError):
        FakeEmbedder({"known": [1.0, 0.0]}).embed("unknown")


def test_check_ready_is_a_no_op_and_metadata_is_reported() -> None:
    embedder = FakeEmbedder({"x": [1.0, 2.0, 3.0]}, model_id="fake@rev")
    embedder.check_ready()
    assert embedder.model_id == "fake@rev"
    assert embedder.dimensions == 3
