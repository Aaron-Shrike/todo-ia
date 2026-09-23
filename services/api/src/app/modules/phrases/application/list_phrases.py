"""`ListPhrases` use case (tasks.md 7b.1, design.md's "Request shapes":
`GET /phrases` -- no parameters, not paginated, hard-capped at
`PHRASES_LIST_LIMIT`). A thin pass-through over `PhraseRepository.
list_recent` inside a single read-only `UnitOfWork` -- no embedding, no
similarity policy, unlike every other use case in this module.
"""

from __future__ import annotations

from app.modules.phrases.contracts import Phrase, UnitOfWorkFactory


class ListPhrases:
    def __init__(self, uow_factory: UnitOfWorkFactory, *, limit: int) -> None:
        self._uow_factory = uow_factory
        self._limit = limit

    def __call__(self) -> list[Phrase]:
        with self._uow_factory(read_only=True) as uow:  # READ COMMITTED, always live
            return uow.repo.list_recent(self._limit)
