"""Published boundary of `phrases` (tasks.md 2.1/2d.1, design.md's
`contracts.py`).

`phrases.application`/`.api` depend on this module only, never a concrete
adapter (`import-linter`'s `composition-root-owns-adapters` contract).

Deviations from tasks.md's shorthand (design.md is authoritative for
internals, same precedent as Unit 1): methods are `add`/`list_recent`, not
`insert`/`list`; `Neighbor` is added (untyped otherwise in design's own
`find_nearest` signature).

**`MatchCursor` scope note** (design.md's code sample types `find_matches`'
`cursor` parameter but does not give the class body -- this is the Unit 2d
apply-time decision): the wire cursor's `t`/`th` fields (design.md's
"Cursor format": comparison form and threshold binding) are validated by
the cursor CODEC and the calling use case (Unit 2c/3, not yet built)
*before* a repository call is ever made -- design.md's own `ListMatches`
step order is "decode -> validate fields -> compare t and th -> embed ->
query". `find_matches`'s keyset math (D16) only ever needs the last
delivered row's raw distance and id, so this repository-facing
`MatchCursor` carries only `distance`/`id`. Unit 2c's codec and Unit 3's
use cases are expected to decode the full `{v,t,d,i,th}` envelope
themselves and construct this narrower type only after the `t`/`th`
binding checks pass.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from enum import Enum
from typing import Generic, Protocol, TypeVar

from app.modules.similarity.contracts import Vector

__all__ = [
    "DuplicateTextConflict",
    "Isolation",
    "ListCursor",
    "ListFilters",
    "LockTimeout",
    "Match",
    "MatchCursor",
    "NO_FILTERS",
    "Neighbor",
    "NewPhrase",
    "Page",
    "Phrase",
    "PhraseListPage",
    "PhraseRepository",
    "UnitOfWork",
    "UnitOfWorkFactory",
    "ValidationStatus",
]

_T = TypeVar("_T")


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


@dataclass(frozen=True)
class Match:
    """One row of `find_matches`: RAW distance -- the application clamps,
    rounds (`SimilarityPolicy.score`), applies `includes` and the tail rule
    (design.md's "Match query and keyset pagination"). The repository does
    NOT round or apply the threshold's exact boundary; it only filters on
    the widened `max_distance` bound the caller supplies."""

    id: int
    text: str
    distance: float


@dataclass(frozen=True)
class MatchCursor:
    """Keyset position `find_matches` continues from -- design.md's D16
    `(bucket, id)` ordering, `bucket = floor(distance / KEY_EPSILON)`. See
    this module's docstring for why `t`/`th` (the wire cursor's text/
    threshold binding fields) are NOT part of this type."""

    distance: float
    id: int


@dataclass(frozen=True)
class Page(Generic[_T]):
    """One page of `find_matches`: `items` in `(bucket, id)` order,
    `next_cursor` set iff `has_more` and `items` is non-empty (design.md's
    `LIMIT limit + 1` has-more probe). Assumes `limit >= 1`, enforced by the
    API schema layer (design.md) before any repository call reaches here."""

    items: list[_T]
    next_cursor: MatchCursor | None
    has_more: bool


@dataclass(frozen=True)
class ListCursor:
    """Keyset position `list_page` continues from — `(created_at, id)` DESC,
    the same ordering `phrases_created_at_id_idx` already serves. Distinct
    from `MatchCursor`: unrelated resource, no text/threshold binding."""

    created_at: datetime
    id: int


@dataclass(frozen=True)
class PhraseListPage:
    """One page of `list_page` (newest first). `total` is the row count of
    the ACTIVE filter set (`NO_FILTERS` when unfiltered, the full row
    count) — what the UI's "10/60" counter reads — recomputed on every
    call rather than cached, since it changes as phrases are saved."""

    items: list[Phrase]
    total: int
    next_cursor: ListCursor | None
    has_more: bool


@dataclass(frozen=True)
class ListFilters:
    """Optional narrowing for `list_page`/`count_filtered` (design.md D1):
    `GET /phrases`'s `status`/`q`/`min_score` query params, combined with
    AND semantics. `text` is already in COMPARISON form (`comparison_form`
    applied by the application layer, D2) — adapters MUST NOT re-normalize
    it. `min_score` compares with `>=`; a NULL `similarity_score` is
    excluded, matching SQL three-valued NULL semantics (`NULL >= x` is
    UNKNOWN)."""

    status: ValidationStatus | None = None
    text: str | None = None
    min_score: float | None = None


# Module-level constant, not `ListFilters()` inline at each call site --
# avoids ruff B008 (mutable-looking default in a function signature) even
# though this dataclass is frozen; also the single shared "no filter"
# value every existing call site's default keeps working with.
NO_FILTERS = ListFilters()


class DuplicateTextConflict(Exception):
    """`add` unique-violation on `normalized_text` among `unique` rows
    (ADR-006, the technical decision record adopting the partial unique
    index `phrases_unique_normalized_text_uidx` for exact-duplicate
    integrity). `SavePhrase` (Unit 3) retries once, in a fresh
    transaction."""


class LockTimeout(Exception):
    """`lock_for_write` waited longer than `LOCK_TIMEOUT_MS` (SQLSTATE
    `55P03`). pgvector only -- in-memory's `lock_for_write` is a no-op.
    Propagates through `SavePhrase` unchanged, rolled back on unwind; Unit
    6/7 maps it to `500 INTERNAL_ERROR`."""


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

    def list_page(
        self, limit: int, cursor: ListCursor | None, *, filters: ListFilters = NO_FILTERS
    ) -> PhraseListPage:
        """Newest-first, keyset-paginated (`(created_at, id)` DESC) —
        `GET /phrases`'s real pagination, used alongside `total`'s own
        `count_filtered`. `limit + 1` rows are considered internally to
        decide `has_more`, same convention as `find_matches`. `filters`
        narrows the rows considered, combined with AND semantics;
        `NO_FILTERS` (the default) matches every row, same as before
        filters existed -- every pre-existing call site stays valid."""
        ...

    def count_filtered(self, filters: ListFilters) -> int:
        """Row count of the ACTIVE filter set, independent of any page —
        what `list_page`'s `total` field reports. `count_all()` is
        `count_filtered(NO_FILTERS)`."""
        ...

    def count_all(self) -> int:
        """Total stored phrase count, independent of any page —
        `count_filtered(NO_FILTERS)`."""
        ...

    def find_nearest(self, q: Vector) -> Neighbor | None:
        """Unfiltered top-1, `(distance asc, id asc)`. `None` only if
        empty. Validate endpoint only -- MUST NOT be called by `SavePhrase`
        (approximate in pgvector; see `find_nearest_exact`)."""
        ...

    def find_nearest_exact(self, q: Vector) -> Neighbor | None:
        """Same contract, EXACT scan. `SavePhrase` only, under the lock."""
        ...

    def lock_for_write(self) -> None:
        """`pg_advisory_xact_lock` under a bounded `SET LOCAL lock_timeout`
        in pgvector; no-op in-memory. Raises `LockTimeout` if the wait
        exceeds the configured timeout."""
        ...

    def find_matches(
        self, q: Vector, max_distance: float, limit: int, cursor: MatchCursor | None
    ) -> Page[Match]:
        """EXACT scan. Threshold-filtered (widened bound) + keyset on
        `(bucket, id)` (D16). Returns RAW distances; the application
        clamps/rounds, applies `includes`, and applies the tail rule.
        `limit + 1` rows are considered internally to decide `has_more`."""
        ...

    def count_matches(self, q: Vector, max_distance: float) -> int:
        """Total count of stored phrases within `max_distance` (the SAME
        widened bound `find_matches` filters on) — what the UI's
        "10/46 coincidencias" counter reads. EXACT scan, same as
        `find_matches`; counted independently of any page/cursor."""
        ...
