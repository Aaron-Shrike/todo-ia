"""Unit tests for `SentenceTransformersEmbedder` (tasks.md 8.2, design.md
ADR-003 / D6). The adapter never imports the `sentence_transformers`
package itself -- only `load_sentence_transformer`'s production factory
does, lazily -- so every test here injects a STUBBED model object (duck-
typed per `_encode`/`get_sentence_embedding_dimension`) and needs neither
`sentence_transformers` nor `torch` installed.

The real-model integration test (`slow` marker, design.md's "marker slow
for the real-model test") is intentionally NOT executed in this
environment: no `sentence-transformers`/`torch` install and no network
budget for a multi-hundred-MB model download are available here (see
apply-progress.md's Unit 8 section) -- it is written for a future
docker/network-capable session to run and is excluded by `make test-unit`
via its marker, same as every other `slow` test in this suite.
"""

from __future__ import annotations

import pytest

from app.modules.similarity.adapters.sentence_transformers import (
    SentenceTransformersEmbedder,
    load_sentence_transformer,
)
from app.platform.settings import Settings


class _StubModel:
    """Duck-typed stand-in for `sentence_transformers.SentenceTransformer`:
    only the two members the adapter actually calls."""

    def __init__(self, dimension: int, vectors: dict[str, list[float]]) -> None:
        self._dimension = dimension
        self._vectors = vectors
        self.encode_calls: list[tuple[str, bool]] = []

    def encode(self, text: str, *, normalize_embeddings: bool) -> list[float]:
        self.encode_calls.append((text, normalize_embeddings))
        return self._vectors[text]

    def get_sentence_embedding_dimension(self) -> int:
        return self._dimension


def test_model_id_is_the_model_name_and_revision_joined_by_at() -> None:
    model = _StubModel(3, {"hola": [0.1, 0.2, 0.3]})
    embedder = SentenceTransformersEmbedder(
        model, model_name="org/checkpoint", revision="a" * 40
    )

    assert embedder.model_id == "org/checkpoint@" + "a" * 40


def test_dimensions_is_read_from_the_model_at_construction() -> None:
    model = _StubModel(384, {})
    embedder = SentenceTransformersEmbedder(model, model_name="m", revision="0" * 40)

    assert embedder.dimensions == 384


def test_embed_delegates_to_the_model_with_normalize_embeddings_true() -> None:
    model = _StubModel(2, {"comprar leche": [0.6, 0.8]})
    embedder = SentenceTransformersEmbedder(model, model_name="m", revision="0" * 40)

    result = embedder.embed("comprar leche")

    assert result == [0.6, 0.8]
    assert model.encode_calls == [("comprar leche", True)]


def test_embed_returns_a_plain_list_of_floats_for_a_second_distinct_text() -> None:
    # Triangulation: a different text -> a different vector, proving `embed`
    # is not hardcoded to the first test's fixture.
    model = _StubModel(3, {"a": [1.0, 0.0, 0.0], "b": [0.0, 1.0, 0.0]})
    embedder = SentenceTransformersEmbedder(model, model_name="m", revision="0" * 40)

    assert embedder.embed("a") == [1.0, 0.0, 0.0]
    assert embedder.embed("b") == [0.0, 1.0, 0.0]
    assert [call[0] for call in model.encode_calls] == ["a", "b"]


def test_check_ready_is_a_no_op_that_never_calls_the_model() -> None:
    model = _StubModel(2, {"x": [1.0, 0.0]})
    embedder = SentenceTransformersEmbedder(model, model_name="m", revision="0" * 40)

    embedder.check_ready()

    assert model.encode_calls == []


@pytest.mark.slow
def test_the_real_model_loads_and_reports_384_dimensions() -> None:
    """NOT executed in this environment -- see module docstring."""
    # Fix-pass finding #8: this SHA is cross-referenced (not re-derived
    # from) `services/api/Dockerfile`'s `ARG EMBEDDING_MODEL_REVISION`
    # default -- both must be updated together on a checkpoint bump; a
    # Dockerfile ARG cannot literally `import` a Python constant, so this
    # comment pair is the documented single source of truth.
    settings = Settings(
        database_url="postgresql+psycopg://test:test@localhost:5432/test",
        embedding_model_revision="e8f8c211226b894fcb81acc59f3b34ba3efd5f42",
    )

    embedder = load_sentence_transformer(settings)

    assert embedder.dimensions == 384
    assert embedder.model_id == f"{settings.embedding_model}@{settings.embedding_model_revision}"
