"""`ValidatePhrase` use case (tasks.md 3.1, design.md's Data Flow /
"Reconciliation rule"). Stateless: persists nothing
(semantic-validation spec's "Statelessness" scenario).
"""

from __future__ import annotations

from app.modules.phrases.application._shared import (
    MostSimilarView,
    VerdictView,
    build_matches_page,
    normalize_and_check_length,
)
from app.modules.phrases.contracts import Isolation, UnitOfWorkFactory
from app.modules.similarity.contracts import EmbeddingProvider, SimilarityPolicy


class ValidatePhrase:
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

    def __call__(self, text: str, *, limit: int) -> VerdictView:
        _, comparison = normalize_and_check_length(text, max_length=self._phrase_max_length)
        vector = self._embedder.embed(comparison)

        # One REPEATABLE READ read-only snapshot for both reads (design.md
        # "Snapshot consistency") -- ValidatePhrase never writes and takes
        # no lock.
        with self._uow_factory(isolation=Isolation.REPEATABLE_READ, read_only=True) as uow:
            neighbor = uow.repo.find_nearest(vector)
            page = uow.repo.find_matches(
                vector, max_distance=self._policy.max_distance(), limit=limit, cursor=None
            )
        matches_page = build_matches_page(page, self._policy, comparison=comparison)

        if matches_page.matches:
            # Reconciliation rule: the exact scan is authoritative over the
            # approximate `find_nearest` whenever `matches` is non-empty.
            top = matches_page.matches[0]
            return VerdictView(
                is_duplicate=True,
                threshold=self._policy.threshold,
                score=top.score,
                most_similar=MostSimilarView(top.id, top.text, top.score),
                matches=matches_page.matches,
                next_cursor=matches_page.next_cursor,
                has_more=matches_page.has_more,
            )

        if neighbor is None:
            return VerdictView(
                is_duplicate=False,
                threshold=self._policy.threshold,
                score=None,
                most_similar=None,
                matches=[],
                next_cursor=None,
                has_more=False,
            )

        score = self._policy.score(neighbor.distance)
        return VerdictView(
            is_duplicate=False,
            threshold=self._policy.threshold,
            score=score,
            most_similar=MostSimilarView(neighbor.id, neighbor.text, score),
            matches=[],
            next_cursor=None,
            has_more=False,
        )
