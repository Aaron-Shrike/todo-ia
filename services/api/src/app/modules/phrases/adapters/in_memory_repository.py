"""In-memory `PhraseRepository` + `UnitOfWork` (tasks.md 2.3). The fast
fake the pgvector adapter (Unit 5a/5b) is tested against via
`tests/contract_suite/repository_contract.py`, so it cannot drift from it.
Implements the same `find_nearest` tie-break as pgvector, using the domain
cosine (via `similarity.contracts`' re-export). In memory,
`find_nearest`/`find_nearest_exact` are the same exact computation.

`REPEATABLE_READ` freezes a snapshot at `__enter__`; `READ_COMMITTED`
re-reads the live store on every call. Writes are buffered locally and
applied to the shared store only on `commit()`; `rollback()` (or exiting
the context manager without a commit) discards them.

`find_matches`: see `phrases/contracts.py`'s module docstring (review-budget
deferral note lives there only).
"""

from __future__ import annotations

from collections.abc import Callable
from datetime import UTC, datetime
from itertools import count

from app.modules.phrases.contracts import (
    DuplicateTextConflict,
    Isolation,
    Neighbor,
    NewPhrase,
    Phrase,
    ValidationStatus,
)
from app.modules.phrases.domain.errors import PhraseMetadataInvariantViolation
from app.modules.similarity.contracts import Vector, cosine_distance


def _validate_paired_metadata(phrase: NewPhrase) -> None:
    """Enforce migration 0001's `phrases_metadata_paired` and
    `phrases_confirmed_has_neighbor` CHECK constraints in the domain, before
    any adapter writes a row -- see `PhraseMetadataInvariantViolation`."""
    paired = (phrase.similarity_score is None) == (phrase.most_similar_phrase_id is None)
    if not paired:
        raise PhraseMetadataInvariantViolation(
            "similarity_score and most_similar_phrase_id must be recorded as a pair "
            "(phrases_metadata_paired)"
        )
    if phrase.validation_status is ValidationStatus.DUPLICATE_CONFIRMED and (
        phrase.similarity_score is None or phrase.most_similar_phrase_id is None
    ):
        raise PhraseMetadataInvariantViolation(
            "a duplicate_confirmed phrase must carry both similarity_score and "
            "most_similar_phrase_id (phrases_confirmed_has_neighbor)"
        )


class _InMemoryStore:
    """Backing state for one `InMemoryUnitOfWorkFactory`; mutated only
    through `InMemoryUnitOfWork.commit()`."""

    def __init__(self) -> None:
        self._phrases: list[Phrase] = []
        self._ids = count(1)

    def snapshot(self) -> list[Phrase]:
        return list(self._phrases)

    def next_id(self) -> int:
        return next(self._ids)

    def apply(self, rows: list[Phrase]) -> None:
        self._phrases.extend(rows)


class InMemoryPhraseRepository:
    """Bound to one `InMemoryUnitOfWork`'s view: `_read_view` is the read
    snapshot, `_pending` is this transaction's uncommitted writes."""

    def __init__(
        self,
        store: _InMemoryStore,
        *,
        read_view: Callable[[], list[Phrase]],
        read_only: bool = False,
    ) -> None:
        self._store = store
        self._read_view = read_view
        self._read_only = read_only
        self._pending: list[Phrase] = []

    def _rows(self) -> list[Phrase]:
        return [*self._read_view(), *self._pending]

    def _has_pending_writes(self) -> bool:
        return bool(self._pending)

    def _drain_pending(self) -> list[Phrase]:
        """Return and clear buffered writes (owning `UnitOfWork` only)."""
        pending, self._pending = self._pending, []
        return pending

    def add(self, phrase: NewPhrase) -> Phrase:
        # Fail-fast at the statement, matching a real Postgres `READ ONLY`
        # transaction: a write is rejected here, never silently discarded
        # by an un-committed `__exit__` -> `rollback()`.
        if self._read_only:
            raise RuntimeError("cannot write inside a read-only UnitOfWork")
        _validate_paired_metadata(phrase)
        if phrase.validation_status is ValidationStatus.UNIQUE and any(
            row.normalized_text == phrase.normalized_text
            and row.validation_status is ValidationStatus.UNIQUE
            for row in self._rows()
        ):
            raise DuplicateTextConflict(phrase.normalized_text)
        row = Phrase(
            id=self._store.next_id(),
            text=phrase.text,
            normalized_text=phrase.normalized_text,
            embedding=phrase.embedding,
            similarity_score=phrase.similarity_score,
            most_similar_phrase_id=phrase.most_similar_phrase_id,
            validation_status=phrase.validation_status,
            validated_at=phrase.validated_at,
            created_at=datetime.now(UTC),
        )
        self._pending.append(row)
        return row

    def list_recent(self, limit: int) -> list[Phrase]:
        rows = sorted(self._rows(), key=lambda row: (row.created_at, row.id), reverse=True)
        return rows[:limit]

    def find_nearest(self, q: Vector) -> Neighbor | None:
        return self._nearest(q)

    def find_nearest_exact(self, q: Vector) -> Neighbor | None:
        return self._nearest(q)  # in-memory: both are exact

    def _nearest(self, q: Vector) -> Neighbor | None:
        best: Neighbor | None = None
        best_key: tuple[float, int] | None = None
        for row in self._rows():
            distance = cosine_distance(row.embedding, q)
            key = (distance, row.id)
            if best_key is None or key < best_key:
                best_key = key
                best = Neighbor(id=row.id, text=row.text, distance=distance)
        return best

    def lock_for_write(self) -> None:
        return None

    # `find_matches`: see this module's docstring.


class InMemoryUnitOfWork:
    """One transaction over an `_InMemoryStore`."""

    def __init__(self, store: _InMemoryStore, *, isolation: Isolation, read_only: bool) -> None:
        self._store = store
        self.isolation = isolation
        self.read_only = read_only
        self._done = True
        self.repo: InMemoryPhraseRepository

    def __enter__(self) -> InMemoryUnitOfWork:
        if self.isolation is Isolation.REPEATABLE_READ:
            snapshot = self._store.snapshot()

            def read_view() -> list[Phrase]:
                return snapshot
        else:
            read_view = self._store.snapshot
        self.repo = InMemoryPhraseRepository(
            self._store, read_view=read_view, read_only=self.read_only
        )
        self._done = False
        return self

    def __exit__(self, *exc: object) -> None:
        if not self._done:
            self.rollback()

    def commit(self) -> None:
        # Defense in depth: `InMemoryPhraseRepository.add` already rejects a
        # write immediately when `read_only`, so `_pending` should never be
        # non-empty here -- this guard just refuses to silently swallow the
        # case if that invariant is ever broken by a future change.
        if self.read_only and self.repo._has_pending_writes():
            raise RuntimeError("cannot write inside a read-only UnitOfWork")
        self._store.apply(self.repo._drain_pending())
        self._done = True

    def rollback(self) -> None:
        self.repo._drain_pending()
        self._done = True


class InMemoryUnitOfWorkFactory:
    """`UnitOfWorkFactory` bound to one, fresh `_InMemoryStore` -- construct
    one instance per test for isolation between tests."""

    def __init__(self) -> None:
        self._store = _InMemoryStore()

    def __call__(
        self, *, isolation: Isolation = Isolation.READ_COMMITTED, read_only: bool = False
    ) -> InMemoryUnitOfWork:
        return InMemoryUnitOfWork(self._store, isolation=isolation, read_only=read_only)
