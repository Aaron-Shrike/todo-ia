"""Composition root for `phrases` use cases (tasks.md 6b.1, extended 7.1
with `list_matches`/`save_phrase`, extended 7b.1 with `list_phrases`).
Wires each use case from already-constructed ports; never decides which
concrete adapter backs `embedder`/`uow_factory` -- that stays `main.py`'s
(production) or a test's (fake) call, keeping `phrases/api/`
adapter-agnostic (import-linter's `composition-root-owns-adapters`
contract).
"""

from __future__ import annotations

from dataclasses import dataclass

from app.modules.phrases.application.get_phrase import GetPhrase
from app.modules.phrases.application.list_matches import ListMatches
from app.modules.phrases.application.list_phrases import ListPhrases
from app.modules.phrases.application.save_phrase import SavePhrase
from app.modules.phrases.application.validate_phrase import ValidatePhrase
from app.modules.phrases.contracts import UnitOfWorkFactory
from app.modules.similarity.contracts import EmbeddingProvider, SimilarityPolicy


@dataclass(frozen=True)
class PhrasesContainer:
    """Attached to `app.state.phrases`; `router.py` reads use cases off it
    per request and never constructs one itself."""

    validate_phrase: ValidatePhrase
    list_matches: ListMatches
    save_phrase: SavePhrase
    list_phrases: ListPhrases
    get_phrase: GetPhrase


def build_phrases_container(
    *,
    embedder: EmbeddingProvider,
    uow_factory: UnitOfWorkFactory,
    policy: SimilarityPolicy,
    phrase_max_length: int,
    matches_page_size: int,
) -> PhrasesContainer:
    return PhrasesContainer(
        validate_phrase=ValidatePhrase(
            uow_factory, embedder, policy, phrase_max_length=phrase_max_length
        ),
        list_matches=ListMatches(
            uow_factory, embedder, policy, phrase_max_length=phrase_max_length
        ),
        save_phrase=SavePhrase(
            uow_factory,
            embedder,
            policy,
            phrase_max_length=phrase_max_length,
            default_page_size=matches_page_size,
        ),
        list_phrases=ListPhrases(uow_factory),
        get_phrase=GetPhrase(uow_factory),
    )
