"""`GetPhrase` use case (`GET /phrases/{id}`). A thin pass-through over
`PhraseRepository.get` inside a single read-only `UnitOfWork` — same shape
as `ListPhrases`, no embedding, no similarity policy.
"""

from __future__ import annotations

from app.modules.phrases.contracts import Phrase, UnitOfWorkFactory
from app.modules.phrases.domain.errors import PhraseNotFound


class GetPhrase:
    def __init__(self, uow_factory: UnitOfWorkFactory) -> None:
        self._uow_factory = uow_factory

    def __call__(self, phrase_id: int) -> Phrase:
        with self._uow_factory(read_only=True) as uow:  # READ COMMITTED, always live
            phrase = uow.repo.get(phrase_id)
        if phrase is None:
            raise PhraseNotFound(phrase_id=phrase_id)
        return phrase
