"""Composition root for `phrases` use cases (tasks.md 6b.1). Wires
`ValidatePhrase` from already-constructed ports; never decides which
concrete adapter backs `embedder`/`uow_factory` -- that stays `main.py`'s
(production) or a test's (fake) call, keeping `phrases/api/` adapter-
agnostic (import-linter's `composition-root-owns-adapters` contract).
"""

from __future__ import annotations

from dataclasses import dataclass

from app.modules.phrases.application.validate_phrase import ValidatePhrase
from app.modules.phrases.contracts import UnitOfWorkFactory
from app.modules.similarity.contracts import EmbeddingProvider, SimilarityPolicy


@dataclass(frozen=True)
class PhrasesContainer:
    """Attached to `app.state.phrases`; `router.py` reads use cases off it
    per request and never constructs one itself."""

    validate_phrase: ValidatePhrase


def build_phrases_container(
    *,
    embedder: EmbeddingProvider,
    uow_factory: UnitOfWorkFactory,
    policy: SimilarityPolicy,
    phrase_max_length: int,
) -> PhrasesContainer:
    return PhrasesContainer(
        validate_phrase=ValidatePhrase(
            uow_factory, embedder, policy, phrase_max_length=phrase_max_length
        )
    )
