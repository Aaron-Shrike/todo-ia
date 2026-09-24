"""Integration tests for the pgvector `find_matches` adapter (tasks.md
5a.2/5a.3). Runs against real Postgres + pgvector (`docker compose up -d db
migrate`). Registers `PgVectorPhraseRepository` against the shared
`MatchesContractSuite`; `NearestNeighbourContractSuite` registers pgvector
once Unit 5b builds the write-path primitives (apply-progress.md's Unit 5a
deviations has the split rationale). Adds pgvector-only guards: EXPLAIN
proves no HNSW scan / no `OFFSET`; `SET LOCAL` scoping does not leak; the
0.79996/0.79994 tail-rule boundary (widened SQL admits both, `_shared.
build_matches_page` keeps only the first); oracle agreement vs
`domain/cosine.py` within 1e-5.
"""

from __future__ import annotations

import math
import os
import random
from collections.abc import Iterator
from datetime import UTC, datetime
from pathlib import Path

import pytest
from alembic import command
from alembic.config import Config
from sqlalchemy import Engine, create_engine, text

from app.modules.phrases.adapters.pgvector_repository import (
    PgVectorPhraseRepository,
    PgVectorUnitOfWorkFactory,
    build_find_matches_query,
    serialize_vector,
)
from app.modules.phrases.application._shared import build_matches_page
from app.modules.phrases.contracts import NewPhrase, UnitOfWorkFactory, ValidationStatus
from app.modules.similarity.contracts import SimilarityPolicy, Vector, cosine_distance
from tests.contract_suite.repository_contract import MatchesContractSuite
from tests.contract_suite.vectors import PROBE, vector_at_distance

pytestmark = pytest.mark.integration

_API_ROOT = Path(__file__).resolve().parents[2]
_DIMENSIONS = 384


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
    """Same technique as `test_schema.py`: Alembic downgrade/upgrade, never
    a raw `DROP TABLE` (desyncs `alembic_version`)."""
    config = _alembic_config(database_url)
    command.downgrade(config, "base")
    command.upgrade(config, "head")
    yield


def _new_phrase(text_value: str, embedding: Vector) -> NewPhrase:
    return NewPhrase(
        text=text_value,
        normalized_text=text_value,
        embedding=embedding,
        similarity_score=None,
        most_similar_phrase_id=None,
        validation_status=ValidationStatus.UNIQUE,
        validated_at=datetime.now(UTC),
    )


class TestPgVectorMatchesContract(MatchesContractSuite):
    @pytest.fixture
    def uow_factory(self, engine: Engine) -> UnitOfWorkFactory:
        return PgVectorUnitOfWorkFactory(engine)


def test_count_matches_reports_the_full_count_independent_of_page_size(engine: Engine) -> None:
    policy = SimilarityPolicy(threshold=0.80)
    with engine.connect() as conn:
        repo = PgVectorPhraseRepository(conn)
        for i in range(5):
            # all above threshold
            repo.add(_new_phrase(f"m{i}", vector_at_distance(0.05 + i * 0.001)))
        repo.add(_new_phrase("far", vector_at_distance(1.5)))  # below threshold
        conn.commit()

        repo = PgVectorPhraseRepository(conn, read_only=True)
        total = repo.count_matches(PROBE, max_distance=policy.max_distance())
        page = repo.find_matches(PROBE, max_distance=policy.max_distance(), limit=2, cursor=None)
        conn.rollback()

    assert total == 5  # the orthogonal phrase is excluded, unaffected by `limit`
    assert len(page.items) == 2  # `limit` still bounds the page itself


def test_explain_shows_no_hnsw_and_no_offset_and_set_local_does_not_leak(engine: Engine) -> None:
    with engine.connect() as conn:
        rows = [
            {"t": f"row{i}", "e": serialize_vector(vector_at_distance(0.01 + i * 0.003))}
            for i in range(250)  # > hnsw.ef_search (200): a non-vacuous guard
        ]
        conn.execute(
            text(
                "INSERT INTO phrases (text, normalized_text, embedding, validation_status,"
                " validated_at) VALUES (:t, :t, :e, 'unique', now())"
            ),
            rows,
        )
        conn.execute(text("SELECT set_config('enable_indexscan', 'off', true)"))
        assert conn.execute(text("SHOW enable_indexscan")).scalar_one() == "off"
        query = build_find_matches_query(has_cursor=True)
        params = {"q": serialize_vector(PROBE), "max_distance": 1.0, "limit": 50}
        plan_rows = conn.execute(
            text("EXPLAIN " + query), {**params, "cursor_bucket": -1, "cursor_id": 0}
        ).fetchall()
        conn.commit()

    plan_text = "\n".join(row[0] for row in plan_rows)
    assert "hnsw" not in plan_text.lower()
    assert "OFFSET" not in plan_text
    # `is_local=true` must vanish at commit -- the next statement on a
    # pooled connection sees the session default again, never a leak.
    with engine.connect() as conn:
        assert conn.execute(text("SHOW enable_indexscan")).scalar_one() == "on"


def test_boundary_0_79996_in_0_79994_out_via_tail_rule(engine: Engine) -> None:
    # SQL is a deliberate superset: both fall inside the widened bound, but
    # only the 0.79996 row survives the exact threshold + tail rule.
    policy = SimilarityPolicy(threshold=0.80)
    distance_in = 1 - 0.79996  # rounds to 0.8000 -> included
    distance_out = 1 - 0.79994  # rounds to 0.7999 -> excluded
    with engine.connect() as conn:
        repo = PgVectorPhraseRepository(conn)
        id_in = repo.add(_new_phrase("in", vector_at_distance(distance_in))).id
        id_out = repo.add(_new_phrase("out", vector_at_distance(distance_out))).id
        conn.commit()

        repo = PgVectorPhraseRepository(conn, read_only=True)
        page = repo.find_matches(PROBE, max_distance=policy.max_distance(), limit=10, cursor=None)
        conn.rollback()

    assert {m.id for m in page.items} == {id_in, id_out}  # SQL admits both (widened bound)

    result = build_matches_page(page, policy, comparison="probe", total=len(page.items))
    assert [m.id for m in result.matches] == [id_in]  # tail rule stops at the first failing row
    assert result.has_more is False


def test_oracle_agreement_with_pure_python_cosine_within_1e5(engine: Engine) -> None:
    rng = random.Random(20260922)

    def _random_unit_vector() -> list[float]:
        raw = [rng.uniform(-1.0, 1.0) for _ in range(_DIMENSIONS)]
        norm = math.sqrt(sum(c * c for c in raw))
        return [c / norm for c in raw]

    query, *stored = [_random_unit_vector() for _ in range(6)]
    with engine.connect() as conn:
        repo = PgVectorPhraseRepository(conn)
        ids = [repo.add(_new_phrase(f"o{i}", vector)).id for i, vector in enumerate(stored)]
        conn.commit()

        repo = PgVectorPhraseRepository(conn, read_only=True)
        page = repo.find_matches(query, max_distance=2.0, limit=10, cursor=None)
        conn.rollback()

    by_id = dict(zip(ids, stored, strict=True))
    assert len(page.items) == 5
    for match in page.items:
        expected = cosine_distance(query, by_id[match.id])
        assert abs(match.distance - expected) < 1e-5
