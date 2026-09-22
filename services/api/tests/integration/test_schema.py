"""Integration tests for the `phrases` schema (tasks.md Unit 4 / 4.3).

Runs against real Postgres + pgvector, the throwaway `phrases_test` database
created by `infra/db/init.sql` in the `db` compose service. Requires
`docker compose up -d db` first. Marker: `integration` (excluded from
`make test-unit`).

Covers (specs/phrase-management/spec.md): "Database-level uniqueness of
unconfirmed phrases", "Migrations", and the `phrases_metadata_paired` /
`phrases_confirmed_has_neighbor` CHECKs from design.md.
"""

from __future__ import annotations

import os
from collections.abc import Iterator
from pathlib import Path

import pytest
from alembic import command
from alembic.config import Config
from sqlalchemy import Connection, Engine, create_engine, text
from sqlalchemy.exc import IntegrityError

pytestmark = pytest.mark.integration

_API_ROOT = Path(__file__).resolve().parents[2]
_VECTOR = "[" + ",".join(["0.1"] * 384) + "]"


def _database_url() -> str:
    """`phrases_test`, derived from `DATABASE_URL` or a host-side default."""
    base = os.environ.get(
        "DATABASE_URL", "postgresql+psycopg://todo_ia:todo_ia@localhost:5432/todo_ia"
    )
    return base.rpartition("/")[0] + "/phrases_test"


def _alembic_config(database_url: str) -> Config:
    config = Config(str(_API_ROOT / "alembic.ini"))
    config.set_main_option("script_location", str(_API_ROOT / "migrations"))
    config.set_main_option("sqlalchemy.url", database_url)
    return config


def _insert(
    conn: Connection,
    text_value: str,
    normalized_text: str,
    status: str = "unique",
    score: float | None = None,
    neighbor: int | None = None,
) -> int:
    row = conn.execute(
        text(
            "INSERT INTO phrases (text, normalized_text, embedding, similarity_score,"
            " most_similar_phrase_id, validation_status, validated_at)"
            " VALUES (:t, :n, :e, :s, :nb, :v, now()) RETURNING id"
        ),
        {
            "t": text_value,
            "n": normalized_text,
            "e": _VECTOR,
            "s": score,
            "nb": neighbor,
            "v": status,
        },
    )
    return row.scalar_one()


def _schema_state(conn: Connection) -> tuple[bool, bool]:
    table = conn.execute(text("SELECT to_regclass('public.phrases') IS NOT NULL")).scalar_one()
    ext = conn.execute(
        text("SELECT EXISTS (SELECT 1 FROM pg_extension WHERE extname = 'vector')")
    ).scalar_one()
    return bool(table), bool(ext)


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
    """Clean slate per test via Alembic's own downgrade/upgrade — not a raw
    `DROP TABLE`, which would desync `alembic_version`. Both directions are
    idempotent, safe from any starting state."""
    config = _alembic_config(database_url)
    command.downgrade(config, "base")
    command.upgrade(config, "head")
    yield


class TestDatabaseLevelUniqueness:
    """specs/phrase-management/spec.md: "Database-level uniqueness of unconfirmed phrases"."""

    def test_second_unique_row_with_same_text_is_rejected(self, engine: Engine) -> None:
        with engine.begin() as conn:
            _insert(conn, "Comprar leche", "comprar leche")
        with pytest.raises(IntegrityError) as excinfo:
            with engine.begin() as conn:
                _insert(conn, "comprar   leche!", "comprar leche")
        assert "phrases_unique_normalized_text_uidx" in str(excinfo.value.orig)

    def test_confirmed_duplicate_with_same_text_is_accepted(self, engine: Engine) -> None:
        with engine.begin() as conn:
            neighbor = _insert(conn, "Comprar leche", "comprar leche")
        with engine.begin() as conn:
            confirmed = _insert(
                conn, "otra vez", "comprar leche", "duplicate_confirmed", 0.92, neighbor
            )
        assert confirmed != neighbor

    def test_different_text_is_unaffected(self, engine: Engine) -> None:
        with engine.begin() as conn:
            _insert(conn, "Comprar leche", "comprar leche")
            second = _insert(conn, "Comprar pan", "comprar pan")
        assert second is not None


class TestPersistenceChecks:
    """design.md's `phrases_metadata_paired` / `phrases_confirmed_has_neighbor` CHECKs."""

    @pytest.fixture
    def neighbor(self, engine: Engine) -> int:
        with engine.begin() as conn:
            return _insert(conn, "n", "n")

    @pytest.mark.parametrize(
        ("score", "with_neighbor", "status", "constraint_name"),
        [
            (0.5, False, "unique", "phrases_metadata_paired"),
            (None, True, "unique", "phrases_metadata_paired"),
            (None, False, "duplicate_confirmed", "phrases_confirmed_has_neighbor"),
        ],
        ids=["score_without_neighbor", "neighbor_without_score", "confirmed_without_neighbor"],
    )
    def test_check_constraint_rejects_unpaired_metadata(
        self,
        engine: Engine,
        neighbor: int,
        score: float | None,
        with_neighbor: bool,
        status: str,
        constraint_name: str,
    ) -> None:
        with pytest.raises(IntegrityError) as excinfo:
            with engine.begin() as conn:
                _insert(conn, "x", "x", status, score, neighbor if with_neighbor else None)
        assert constraint_name in str(excinfo.value.orig)

    def test_confirmed_status_with_valid_pair_is_accepted(
        self, engine: Engine, neighbor: int
    ) -> None:
        with engine.begin() as conn:
            confirmed = _insert(conn, "otra vez", "n", "duplicate_confirmed", 0.9, neighbor)
        assert confirmed != neighbor


class TestMigrationLifecycle:
    """specs/phrase-management/spec.md: "Migrations"."""

    def test_upgrade_from_empty_creates_table_and_extension(self, engine: Engine) -> None:
        # `_freshly_migrated_schema` already dropped everything and upgraded to head.
        with engine.begin() as conn:
            assert _schema_state(conn) == (True, True)

    def test_downgrade_to_base_drops_table_and_extension(
        self, engine: Engine, database_url: str
    ) -> None:
        command.downgrade(_alembic_config(database_url), "base")
        with engine.begin() as conn:
            assert _schema_state(conn) == (False, False)
