"""`sentence-transformers` `EmbeddingProvider` adapter (tasks.md 8.2,
design.md ADR-003 / D6: "sentence-transformers now, ONNX/fastembed later").

`SentenceTransformersEmbedder` takes an ALREADY-LOADED model object
(duck-typed per `_EncodeModel`) and never imports the `sentence_transformers`
package itself -- so unit tests exercise the real adapter logic (`model_id`
assembly, `dimensions`, the `normalize_embeddings=True` contract) against a
stubbed model with no `sentence_transformers`/`torch` install required.
`load_sentence_transformer` below is the ONLY place that imports the real
library -- lazily, inside the function body -- and only `main.py`'s
production lifespan calls it; no test in this codebase does.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Protocol

from app.modules.similarity.container import build_model_id
from app.modules.similarity.contracts import Vector

if TYPE_CHECKING:
    from app.platform.settings import Settings


class _EncodeModel(Protocol):
    """Duck-typed subset of `sentence_transformers.SentenceTransformer`
    this adapter actually calls."""

    def encode(self, text: str, *, normalize_embeddings: bool) -> object: ...

    def get_sentence_embedding_dimension(self) -> int: ...


class SentenceTransformersEmbedder:
    """`EmbeddingProvider` over an already-loaded model. `model_id` is
    `"<model_name>@<revision>"` (design.md D10's cache-key format);
    `dimensions` is read once from the model at construction."""

    def __init__(self, model: _EncodeModel, *, model_name: str, revision: str) -> None:
        self._model = model
        # `build_model_id` (`similarity/container.py`, D10) is the one
        # source of truth for the `model@revision` format -- fix-pass
        # finding #7: this used to duplicate the same f-string inline.
        self.model_id = build_model_id(model=model_name, revision=revision)
        self.dimensions = model.get_sentence_embedding_dimension()

    def embed(self, text: str) -> Vector:
        """PRE: `text` already normalized (comparison form -- see
        `similarity.contracts.EmbeddingProvider`). POST: L2-normalized (the
        library's own `normalize_embeddings=True` flag does this -- no
        extra normalization pass needed here), `len == self.dimensions`."""
        vector = self._model.encode(text, normalize_embeddings=True)
        return [float(component) for component in vector]  # type: ignore[attr-defined]

    def check_ready(self) -> None:
        # The model loaded synchronously at construction (see
        # `load_sentence_transformer` below); if this object exists at all,
        # it already loaded successfully. Nothing left to check.
        return None


def load_sentence_transformer(settings: Settings) -> SentenceTransformersEmbedder:
    """Production factory: the ONLY place in this module tree that imports
    `sentence_transformers` (lazy, inside this function body) -- keeps
    every unit test import-safe with neither the package nor its `torch`
    dependency installed. Called once, from `main.py`'s lifespan startup
    hook; never from a test (the `slow`-marked real-model test in
    `test_sentence_transformers.py` is the one exception, and it is not
    executed in this environment -- see that file's module docstring)."""
    from sentence_transformers import SentenceTransformer

    model = SentenceTransformer(
        settings.embedding_model, revision=settings.embedding_model_revision
    )
    return SentenceTransformersEmbedder(
        model, model_name=settings.embedding_model, revision=settings.embedding_model_revision
    )
