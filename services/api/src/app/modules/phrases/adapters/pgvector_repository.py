"""pgvector `PhraseRepository`/`UnitOfWork` (tasks.md 5a.1-5a.3, 5b.0-5b.2).

`find_matches` (5a): exact scan (`enable_indexscan=off`), WIDENED
`max_distance` bound, `(bucket, id)` order (D16); `_shared.build_matches_page`
(Unit 3) owns the rounded threshold + tail rule, not this adapter.

`find_nearest`/`find_nearest_exact` (5b): 5b.0's VERIFY found design.md's
literal two-key `ORDER BY ..., id LIMIT 1` defeats the HNSW plan even at
10,000 rows (raw `EXPLAIN` plans: apply-progress.md's Unit 5b section) --
confirming the documented fallback: a k-NN subquery re-sorted outside DOES
hit `phrases_embedding_hnsw_idx` under the same forcing. `find_nearest`
uses that fallback; `find_nearest_exact` uses the literal shape directly
(an exact scan wants Seq Scan anyway, same planner setting as `find_matches`).

`lock_for_write` delegates to `platform.db.acquire_write_lock`, mapping
SQLSTATE `55P03` to `LockTimeout`. `add()` maps ONLY a `23505` on
`phrases_unique_normalized_text_uidx` to `DuplicateTextConflict`.

`after_statement` (test-only): invoked with a per-repository statement
counter after every real query -- the barrier-snapshot test
(`test_nearest_and_uow.py`, a follow-up commit on this branch) uses it to
pause between `find_nearest` and `find_matches` in one transaction.
"""

from __future__ import annotations

from collections.abc import Callable
from math import floor
from typing import TYPE_CHECKING, Any, cast

from sqlalchemy import Connection, Engine, Row, text
from sqlalchemy.exc import IntegrityError, OperationalError

from app.modules.phrases.contracts import (
    DuplicateTextConflict,
    Isolation,
    ListCursor,
    LockTimeout,
    Match,
    MatchCursor,
    Neighbor,
    NewPhrase,
    Page,
    Phrase,
    PhraseListPage,
    PhraseRepository,
    ValidationStatus,
)
from app.modules.similarity.contracts import KEY_EPSILON, Vector
from app.platform.db import acquire_write_lock

_DEFAULT_EF_SEARCH = 200  # design.md's HNSW_EF_SEARCH default; Unit 6 wires the real setting
_DEFAULT_LOCK_TIMEOUT_MS = 5000  # design.md's LOCK_TIMEOUT_MS default
_KNN_CANDIDATES = 10  # design.md's documented fallback size ("k = 10")
_UNIQUE_TEXT_CONSTRAINT = "phrases_unique_normalized_text_uidx"
_LOCK_TIMEOUT_SQLSTATE = "55P03"

# design.md's SQL, verbatim except `CAST(:q AS vector)` (no pgvector-python
# adapter installed; `:q::vector` is unusable -- `text()` does not parse a
# `:name` immediately followed by `::`).
_BASE_SELECT = """
SELECT id, text, embedding <=> CAST(:q AS vector) AS distance,
       floor((embedding <=> CAST(:q AS vector)) / 1e-6) AS bucket
FROM phrases
WHERE embedding <=> CAST(:q AS vector) <= :max_distance
"""

_CURSOR_PREDICATE = """
  AND ( floor((embedding <=> CAST(:q AS vector)) / 1e-6) > :cursor_bucket
        OR (floor((embedding <=> CAST(:q AS vector)) / 1e-6) = :cursor_bucket AND id > :cursor_id) )
"""

_ORDER_LIMIT = """
ORDER BY bucket, id
LIMIT :limit + 1
"""


def build_find_matches_query(*, has_cursor: bool) -> str:
    """Exposed so the EXPLAIN guard test runs the real query, not a copy."""
    predicate = _CURSOR_PREDICATE if has_cursor else ""
    return _BASE_SELECT + predicate + _ORDER_LIMIT


