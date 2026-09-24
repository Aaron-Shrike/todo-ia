"""EXPLAIN guards for `GET /phrases`'s `status` filter (Unit 2, tasks.md
2.4, design.md's Testing Strategy). Proves migration 0002's partial index
`phrases_duplicate_confirmed_created_at_id_idx` is actually chosen by the
planner for the rare `status=duplicate_confirmed` filter -- with a cursor,
without one, and for the count query -- against a skewed table shaped like
`explore-db-findings.md` (20000 `unique` / 3 `duplicate_confirmed`), AND
under `SET plan_cache_mode = force_generic_plan`, which guards D4's
decision to inline the status value as a SQL literal rather than bind it
as `:status`: a bound parameter could fall back to a generic plan that
can't prove `$1 = 'duplicate_confirmed'` and would silently stop using the
partial index; a literal can't, by construction, regardless of plan mode.
Also re-confirms the unfiltered path is unaffected (still `Index (Only)
Scan` on `phrases_created_at_id_idx`, never a `Seq Scan`) -- no plan
regression on the default page.

**Apply-time note**: this file could not be executed via pytest this
session -- see `apply-progress.md`'s Unit 2 section for why (same sandboxed
TCP limitation Unit 1 hit). Every assertion here was hand-verified via
`docker compose exec db psql -U todo_ia -d phrases_test` against a table
built from this exact seed shape before this file was written; see
apply-progress.md for the literal `EXPLAIN (ANALYZE, BUFFERS)` output.
Re-run this file for real via `pytest -m integration
tests/integration/test_list_filters_pgvector.py -q` in an unsandboxed
environment before this unit is considered fully verified.
"""

from __future__ import annotations

import os
from collections.abc import Iterator
from pathlib import Path

import pytest
from alembic import command
from alembic.config import Config
from sqlalchemy import Engine, create_engine, text

from app.modules.phrases.adapters.pgvector_repository import (
    build_count_list_query,
    build_list_page_query,
)
from app.modules.phrases.contracts import ValidationStatus

pytestmark = pytest.mark.integration

_API_ROOT = Path(__file__).resolve().parents[2]


def _database_url() -> str:
    # Same convention as every other file under `tests/integration/`
    # (`test_pgvector_repository.py`, `test_list_page_pgvector.py`, etc.):
    # each defines its own copy rather than importing across test modules.
    base = os.environ.get(
        "DATABASE_URL", "postgresql+psycopg://todo_ia:todo_ia@localhost:5432/todo_ia"
    )
    return base.rpartition("/")[0] + "/phrases_test"

# A 384-dim zero vector literal -- content is irrelevant to these EXPLAIN
# guards (they exercise the `validation_status`/cursor/`ORDER BY ... LIMIT`
# path, never the HNSW embedding index), but the column is `NOT NULL`.
_ZERO_VECTOR = "[" + ",".join(["0"] * 384) + "]"

_UNIQUE_COUNT = 20000  # explore-db-findings.md's real table shape
_DUPLICATE_COUNT = 3


def _alembic_config(database_url: str) -> Config:
    config = Config(str(_API_ROOT / "alembic.ini"))
    config.set_main_option("script_location", str(_API_ROOT / "migrations"))
    config.set_main_option("sqlalchemy.url", database_url)
    return config


@pytest.fixture(scope="module")
def database_url() -> str:
    return _database_url()


@pytest.fixture(scope="module")
def engine(database_url: str) -> Iterator[Engine]:
    engine = create_engine(database_url)
    yield engine
    engine.dispose()


@pytest.fixture(scope="module", autouse=True)
def _skewed_table(database_url: str, engine: Engine) -> Iterator[None]:
    """Module-scoped: rebuilding a 20003-row table per test would be slow
    and these EXPLAIN guards are read-only, so every test in this file
    shares one seeded table (unlike the function-scoped `_freshly_migrated_
    schema` fixture the smaller pgvector integration files use)."""
    config = _alembic_config(database_url)
    command.downgrade(config, "base")
    command.upgrade(config, "head")
    with engine.begin() as conn:
        conn.execute(
            text(
                """
                INSERT INTO phrases (text, normalized_text, embedding, similarity_score,
                                      most_similar_phrase_id, validation_status,
                                      validated_at, created_at)
                SELECT
                    'p' || g, 'p' || g, CAST(:vec AS vector), NULL, NULL, 'unique',
                    now(), now() - (g || ' seconds')::interval
                FROM generate_series(1, :n) AS g
                """
            ),
            {"vec": _ZERO_VECTOR, "n": _UNIQUE_COUNT},
        )
        conn.execute(
            text(
                """
                INSERT INTO phrases (text, normalized_text, embedding, similarity_score,
                                      most_similar_phrase_id, validation_status,
                                      validated_at, created_at)
                SELECT
                    'dup' || g, 'dup' || g, CAST(:vec AS vector), 0.9, 1,
                    'duplicate_confirmed', now(), now() - (g || ' seconds')::interval
                FROM generate_series(1, :n) AS g
                """
            ),
            {"vec": _ZERO_VECTOR, "n": _DUPLICATE_COUNT},
        )
        conn.execute(text("ANALYZE phrases"))
    yield
    command.downgrade(config, "base")


