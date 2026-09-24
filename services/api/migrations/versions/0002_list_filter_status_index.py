"""list filter status index

Revision ID: 0002
Revises: 0001
Create Date: 2026-09-24

Raw SQL (design.md "Migration `0002_list_filter_status_index.py`"). Adds one
partial index serving `GET /phrases?status=duplicate_confirmed`'s ordering,
its cursor position, and an index-only count in one structure, given the
observed skew where `duplicate_confirmed` is a small minority of rows
(explore-db-findings.md: 20,001 `unique` / 3 `duplicate_confirmed`).

D7 (design.md): plain `CREATE INDEX`, not `CONCURRENTLY` -- Alembic runs
each migration in a transaction (`CONCURRENTLY` cannot run inside one), and
the build is a single ~20k-row scan (milliseconds) over an index that only
ever holds a handful of rows, so the lock window is negligible.
"""

from __future__ import annotations

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "0002"
down_revision: str | None = "0001"
branch_labels: str | None = None
depends_on: str | None = None

_INDEX_NAME = "phrases_duplicate_confirmed_created_at_id_idx"


def upgrade() -> None:
    op.execute(
        f"CREATE INDEX {_INDEX_NAME} "
        "ON phrases (created_at DESC, id DESC) "
        "WHERE validation_status = 'duplicate_confirmed';"
    )


def downgrade() -> None:
    op.execute(f"DROP INDEX IF EXISTS {_INDEX_NAME};")
