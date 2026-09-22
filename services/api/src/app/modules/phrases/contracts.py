"""Published boundary of `phrases` (tasks.md 2.1, design.md's `contracts.py`).

`phrases.application`/`.api` depend on this module only, never a concrete
adapter (`import-linter`'s `composition-root-owns-adapters` contract).

Deviations from tasks.md's shorthand (design.md is authoritative for
internals, same precedent as Unit 1): methods are `add`/`list_recent`, not
`insert`/`list`; `Neighbor` is added (untyped otherwise in design's own
`find_nearest` signature).

**Review-budget split** (tasks.md's Unit 2 escape hatch, single source of
truth for this note -- other files in this unit point back here instead of
repeating it): `find_matches`, `Match`, `Page` and `MatchCursor` are
deferred to an immediate follow-up PR (Unit 2d) -- see apply-progress.md.
`find_nearest`/`find_nearest_exact` (this PR's scope) do not need them.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from enum import Enum
from typing import Protocol

from app.modules.similarity.contracts import Vector

__all__ = [
    "DuplicateTextConflict",
    "Isolation",
    "Neighbor",
    "NewPhrase",
    "Phrase",
    "PhraseRepository",
    "UnitOfWork",
    "UnitOfWorkFactory",
    "ValidationStatus",
]


class ValidationStatus(Enum):
    """Mirrors the `validation_status` CHECK constraint (migration 0001, the
    Alembic revision that creates the `phrases` table -- see design.md's
    "Data Model and Migrations")."""

    UNIQUE = "unique"
    DUPLICATE_CONFIRMED = "duplicate_confirmed"


class Isolation(Enum):
    """`SavePhrase` -> READ_COMMITTED; `ValidatePhrase` -> REPEATABLE_READ."""

    READ_COMMITTED = "READ COMMITTED"
    REPEATABLE_READ = "REPEATABLE READ"


@dataclass(frozen=True)
class NewPhrase:
    """What `PhraseRepository.add` writes. Score/neighbour are always a
    PAIR (`phrases_metadata_paired` -- the migration-0001 CHECK constraint
    requiring `similarity_score IS NULL` iff `most_similar_phrase_id IS
    NULL`; enforced in code by `PhraseMetadataInvariantViolation`); both
    `None` only on an empty store."""

    text: str
    normalized_text: str
    embedding: Vector
    similarity_score: float | None
    most_similar_phrase_id: int | None
    validation_status: ValidationStatus
    validated_at: datetime


@dataclass(frozen=True)
class Phrase:
    """A stored phrase row, as `add`/`list_recent` return it."""

    id: int
    text: str
    normalized_text: str
    embedding: Vector
    similarity_score: float | None
    most_similar_phrase_id: int | None
    validation_status: ValidationStatus
    validated_at: datetime
    created_at: datetime


@dataclass(frozen=True)
class Neighbor:
    """`find_nearest`/`find_nearest_exact` result: RAW distance."""

    id: int
    text: str
    distance: float


class DuplicateTextConflict(Exception):
    """`add` unique-violation on `normalized_text` among `unique` rows
    (ADR-006, the technical decision record adopting the partial unique
    index `phrases_unique_normalized_text_uidx` for exact-duplicate
    integrity). `SavePhrase` (Unit 3) retries once, in a fresh
    transaction."""


class UnitOfWork(Protocol):
    """One transaction; lets the application say BEGIN/ROLLBACK/retry
    without importing a concrete adapter."""

    repo: PhraseRepository

    def __enter__(self) -> UnitOfWork: ...

    def __exit__(self, *exc: object) -> None: ...

    def commit(self) -> None: ...

    def rollback(self) -> None: ...


class UnitOfWorkFactory(Protocol):
    def __call__(
        self, *, isolation: Isolation = Isolation.READ_COMMITTED, read_only: bool = False
    ) -> UnitOfWork: ...


class PhraseRepository(Protocol):
    """Always bound to ONE `UnitOfWork`'s transaction."""

    def add(self, phrase: NewPhrase) -> Phrase: ...

    def list_recent(self, limit: int) -> list[Phrase]: ...  # newest first, no cursor

    def find_nearest(self, q: Vector) -> Neighbor | None:
        """Unfiltered top-1, `(distance asc, id asc)`. `None` only if
        empty. Validate endpoint only -- MUST NOT be called by `SavePhrase`
        (approximate in pgvector; see `find_nearest_exact`)."""
        ...

    def find_nearest_exact(self, q: Vector) -> Neighbor | None:
        """Same contract, EXACT scan. `SavePhrase` only, under the lock."""
        ...

    def lock_for_write(self) -> None: ...  # advisory lock in pgvector; no-op in-memory

    # `find_matches` (EXACT scan, `(bucket, id)` keyset pagination) is
    # deferred to an immediate follow-up PR -- see this module's docstring.