def _explain_lines(engine: Engine, sql: str, params: dict[str, object]) -> str:
    with engine.connect() as conn:
        rows = conn.execute(text(f"EXPLAIN (ANALYZE, BUFFERS) {sql}"), params).fetchall()
    return "\n".join(str(row[0]) for row in rows)


def test_unfiltered_first_page_still_uses_the_created_at_id_index(engine: Engine) -> None:
    """No plan regression on the default (unfiltered) path -- Unit 1's
    `build_list_page_query(has_cursor=False)` output is already proven
    byte-identical to the pre-Unit-1 query (pure-logic test in
    `test_pgvector_repository.py`); this proves the REAL plan for that
    identical SQL text is unaffected too."""
    plan = _explain_lines(engine, build_list_page_query(has_cursor=False), {"limit": 11})
    assert "phrases_created_at_id_idx" in plan
    assert "Seq Scan" not in plan


def test_status_filter_uses_the_partial_index_without_a_cursor(engine: Engine) -> None:
    sql = build_list_page_query(has_cursor=False, status=ValidationStatus.DUPLICATE_CONFIRMED)
    plan = _explain_lines(engine, sql, {"limit": 11})
    assert "phrases_duplicate_confirmed_created_at_id_idx" in plan
    assert "Seq Scan" not in plan


def test_status_filter_uses_the_partial_index_with_a_cursor(engine: Engine) -> None:
    sql = build_list_page_query(
        has_cursor=True, status=ValidationStatus.DUPLICATE_CONFIRMED
    )
    plan = _explain_lines(
        engine,
        sql,
        {
            "limit": 11,
            "cursor_created_at": "2026-01-01T00:00:00Z",
            "cursor_id": 999_999_999,
        },
    )
    assert "phrases_duplicate_confirmed_created_at_id_idx" in plan
    assert "Seq Scan" not in plan


def test_status_filter_count_uses_the_partial_index(engine: Engine) -> None:
    sql = build_count_list_query(status=ValidationStatus.DUPLICATE_CONFIRMED)
    plan = _explain_lines(engine, sql, {})
    assert "phrases_duplicate_confirmed_created_at_id_idx" in plan
    assert "Seq Scan" not in plan


def test_status_filter_uses_the_partial_index_under_a_forced_generic_plan(
    engine: Engine,
) -> None:
    """D4's own guard: the status value is inlined as a SQL LITERAL, never
    bound as `:status` -- so even when Postgres is forced to use a GENERIC
    plan (as psycopg3 auto-prepare would eventually force for a real
    long-lived connection), the literal `validation_status =
    'duplicate_confirmed'` is still visible to the planner at prepare time
    and the partial index is still chosen. A bound `:status` parameter
    would NOT survive this guard -- a generic plan can't assume `$1 =
    'duplicate_confirmed'` and would fall back to the full
    `phrases_created_at_id_idx` (or a Seq Scan), silently regressing the
    exact case this migration exists for."""
    sql = build_list_page_query(has_cursor=True, status=ValidationStatus.DUPLICATE_CONFIRMED)
    # `:limit`/`:cursor_created_at`/`:cursor_id` become `$1`/`$2`/`$3` in the
    # order they appear in `sql` -- PREPARE needs positional placeholders.
    positional_sql = sql
    for name, placeholder in (
        ("cursor_created_at", "$1"),
        ("cursor_id", "$2"),
        ("limit", "$3"),
    ):
        positional_sql = positional_sql.replace(f":{name}", placeholder, 1)

    with engine.connect() as conn:
        conn.execute(text("SET plan_cache_mode = force_generic_plan"))
        conn.execute(
            text(f"PREPARE list_guard(timestamptz, bigint, int) AS {positional_sql}")
        )
        try:
            # Executed several times so a real client's auto-prepare
            # threshold (psycopg3: after 5 executions) would also have
            # kicked in by now, same as design.md's own rationale for D4.
            for _ in range(5):
                conn.execute(text("EXECUTE list_guard(now(), 999999999, 11)"))
            rows = conn.execute(
                text("EXPLAIN (ANALYZE, BUFFERS) EXECUTE list_guard(now(), 999999999, 11)")
            ).fetchall()
        finally:
            conn.execute(text("DEALLOCATE list_guard"))
    plan = "\n".join(str(row[0]) for row in rows)
    assert "phrases_duplicate_confirmed_created_at_id_idx" in plan
    assert "Seq Scan" not in plan
