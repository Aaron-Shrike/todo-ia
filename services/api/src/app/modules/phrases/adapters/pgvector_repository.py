"""pgvector `find_matches` (tasks.md 5a.1): the exact keyset match query.

`set_config('enable_indexscan', 'off', true)` (`is_local=true`, the
parameterizable `SET LOCAL`) forces an exact scan past
`phrases_embedding_hnsw_idx` (D1/D8), vanishing at commit/rollback -- never
leaking into a pooled connection's next transaction. `find_matches` filters
on the WIDENED `max_distance` bound and orders on `(bucket, id)` (D16); it
does NOT apply the rounded `Decimal` threshold or the tail rule -- that is
`_shared.build_matches_page` (Unit 3), mirroring the in-memory adapter (the
oracle this is tested against via `MatchesContractSuite`).

`add()` is a minimal INSERT, existing only to seed fixtures for this
module's tests and `MatchesContractSuite`'s `_seed()` helper. `find_nearest`,
`find_nearest_exact` and `lock_for_write` are Unit 5b's write-path
primitives and raise `NotImplementedError` here -- see apply-progress.md's
Unit 5a deviations for the split rationale.
"""

from __future__ import annotations

from math import floor

from sqlalchemy import Connection, Engine, text

from app.modules.phrases.contracts import (
    Isolation,
    Match,
    MatchCursor,
    Neighbor,
    NewPhrase,
    Page,
    Phrase,
)
from app.modules.similarity.contracts import KEY_EPSILON, Vector

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


def serialize_vector(vector: Vector) -> str:
    """`[c0,c1,...]` text literal pgvector's input parser accepts."""
    return "[" + ",".join(repr(float(component)) for component in vector) + "]"


def _bucket(distance: float) -> int:
    return floor(distance / KEY_EPSILON)


class PgVectorPhraseRepository:
    """Bound to one open `Connection`; `PgVectorUnitOfWork` owns its lifecycle."""

    def __init__(self, connection: Connection, *, read_only: bool = False) -> None:
        self._connection = connection
        self._read_only = read_only

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

        has_more = len(rows) > limit
        page_rows = rows[:limit]
        items = [Match(id=row.id, text=row.text, distance=row.distance) for row in page_rows]
        next_cursor = (
            MatchCursor(distance=items[-1].distance, id=items[-1].id)
            if has_more and items
            else None
        )
        return Page(items=items, next_cursor=next_cursor, has_more=has_more)

    def add(self, phrase: NewPhrase) -> Phrase:
        # Seeding-only insert -- see this module's docstring.
        if self._read_only:
            raise RuntimeError("cannot write inside a read-only UnitOfWork")
        params = {
            "t": phrase.text, "n": phrase.normalized_text, "e": serialize_vector(phrase.embedding),
            "s": phrase.similarity_score, "nb": phrase.most_similar_phrase_id,
            "v": phrase.validation_status.value, "va": phrase.validated_at,
        }
        row = self._connection.execute(
            text(
                "INSERT INTO phrases (text, normalized_text, embedding, similarity_score,"
                " most_similar_phrase_id, validation_status, validated_at)"
                " VALUES (:t, :n, :e, :s, :nb, :v, :va) RETURNING id, created_at"
            ),
            params,
        ).one()
        return Phrase(id=row.id, created_at=row.created_at, **vars(phrase))

    def find_nearest(self, q: Vector) -> Neighbor | None:
        raise NotImplementedError("find_nearest lands in Unit 5b")

    def find_nearest_exact(self, q: Vector) -> Neighbor | None:
        raise NotImplementedError("find_nearest_exact lands in Unit 5b")

    def lock_for_write(self) -> None:
        raise NotImplementedError("lock_for_write (advisory lock) lands in Unit 5b")


class PgVectorUnitOfWork:
    """Minimal transaction wrapper (connect, isolation, commit/rollback).
    Advisory lock and conflict mapping land in Unit 5b.2."""

    def __init__(self, engine: Engine, *, isolation: Isolation, read_only: bool) -> None:
        self._engine = engine
        self.isolation = isolation
        self.read_only = read_only
        self._connection: Connection | None = None
        self.repo: PgVectorPhraseRepository

    def __enter__(self) -> PgVectorUnitOfWork:
        connection = self._engine.connect()
        connection.execution_options(
            isolation_level=self.isolation.value, postgresql_readonly=self.read_only
        )
        self._connection = connection
        self.repo = PgVectorPhraseRepository(connection, read_only=self.read_only)
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
    def __init__(self, engine: Engine) -> None:
        self._engine = engine

    def __call__(
        self, *, isolation: Isolation = Isolation.READ_COMMITTED, read_only: bool = False
    ) -> PgVectorUnitOfWork:
        return PgVectorUnitOfWork(self._engine, isolation=isolation, read_only=read_only)
