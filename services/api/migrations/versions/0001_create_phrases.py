"""create phrases table

Revision ID: 0001
Revises:
Create Date: 2026-09-22

Raw SQL (design.md "Data Model and Migrations"). Enables `vector`, then
creates the HNSW index only after confirming the installed extension
supports it (>= 0.5.0) — tasks.md 4.2's "fail fast if HNSW unsupported".
"""

from __future__ import annotations

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "0001"
down_revision: str | None = None
branch_labels: str | None = None
depends_on: str | None = None

# Verified for the pinned image (pgvector/pgvector:pg16, extversion 0.8.6,
# task 4.0); this guard protects any other image used in its place.
_MIN_VECTOR_VERSION_FOR_HNSW = (0, 5, 0)


def _assert_hnsw_is_supported() -> None:
    connection = op.get_bind()
    row = connection.exec_driver_sql(
        "SELECT extversion FROM pg_extension WHERE extname = 'vector'"
    ).fetchone()
    if row is None:
        raise RuntimeError(
            "pgvector extension not found after CREATE EXTENSION IF NOT EXISTS vector; "
            "cannot verify HNSW support."
        )
    installed = tuple(int(part) for part in row[0].split(".")[:3])
    if installed < _MIN_VECTOR_VERSION_FOR_HNSW:
        required = ".".join(str(part) for part in _MIN_VECTOR_VERSION_FOR_HNSW)
        raise RuntimeError(
            f"pgvector extension version {row[0]} does not support HNSW indexes "
            f"(requires >= {required}). Fall back to postgres:16-alpine plus a "
            "build-time pgvector install per design.md's documented fallback, or "
            "use a pgvector image that ships a newer extension version."
        )


def upgrade() -> None:
    op.execute("CREATE EXTENSION IF NOT EXISTS vector;")
    _assert_hnsw_is_supported()

    op.execute(
        """
        CREATE TABLE phrases (
          id                     BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
          text                   TEXT        NOT NULL,
          normalized_text        TEXT        NOT NULL,
          embedding              vector(384) NOT NULL,
          similarity_score       DOUBLE PRECISION NULL CHECK (similarity_score BETWEEN 0 AND 1),
          most_similar_phrase_id BIGINT      NULL REFERENCES phrases(id) ON DELETE RESTRICT,
          validation_status      TEXT        NOT NULL
                                   CHECK (validation_status IN ('unique', 'duplicate_confirmed')),
          validated_at           TIMESTAMPTZ NOT NULL,
          created_at             TIMESTAMPTZ NOT NULL DEFAULT now(),
          CONSTRAINT phrases_metadata_paired CHECK (
            (similarity_score IS NULL) = (most_similar_phrase_id IS NULL)
          ),
          CONSTRAINT phrases_confirmed_has_neighbor CHECK (
            validation_status <> 'duplicate_confirmed'
            OR (similarity_score IS NOT NULL AND most_similar_phrase_id IS NOT NULL)
          )
        );
        """
    )

    # Serves `find_nearest` (validate endpoint) only; `find_matches` and
    # `find_nearest_exact` are exact scans and never use it (D1).
    op.execute(
        "CREATE INDEX phrases_embedding_hnsw_idx "
        "ON phrases USING hnsw (embedding vector_cosine_ops);"
    )
    op.execute("CREATE INDEX phrases_created_at_id_idx ON phrases (created_at DESC, id DESC);")

    # Integrity backstop (ADR-006): at most one `unique` row per normalized
    # text; `duplicate_confirmed` rows fall outside the predicate.
    op.execute(
        "CREATE UNIQUE INDEX phrases_unique_normalized_text_uidx "
        "ON phrases (normalized_text) WHERE validation_status = 'unique';"
    )


def downgrade() -> None:
    op.execute("DROP TABLE IF EXISTS phrases;")
    op.execute("DROP EXTENSION IF EXISTS vector;")