# `count_matches`: same widened `max_distance` bound as `find_matches`
# (no cursor, no ordering, no bucket needed) -- the UI's "10/46
# coincidencias" counter reads this, independent of any page.
_COUNT_MATCHES_QUERY = """
SELECT count(*) FROM phrases
WHERE embedding <=> CAST(:q AS vector) <= :max_distance
"""


# `find_nearest`: the documented k-NN-subquery fallback (5b.0's VERIFY).
FIND_NEAREST_QUERY = """
SELECT id, text, distance FROM (
    SELECT id, text, embedding <=> CAST(:q AS vector) AS distance
    FROM phrases
    ORDER BY embedding <=> CAST(:q AS vector)
    LIMIT :k
) candidates
ORDER BY distance, id
LIMIT 1
"""

# `find_nearest_exact`: design.md's literal shape (exact scan wants Seq Scan).
FIND_NEAREST_EXACT_QUERY = """
SELECT id, text, embedding <=> CAST(:q AS vector) AS distance
FROM phrases
ORDER BY embedding <=> CAST(:q AS vector), id
LIMIT 1
"""

# `list_recent` (Unit 7b fix-pass, task 2): newest first, no cursor, per
# `PhraseRepository.list_recent`'s own comment -- same `(created_at, id)
# DESC` ordering as `InMemoryPhraseRepository.list_recent`. Served by
# migration 0001's `phrases_created_at_id_idx (created_at DESC, id DESC)`,
# unused until now. `embedding::text` (not the bare column): no
# pgvector-python adapter is registered on this connection (this module's
# own docstring/`serialize_vector` note), so casting explicitly guarantees
# the `[c0,c1,...]` text form `deserialize_vector` below expects, instead of
# depending on driver-specific behaviour for an unregistered custom OID.
LIST_RECENT_QUERY = """
SELECT id, text, normalized_text, embedding::text AS embedding, similarity_score,
       most_similar_phrase_id, validation_status, validated_at, created_at
FROM phrases
ORDER BY created_at DESC, id DESC
LIMIT :limit
"""

# `list_page` (real pagination for `GET /phrases`, see `contracts.py`'s
# `PhraseListPage`): same `(created_at, id) DESC` ordering and index as
# `list_recent` above, but keyset-continued from an opaque cursor instead of
# always starting at the top. Row-constructor comparison
# `(created_at, id) < (:cursor_created_at, :cursor_id)` is exactly "strictly
# after the cursor in DESC order" -- Postgres compares row constructors
# lexicographically, so this is equivalent to `find_matches`'s
# bucket-then-id OR chain without needing one.
_LIST_BASE_SELECT = """
SELECT id, text, normalized_text, embedding::text AS embedding, similarity_score,
       most_similar_phrase_id, validation_status, validated_at, created_at
FROM phrases
"""

_LIST_CURSOR_PREDICATE = """
WHERE (created_at, id) < (:cursor_created_at, :cursor_id)
"""

_LIST_ORDER_LIMIT = """
ORDER BY created_at DESC, id DESC
LIMIT :limit + 1
"""


def build_list_page_query(*, has_cursor: bool) -> str:
    """Exposed so a plan/EXPLAIN test runs the real query, not a copy."""
    predicate = _LIST_CURSOR_PREDICATE if has_cursor else ""
    return _LIST_BASE_SELECT + predicate + _LIST_ORDER_LIMIT


COUNT_ALL_QUERY = "SELECT count(*) FROM phrases"


def serialize_vector(vector: Vector) -> str:
    """`[c0,c1,...]` text literal pgvector's input parser accepts."""
    return "[" + ",".join(repr(float(component)) for component in vector) + "]"


def deserialize_vector(raw: str) -> Vector:
    """Inverse of `serialize_vector`. pgvector always renders a `vector`
    column cast to `::text` in this exact `[c0,c1,...]` form -- used by
    `list_recent` to turn a queried row's `embedding` column back into a
    `Vector` for the `Phrase` dataclass."""
    return tuple(float(component) for component in raw.strip("[]").split(","))


