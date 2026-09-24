"""`ListPhrases` use case (`GET /phrases`, keyset-paginated newest first —
see `contracts.py`'s `PhraseListPage`). A thin pass-through over
`PhraseRepository.list_page` inside a single read-only `UnitOfWork` — no
embedding, no similarity policy, unlike every other use case in this module.
"""

from __future__ import annotations

from dataclasses import dataclass

from app.modules.phrases.contracts import ListCursor, Phrase, UnitOfWorkFactory
from app.modules.phrases.domain.list_cursor import decode_list_cursor, encode_list_cursor


@dataclass(frozen=True)
class PhraseListView:
    """Application-layer result: the repository's `ListCursor` is already
    encoded to an opaque string here, same pattern as `_shared.py`'s
    `MatchesPage` — `phrases.api` never imports a cursor codec directly."""

    items: list[Phrase]
    total: int
    next_cursor: str | None
    has_more: bool


class ListPhrases:
    def __init__(self, uow_factory: UnitOfWorkFactory) -> None:
        self._uow_factory = uow_factory

    def __call__(self, *, limit: int, cursor: str | None) -> PhraseListView:
        list_cursor: ListCursor | None = None
        if cursor is not None:
            envelope = decode_list_cursor(cursor)  # raises InvalidListCursor on any violation
            list_cursor = ListCursor(created_at=envelope.created_at, id=envelope.id)

        with self._uow_factory(read_only=True) as uow:  # READ COMMITTED, always live
            page = uow.repo.list_page(limit, list_cursor)

        next_cursor = (
            encode_list_cursor(created_at=page.next_cursor.created_at, id=page.next_cursor.id)
            if page.next_cursor is not None
            else None
        )
        return PhraseListView(
            items=page.items, total=page.total, next_cursor=next_cursor, has_more=page.has_more
        )
