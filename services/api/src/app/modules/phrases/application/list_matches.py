"""`ListMatches` use case (tasks.md 3.2, design.md's Cursor format /
"decode -> validate fields -> compare t and th -> embed -> query" order).
Serves pages 2..n of `matches`; page 1 is `ValidatePhrase`'s job.
"""

from __future__ import annotations

from app.modules.phrases.application._shared import MatchesPage, build_matches_page
from app.modules.phrases.contracts import MatchCursor, UnitOfWorkFactory
from app.modules.phrases.domain.cursor import InvalidCursor, decode_cursor, max_encoded_length
from app.modules.phrases.domain.normalization import comparison_form, display_form
from app.modules.similarity.contracts import EmbeddingProvider, SimilarityPolicy


class ListMatches:
    def __init__(
        self,
        uow_factory: UnitOfWorkFactory,
        embedder: EmbeddingProvider,
        policy: SimilarityPolicy,
        *,
        phrase_max_length: int,
    ) -> None:
        self._uow_factory = uow_factory
        self._embedder = embedder
        self._policy = policy
        self._phrase_max_length = phrase_max_length

    def __call__(self, text: str, *, cursor: str, limit: int) -> MatchesPage:
        envelope = decode_cursor(cursor, max_length=max_encoded_length(self._phrase_max_length))
        comparison = comparison_form(display_form(text))
        if envelope.t != comparison:
            raise InvalidCursor("cursor is bound to a different text")
        if envelope.th != self._policy.threshold:
            raise InvalidCursor("cursor is bound to a different threshold")

        # Only after both binding checks pass does a forward pass happen --
        # `FakeEmbedder.call_count == 0` on any rejected cursor.
        vector = self._embedder.embed(comparison)
        match_cursor = MatchCursor(distance=envelope.d, id=envelope.i)
        with self._uow_factory() as uow:  # READ COMMITTED, always live (design.md)
            page = uow.repo.find_matches(
                vector, max_distance=self._policy.max_distance(), limit=limit, cursor=match_cursor
            )
            total = uow.repo.count_matches(vector, max_distance=self._policy.max_distance())
        return build_matches_page(page, self._policy, comparison=comparison, total=total)