def _row_to_phrase(row: Row[Any]) -> Phrase:
    """Shared by `list_recent` and `list_page` — both query the same column
    set (`LIST_RECENT_QUERY` / `build_list_page_query`)."""
    return Phrase(
        id=row.id,
        text=row.text,
        normalized_text=row.normalized_text,
        embedding=deserialize_vector(row.embedding),
        similarity_score=row.similarity_score,
        most_similar_phrase_id=row.most_similar_phrase_id,
        validation_status=ValidationStatus(row.validation_status),
        validated_at=row.validated_at,
        created_at=row.created_at,
    )


def _bucket(distance: float) -> int:
    return floor(distance / KEY_EPSILON)


def _sqlstate(exc: IntegrityError | OperationalError) -> str | None:
    return getattr(exc.orig, "sqlstate", None)


def _is_unique_violation_on(exc: IntegrityError, constraint: str) -> bool:
    if _sqlstate(exc) != "23505":
        return False
    diag = getattr(exc.orig, "diag", None)
    return getattr(diag, "constraint_name", None) == constraint


class PgVectorPhraseRepository:
    """Bound to one open `Connection`; `PgVectorUnitOfWork` owns its lifecycle."""

    def __init__(
        self,
        connection: Connection,
        *,
        read_only: bool = False,
        ef_search: int = _DEFAULT_EF_SEARCH,
        lock_timeout_ms: int = _DEFAULT_LOCK_TIMEOUT_MS,
        after_statement: Callable[[int], None] | None = None,
    ) -> None:
        self._connection = connection
        self._read_only = read_only
        self._ef_search = ef_search
        self._lock_timeout_ms = lock_timeout_ms
        self._after_statement = after_statement
        self._statement_count = 0

    def _mark_statement(self) -> None:
        """Test-only instrumentation -- see this module's docstring."""
        self._statement_count += 1
        if self._after_statement is not None:
            self._after_statement(self._statement_count)

    def find_matches(
        self, q: Vector, max_distance: float, limit: int, cursor: MatchCursor | None
    ) -> Page[Match]:
        self._connection.execute(text("SELECT set_config('enable_indexscan', 'off', true)"))
        params: dict[str, object] = {
            "q": serialize_vector(q), "max_distance": max_distance, "limit": limit
        }
        if cursor is not None:
            params["cursor_bucket"] = _bucket(cursor.distance)
            params["cursor_id"] = cursor.id
        query = build_find_matches_query(has_cursor=cursor is not None)
        rows = self._connection.execute(text(query), params).fetchall()
        self._mark_statement()

        has_more = len(rows) > limit
        page_rows = rows[:limit]
        items = [Match(id=row.id, text=row.text, distance=row.distance) for row in page_rows]
        next_cursor = (
            MatchCursor(distance=items[-1].distance, id=items[-1].id)
            if has_more and items
            else None
        )
        return Page(items=items, next_cursor=next_cursor, has_more=has_more)

    def count_matches(self, q: Vector, max_distance: float) -> int:
        self._connection.execute(text("SELECT set_config('enable_indexscan', 'off', true)"))
        total = self._connection.execute(
            text(_COUNT_MATCHES_QUERY), {"q": serialize_vector(q), "max_distance": max_distance}
        ).scalar_one()
        self._mark_statement()
        return total

    def add(self, phrase: NewPhrase) -> Phrase:
        if self._read_only:
            raise RuntimeError("cannot write inside a read-only UnitOfWork")
        params = {
            "t": phrase.text, "n": phrase.normalized_text, "e": serialize_vector(phrase.embedding),
            "s": phrase.similarity_score, "nb": phrase.most_similar_phrase_id,
            "v": phrase.validation_status.value, "va": phrase.validated_at,
        }
        try:
            row = self._connection.execute(
                text(
                    "INSERT INTO phrases (text, normalized_text, embedding, similarity_score,"
                    " most_similar_phrase_id, validation_status, validated_at)"
                    " VALUES (:t, :n, :e, :s, :nb, :v, :va) RETURNING id, created_at"
                ),
                params,
            ).one()
        except IntegrityError as exc:
            # Only THIS constraint's 23505 is a domain conflict; others propagate.
            if _is_unique_violation_on(exc, _UNIQUE_TEXT_CONSTRAINT):
                raise DuplicateTextConflict(phrase.normalized_text) from exc
            raise
        self._mark_statement()
        return Phrase(id=row.id, created_at=row.created_at, **vars(phrase))

    def list_recent(self, limit: int) -> list[Phrase]:
        rows = self._connection.execute(text(LIST_RECENT_QUERY), {"limit": limit}).fetchall()
        self._mark_statement()
        return [_row_to_phrase(row) for row in rows]

    def list_page(self, limit: int, cursor: ListCursor | None) -> PhraseListPage:
        params: dict[str, object] = {"limit": limit}
        if cursor is not None:
            params["cursor_created_at"] = cursor.created_at
            params["cursor_id"] = cursor.id
        query = build_list_page_query(has_cursor=cursor is not None)
        rows = self._connection.execute(text(query), params).fetchall()
        self._mark_statement()

        has_more = len(rows) > limit
        page_rows = rows[:limit]
        items = [_row_to_phrase(row) for row in page_rows]
        next_cursor = (
            ListCursor(created_at=items[-1].created_at, id=items[-1].id)
            if has_more and items
            else None
        )
        total = self.count_all()
        return PhraseListPage(items=items, total=total, next_cursor=next_cursor, has_more=has_more)

    def count_all(self) -> int:
        total = self._connection.execute(text(COUNT_ALL_QUERY)).scalar_one()
        self._mark_statement()
        return total

    def find_nearest(self, q: Vector) -> Neighbor | None:
        # Unfiltered top-1, HNSW; explicit `on` in case an earlier statement
        # in this transaction turned it off (design.md).
        self._connection.execute(text("SELECT set_config('enable_indexscan', 'on', true)"))
        self._connection.execute(
            text("SELECT set_config('hnsw.ef_search', :ef, true)"), {"ef": str(self._ef_search)}
        )
        row = self._connection.execute(
            text(FIND_NEAREST_QUERY), {"q": serialize_vector(q), "k": _KNN_CANDIDATES}
        ).first()
        self._mark_statement()
        if row is None:
            return None
        return Neighbor(id=row.id, text=row.text, distance=row.distance)

    def find_nearest_exact(self, q: Vector) -> Neighbor | None:
        # Unfiltered top-1, EXACT scan -- SavePhrase only, under the lock.
        self._connection.execute(text("SELECT set_config('enable_indexscan', 'off', true)"))
        row = self._connection.execute(
            text(FIND_NEAREST_EXACT_QUERY), {"q": serialize_vector(q)}
        ).first()
        self._mark_statement()
        if row is None:
            return None
        return Neighbor(id=row.id, text=row.text, distance=row.distance)

    def lock_for_write(self) -> None:
        try:
            acquire_write_lock(self._connection, lock_timeout_ms=self._lock_timeout_ms)
        except OperationalError as exc:
            if _sqlstate(exc) == _LOCK_TIMEOUT_SQLSTATE:
                raise LockTimeout from exc
            raise
        self._mark_statement()


