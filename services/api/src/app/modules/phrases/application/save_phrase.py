"""`SavePhrase` use case (tasks.md 3.3, design.md's Concurrency section).
Server-side re-validation on every save: the verdict and the recorded
metadata come from `find_nearest_exact` (never the approximate
`find_nearest`), taken under the advisory lock inside a `READ COMMITTED`
transaction opened AFTER embedding (design.md: "so a slow model never
holds the write lock").
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime

from app.modules.phrases.application._shared import (
    MostSimilarView,
    VerdictView,
    build_matches_page,
    normalize_and_check_length,
)
from app.modules.phrases.contracts import (
    DuplicateTextConflict,
    Neighbor,
    NewPhrase,
    Phrase,
    UnitOfWork,
    UnitOfWorkFactory,
    ValidationStatus,
)
from app.modules.similarity.contracts import EmbeddingProvider, SimilarityPolicy, Vector

_MAX_ATTEMPTS = 2  # one bounded retry (ADR-006): the original check-and-insert, then a fresh one.


@dataclass(frozen=True)
class SaveResult:
    """Exactly one of the two is set."""

    phrase: Phrase | None
    conflict: VerdictView | None


class SavePhrase:
    def __init__(
        self,
        uow_factory: UnitOfWorkFactory,
        embedder: EmbeddingProvider,
        policy: SimilarityPolicy,
        *,
        phrase_max_length: int,
        default_page_size: int,
    ) -> None:
        self._uow_factory = uow_factory
        self._embedder = embedder
        self._policy = policy
        self._phrase_max_length = phrase_max_length
        self._default_page_size = default_page_size

    def __call__(self, text: str, *, confirm_duplicate: bool = False) -> SaveResult:
        display, comparison = normalize_and_check_length(text, max_length=self._phrase_max_length)
        vector = self._embedder.embed(comparison)  # BEFORE any transaction/lock
        return self._attempt(display, comparison, vector, confirm_duplicate, attempt=1)

    def _attempt(
        self,
        display: str,
        comparison: str,
        vector: Vector,
        confirm_duplicate: bool,
        *,
        attempt: int,
    ) -> SaveResult:
        with self._uow_factory() as uow:  # READ COMMITTED (design.md D17)
            uow.repo.lock_for_write()
            neighbor = uow.repo.find_nearest_exact(vector)  # exact scan; NEVER find_nearest
            score: float | None = None
            is_duplicate = False
            if neighbor is not None:
                score = self._policy.score(neighbor.distance)
                is_duplicate = self._policy.is_duplicate(score)

            if is_duplicate and not confirm_duplicate:
                conflict = self._conflict(uow, vector, comparison, neighbor, score)
                uow.rollback()
                return SaveResult(phrase=None, conflict=conflict)

            status = (
                ValidationStatus.DUPLICATE_CONFIRMED if is_duplicate else ValidationStatus.UNIQUE
            )
            new_phrase = NewPhrase(
                text=display,
                normalized_text=comparison,
                embedding=vector,
                similarity_score=score,
                most_similar_phrase_id=neighbor.id if neighbor is not None else None,
                validation_status=status,
                validated_at=datetime.now(UTC),
            )
            try:
                saved = uow.repo.add(new_phrase)
            except DuplicateTextConflict:
                uow.rollback()
                if attempt < _MAX_ATTEMPTS:
                    return self._attempt(
                        display, comparison, vector, confirm_duplicate, attempt=attempt + 1
                    )
                return self._forced_conflict(vector, comparison)
            uow.commit()
            return SaveResult(phrase=saved, conflict=None)

    def _forced_conflict(self, vector: Vector, comparison: str) -> SaveResult:
        """design.md: "not expected, no delete path exists" -- the retry
        itself raised again. Never attempt `add()` a third time; surface a
        409 built from one more fresh, read-only snapshot instead."""
        with self._uow_factory(read_only=True) as uow:
            neighbor = uow.repo.find_nearest_exact(vector)
            score = self._policy.score(neighbor.distance) if neighbor is not None else None
            conflict = self._conflict(uow, vector, comparison, neighbor, score)
        return SaveResult(phrase=None, conflict=conflict)

    def _conflict(
        self,
        uow: UnitOfWork,
        vector: Vector,
        comparison: str,
        neighbor: Neighbor | None,
        score: float | None,
    ) -> VerdictView:
        page = uow.repo.find_matches(
            vector,
            max_distance=self._policy.max_distance(),
            limit=self._default_page_size,
            cursor=None,
        )
        total = uow.repo.count_matches(vector, max_distance=self._policy.max_distance())
        matches_page = build_matches_page(page, self._policy, comparison=comparison, total=total)
        most_similar: MostSimilarView | None
        top_score: float | None
        if matches_page.matches:
            top = matches_page.matches[0]
            most_similar, top_score = MostSimilarView(top.id, top.text, top.score), top.score
        elif neighbor is not None and score is not None:
            most_similar, top_score = MostSimilarView(neighbor.id, neighbor.text, score), score
        else:
            most_similar, top_score = None, None
        return VerdictView(
            is_duplicate=True,
            threshold=self._policy.threshold,
            score=top_score,
            most_similar=most_similar,
            matches=matches_page.matches,
            next_cursor=matches_page.next_cursor,
            has_more=matches_page.has_more,
            total=matches_page.total,
        )
