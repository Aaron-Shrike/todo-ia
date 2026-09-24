"""Integration tests for the pgvector `list_page`/`count_all` adapter
(`GET /phrases`'s real pagination). Runs against real Postgres + pgvector
(`docker compose up -d db migrate`) — proves the row-constructor keyset
predicate (`(created_at, id) < (:cursor_created_at, :cursor_id)`) is valid
SQL and behaves correctly there, not just against the in-memory fake.
"""

from __future__ import annotations

import os
from collections.abc import Iterator
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest
from alembic import command
from alembic.config import Config
from sqlalchemy import Engine, create_engine, text

from app.modules.phrases.adapters.pgvector_repository import (
    PgVectorPhraseRepository,
    PgVectorUnitOfWorkFactory,
)
from app.modules.phrases.contracts import ListCursor, NewPhrase, UnitOfWorkFactory, ValidationStatus
from tests.contract_suite.repository_contract import ListPageContractSuite
from tests.contract_suite.vectors import vector_at_distance

pytestmark = pytest.mark.integration

_API_ROOT = Path(__file__).resolve().parents[2]


def _database_url() -> str:
    base = os.environ.get("DATABASE_URL", "postgresql+psycopg://todo_ia:todo_ia@localhost:5432/todo_ia")
    return base.rpartition("/")[0] + "/phrases_test"


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


@pytest.fixture(autouse=True)
def _freshly_migrated_schema(database_url: str) -> Iterator[None]:
    config = _alembic_config(database_url)
    command.downgrade(config, "base")
    command.upgrade(config, "head")
    yield


def _seed(engine: Engine, count: int) -> None:
    """Inserts `count` phrases with distinct, explicit `created_at` values
    (ascending) so newest-first ordering is unambiguous regardless of how
    fast the inserts run."""
    factory = PgVectorUnitOfWorkFactory(engine)
    base = datetime(2026, 1, 1, tzinfo=UTC)
    with factory() as uow:
        for i in range(count):
            uow.repo.add(
                NewPhrase(
                    text=f"p{i}",
                    normalized_text=f"p{i}",
                    embedding=vector_at_distance(0.05 + i * 0.0001),
                    similarity_score=None,
                    most_similar_phrase_id=None,
                    validation_status=ValidationStatus.UNIQUE,
                    validated_at=base,
                )
            )
        uow.commit()
    # `add` timestamps via the DB's own `now()` default (see migration
    # 0001), so every row in one fast test run can land in the SAME
    # microsecond -- overwrite `created_at` explicitly, spaced a second
    # apart, so the newest-first assertions below are deterministic.
    with engine.begin() as conn:
        rows = conn.execute(text("SELECT id FROM phrases ORDER BY id")).scalars().all()
        for offset, row_id in enumerate(rows):
            conn.execute(
                text("UPDATE phrases SET created_at = :ca WHERE id = :id"),
                {"ca": base + timedelta(seconds=offset), "id": row_id},
            )


class TestPgVectorListPageContract(ListPageContractSuite):
    """Registers `PgVectorPhraseRepository` against the shared, adapter-
    agnostic `list_page`/`count_all` scenarios (totality, empty store,
    running `total`) -- same registration pattern as `test_find_matches.py`'s
    `TestPgVectorMatchesContract`. The module's own bespoke tests below still
    own the DB-specific, timestamp-precise "genuinely newest-first" proof
    (`_seed`'s explicit `created_at` overwrite) that a shared, adapter-
    agnostic suite cannot express, since `NewPhrase` never exposes
    `created_at` for the in-memory side to accept either."""

    @pytest.fixture
    def uow_factory(self, engine: Engine) -> UnitOfWorkFactory:
        return PgVectorUnitOfWorkFactory(engine)


def test_list_page_pagination_walk_reaches_every_row_exactly_once(engine: Engine) -> None:
    _seed(engine, 5)
    with engine.connect() as connection:
        repo = PgVectorPhraseRepository(connection)
        collected: list[str] = []
        cursor: ListCursor | None = None
        for _ in range(10):
            page = repo.list_page(2, cursor)
            assert page.total == 5
            collected.extend(p.text for p in page.items)
            if not page.has_more:
                assert page.next_cursor is None
                break
            cursor = page.next_cursor
        else:
            pytest.fail("pagination walk did not terminate")

    assert collected == ["p4", "p3", "p2", "p1", "p0"]  # newest first, no repeats, none skipped


def test_list_page_empty_store(engine: Engine) -> None:
    with engine.connect() as connection:
        repo = PgVectorPhraseRepository(connection)
        page = repo.list_page(10, None)
    assert page.items == []
    assert page.total == 0
    assert page.next_cursor is None
    assert page.has_more is False


def test_count_all_matches_total_rows(engine: Engine) -> None:
    _seed(engine, 7)
    with engine.connect() as connection:
        repo = PgVectorPhraseRepository(connection)
        assert repo.count_all() == 7