if TYPE_CHECKING:
    # mypy-only structural conformance check (Unit 7b fix-pass, task 1):
    # `PgVectorPhraseRepository` must satisfy `PhraseRepository` in full.
    #
    # Why this check is needed and where it was missing: `PgVectorUnitOfWork
    # .repo: PgVectorPhraseRepository` (a concrete, narrower type) never
    # structurally satisfies `UnitOfWork.repo: PhraseRepository` (a mutable
    # Protocol ATTRIBUTE, which mypy treats as INVARIANT -- it could be read
    # OR written through the Protocol-typed reference, so a narrower
    # assigned type is always rejected, even when it is a superset of
    # behaviour). `main.py`'s `_build_container` hits exactly that
    # pre-existing, legitimate false positive when it passes
    # `PgVectorUnitOfWorkFactory` to a `UnitOfWorkFactory`-typed parameter,
    # and silences it with `# type: ignore[arg-type]` (in place since Unit
    # 5b). That single suppressed line was the ONLY place in `src/` where
    # `PgVectorPhraseRepository` ever got checked against `PhraseRepository`
    # -- and only indirectly, through the `repo` attribute -- so the
    # ignore silently swallowed this class's separate, genuine missing
    # `list_recent` method too (confirmed empirically: removing the ignore
    # surfaces only the attribute-invariance note, never a missing-member
    # note, because mypy's attribute-type check short-circuits before
    # comparing the two classes' full member sets).
    #
    # Checking `PgVectorPhraseRepository` directly against `PhraseRepository`
    # here -- never through the mutable `.repo` attribute -- sidesteps that
    # invariance false positive entirely (confirmed empirically: this cast
    # alone, with `list_recent` missing, correctly failed with `"PgVector
    # PhraseRepository" is missing following "PhraseRepository" protocol
    # member: list_recent`). It is therefore a cheap (zero runtime cost,
    # `TYPE_CHECKING`-only), correct, no-false-positive guard against this
    # exact class of regression recurring for this adapter.
    _phrase_repository_conformance: PhraseRepository = cast(PgVectorPhraseRepository, None)


