"""Integration tests for `platform/embedding_boot.py`'s two DB-touching
functions (Unit 8's `read_vector_column_dimensions` / `check_database_
reachable`), closing the gap Unit 8's own docstrings flagged as "not
exercised by a test in this batch -- no live Postgres available" (see
apply-progress.md's Unit 8 section). Unit 14's real `docker compose up`
against a live `db` service is the first environment where these can
actually run, and it caught a genuine bug (see the Unit 14 apply-progress
note): `:table::regclass` was never substituted by SQLAlchemy's bind-param
parser, so `read_vector_column_dimensions` raised a Postgres syntax error
on every real boot. Fixed to `CAST(:table AS regclass)` here.

Runs against the real `phrases_test` database (same `db` compose service,
same conventions as `test_schema.py`). Marker: `integration`.
"""

from __future__ import annotations

import os
from collections.abc import Iterator
from pathlib import Path

import pytest
from alembic import command
from alembic.config import Config
from sqlalchemy import Engine, create_engine

from app.platform.embedding_boot import check_database_reachable, read_vector_column_dimensions

pytestmark = pytest.mark.integration

_API_ROOT = Path(__file__).resolve().parents[2]


def _database_url() -> str:
    base = os.environ.get(
        "DATABASE_URL", "postgresql+psycopg://todo_ia:todo_ia@localhost:5432/todo_ia"
    )
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


class TestReadVectorColumnDimensions:
    def test_matches_the_migrated_vector_384_column(self, engine: Engine) -> None:
        with engine.connect() as connection:
            typmod = read_vector_column_dimensions(
                connection, table="phrases", column="embedding"
            )
        assert typmod == 384


class TestCheckDatabaseReachable:
    def test_true_against_the_real_running_database(self, engine: Engine) -> None:
        assert check_database_reachable(engine) is True

    def test_false_when_the_engine_points_nowhere(self) -> None:
        unreachable = create_engine(
            "postgresql+psycopg://todo_ia:todo_ia@localhost:59999/todo_ia",
            connect_args={"connect_timeout": 1},
        )
        try:
            assert check_database_reachable(unreachable) is False
        finally:
            unreachable.dispose()
