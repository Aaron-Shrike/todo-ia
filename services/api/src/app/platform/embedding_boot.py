"""Boot-time embedding wiring helpers (tasks.md 8.2, design.md "Dimension
coherence check at startup"). `check_dimension_coherence` is the PURE
comparison at the heart of the contract -- unit-tested directly, no
database required. `read_vector_column_dimensions` and
`check_database_reachable` are the thin, no-branching SQL calls that
gather the facts the pure check compares; they lazily import `sqlalchemy`
INSIDE their own function bodies (same pattern as `adapters/
sentence_transformers.py::load_sentence_transformer`) so this module stays
import-safe in a dev venv that has not installed `sqlalchemy` -- confirmed
absent in this environment (see apply-progress.md's Unit 8 section).
Neither function is exercised by a test in this batch: no live Postgres is
available here, the same category of gap as Unit 4's deferred typmod-reader
test.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from sqlalchemy import Connection, Engine


class EmbeddingDimensionMismatch(Exception):
    """Raised at boot when the `phrases.embedding` column's typmod, the
    loaded provider's `dimensions`, and `EMBEDDING_DIMENSIONS` do not all
    agree. A model swap that would silently write differently-sized
    vectors into a fixed `vector(n)` column is caught HERE, before the
    first insert, not after (design.md: "A model swap that silently writes
    768-dim vectors into a `vector(384)` column is caught at boot")."""

    def __init__(
        self, *, typmod: int, provider_dimensions: int, configured_dimensions: int
    ) -> None:
        self.typmod = typmod
        self.provider_dimensions = provider_dimensions
        self.configured_dimensions = configured_dimensions
        super().__init__(
            f"embedding dimension mismatch: column typmod={typmod}, "
            f"provider={provider_dimensions}, EMBEDDING_DIMENSIONS={configured_dimensions}"
        )


def check_dimension_coherence(
    *, typmod: int, provider_dimensions: int, configured_dimensions: int
) -> None:
    """PURE: raises `EmbeddingDimensionMismatch` unless all three values
    are identical. The caller supplies each value already gathered (from
    the DB, the loaded provider, and `Settings`) -- this function makes no
    I/O of its own, which is what makes it unit-testable without a
    database."""
    if not (typmod == provider_dimensions == configured_dimensions):
        raise EmbeddingDimensionMismatch(
            typmod=typmod,
            provider_dimensions=provider_dimensions,
            configured_dimensions=configured_dimensions,
        )


def read_vector_column_dimensions(connection: Connection, *, table: str, column: str) -> int:
    """Reads `pg_attribute.atttypmod` for a `vector(n)` column: pgvector
    stores the declared dimension directly in typmod, with no
    `VARHDRSZ`-style offset (unlike `varchar`) -- per pgvector's
    `vector_typmod_in` C source. **Not exercised by a test in this
    environment** -- no live Postgres instance and `sqlalchemy` itself is
    not installed in this dev venv; this is a genuine, documented gap for
    the next docker-capable session (see apply-progress.md's Unit 8
    section)."""
    from sqlalchemy import text

    query = text(
        "SELECT atttypmod FROM pg_attribute WHERE attrelid = :table::regclass AND attname = :column"
    )
    return int(connection.execute(query, {"table": table, "column": column}).scalar_one())


def check_database_reachable(engine: Engine) -> bool:
    """`SELECT 1` -- the same readiness probe `GET /health` has always
    needed (design.md: "200 only when SELECT 1 succeeds"); Units 6b/7
    injected `check_database` as a plain `Callable[[], bool]` closure built
    ad hoc per test, this is the first REAL implementation, for the
    production lifespan (Unit 8). Catches `OperationalError` specifically
    (a genuinely down/unreachable database) and lets any other exception
    propagate -- a mid-query crash from something other than connectivity
    is a bug to surface, not a readiness signal to swallow. **Not exercised
    by a test in this batch** -- see `read_vector_column_dimensions`'s
    docstring for why."""
    from sqlalchemy import text
    from sqlalchemy.exc import OperationalError

    try:
        with engine.connect() as connection:
            connection.execute(text("SELECT 1"))
        return True
    except OperationalError:
        return False