class PgVectorUnitOfWork:
    """Transaction wrapper: connect, isolation, commit/rollback. Advisory
    lock + `23505` mapping live on `PgVectorPhraseRepository`, not here --
    the lock is scoped to one statement inside the transaction, not
    `__enter__` (design.md: "taken by SavePhrase only, at the top")."""

    def __init__(
        self,
        engine: Engine,
        *,
        isolation: Isolation,
        read_only: bool,
        ef_search: int = _DEFAULT_EF_SEARCH,
        lock_timeout_ms: int = _DEFAULT_LOCK_TIMEOUT_MS,
        after_statement: Callable[[int], None] | None = None,
    ) -> None:
        self._engine = engine
        self.isolation = isolation
        self.read_only = read_only
        self._ef_search = ef_search
        self._lock_timeout_ms = lock_timeout_ms
        self._after_statement = after_statement
        self._connection: Connection | None = None
        self.repo: PgVectorPhraseRepository

    def __enter__(self) -> PgVectorUnitOfWork:
        connection = self._engine.connect()
        connection.execution_options(
            isolation_level=self.isolation.value, postgresql_readonly=self.read_only
        )
        self._connection = connection
        self.repo = PgVectorPhraseRepository(
            connection,
            read_only=self.read_only,
            ef_search=self._ef_search,
            lock_timeout_ms=self._lock_timeout_ms,
            after_statement=self._after_statement,
        )
        return self

    def __exit__(self, *exc: object) -> None:
        connection = self._connection
        if connection is not None and not connection.closed:
            connection.rollback()
            connection.close()

    def commit(self) -> None:
        assert self._connection is not None
        self._connection.commit()

    def rollback(self) -> None:
        assert self._connection is not None
        self._connection.rollback()


class PgVectorUnitOfWorkFactory:
    def __init__(
        self,
        engine: Engine,
        *,
        ef_search: int = _DEFAULT_EF_SEARCH,
        lock_timeout_ms: int = _DEFAULT_LOCK_TIMEOUT_MS,
        after_statement: Callable[[int], None] | None = None,
    ) -> None:
        self._engine = engine
        self._ef_search = ef_search
        self._lock_timeout_ms = lock_timeout_ms
        self._after_statement = after_statement

    def __call__(
        self, *, isolation: Isolation = Isolation.READ_COMMITTED, read_only: bool = False
    ) -> PgVectorUnitOfWork:
        return PgVectorUnitOfWork(
            self._engine,
            isolation=isolation,
            read_only=read_only,
            ef_search=self._ef_search,
            lock_timeout_ms=self._lock_timeout_ms,
            after_statement=self._after_statement,
        )
