"""Integration tests for the pgvector write-path primitives (tasks.md
5b.1-5b.3): `find_nearest` (HNSW top-1), `find_nearest_exact` (exact,
write path), `UnitOfWork` isolation, the advisory lock and the `23505` ->
`DuplicateTextConflict` mapping. Registers pgvector against
`NearestNeighbourContractSuite`, completing the composed suite for
pgvector (5a registered `MatchesContractSuite` only).

The barrier-snapshot tests (REPEATABLE READ vs READ COMMITTED under a
concurrent commit) ship in a follow-up commit on this branch -- tasks.md
5b's pre-authorized seam for a budget overrun.
"""

from __future__ import annotations

import math
import os
import random
import threading
from collections.abc import Iterator
from pathlib import Path

import pytest
from alembic import command
from alembic.config import Config
from sqlalchemy import Connection, Engine, create_engine, text

from app.modules.phrases.adapters.pgvector_repository import (
    FIND_NEAREST_EXACT_QUERY,
    FIND_NEAREST_QUERY,
    PgVectorPhraseRepository,
    PgVectorUnitOfWork,
    PgVectorUnitOfWorkFactory,
    serialize_vector,
)
from app.modules.phrases.application.save_phrase import SavePhrase, SaveResult
from app.modules.phrases.contracts import (
    Isolation,
    LockTimeout,
    Neighbor,
    UnitOfWorkFactory,
    ValidationStatus,
)
from app.modules.similarity.adapters.fake import FakeEmbedder
from app.modules.similarity.contracts import SimilarityPolicy, Vector, cosine_distance
from tests.contract_suite.repository_contract import NearestNeighbourContractSuite
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
    # Same technique as test_schema.py/test_find_matches.py (Alembic
    # downgrade/upgrade, never a raw DROP TABLE) -- also the "truncate
    # fixture between tests" the advisory-lock tests need.
    config = _alembic_config(database_url)
    command.downgrade(config, "base")
    command.upgrade(config, "head")
    yield


def _random_unit_vector(rng: random.Random, dim: int = _DIMENSIONS) -> list[float]:
    raw = [rng.uniform(-1.0, 1.0) for _ in range(dim)]
    norm = math.sqrt(sum(c * c for c in raw))
    return [c / norm for c in raw]


def _seed_raw(engine: Engine, texts_and_vectors: list[tuple[str, Vector]]) -> None:
    rows = [{"t": t, "e": serialize_vector(v)} for t, v in texts_and_vectors]
    with engine.connect() as conn:
        conn.execute(
            text(
                "INSERT INTO phrases (text, normalized_text, embedding, validation_status,"
                " validated_at) VALUES (:t, :t, :e, 'unique', now())"
            ),
            rows,
        )
        conn.commit()


class TestPgVectorNearestNeighbourContract(NearestNeighbourContractSuite):
    @pytest.fixture
    def uow_factory(self, engine: Engine) -> UnitOfWorkFactory:
        return PgVectorUnitOfWorkFactory(engine)


# --- Guard 1: non-vacuous recall (find_nearest agrees with the exact scan
# over hundreds of queries on a corpus larger than the default ef_search).

def test_hnsw_recall_agrees_with_exact_scan_over_hundreds_of_queries(engine: Engine) -> None:
    rng = random.Random(20260922)
    _seed_raw(engine, [(f"row{i}", _random_unit_vector(rng)) for i in range(1000)])
    queries = [_random_unit_vector(rng) for _ in range(300)]

    mismatches = []
    with engine.connect() as conn:
        for q in queries:
            conn.execute(text("SELECT set_config('enable_seqscan', 'off', true)"))
            hnsw = PgVectorPhraseRepository(conn).find_nearest(q)
            exact = PgVectorPhraseRepository(conn).find_nearest_exact(q)
            conn.rollback()
            if hnsw is None or exact is None or hnsw.id != exact.id:
                mismatches.append((hnsw, exact))
    assert mismatches == []


# --- Guard 2: EXPLAIN shows find_nearest hits the HNSW index (forced with
# enable_seqscan=off, no full-table Sort); find_nearest_exact never does,
# even primed the same way first.

def _explain(conn: Connection, query: str, params: dict[str, object]) -> str:
    rows = conn.execute(text("EXPLAIN " + query), params).fetchall()
    return "\n".join(row[0] for row in rows)


def test_explain_shows_find_nearest_uses_hnsw_and_find_nearest_exact_never_does(
    engine: Engine,
) -> None:
    rng = random.Random(1)
    _seed_raw(engine, [(f"e{i}", _random_unit_vector(rng)) for i in range(1000)])
    q = serialize_vector(_random_unit_vector(rng))
    with engine.connect() as conn:
        conn.execute(text("SELECT set_config('enable_seqscan', 'off', true)"))  # forces both arms
        conn.execute(text("SELECT set_config('enable_indexscan', 'on', true)"))
        conn.execute(text("SELECT set_config('hnsw.ef_search', '200', true)"))
        hnsw_plan = _explain(conn, FIND_NEAREST_QUERY, {"q": q, "k": 10})
        exact_plan = _explain(conn, FIND_NEAREST_EXACT_QUERY, {"q": q})
        conn.rollback()
    assert "index scan using phrases_embedding_hnsw_idx" in hnsw_plan.lower()
    assert "seq scan" not in hnsw_plan.lower()
    assert "hnsw" not in exact_plan.lower()  # exact re-sets enable_indexscan=off itself


# --- Guard 2b: save never issues find_nearest, on 201 or 409, proven via a
# statement-counting spy wrapped around the real pgvector UnitOfWork.

def _spy_uow_factory(engine: Engine) -> tuple[UnitOfWorkFactory, dict[str, int]]:
    calls = {"find_nearest": 0}

    class _SpyRepo:
        def __init__(self, inner: PgVectorPhraseRepository) -> None:
            self._inner = inner

        def __getattr__(self, name: str) -> object:
            return getattr(self._inner, name)

        def find_nearest(self, q: Vector) -> object:
            calls["find_nearest"] += 1
            return self._inner.find_nearest(q)

    class _SpyUnitOfWork(PgVectorUnitOfWork):
        def __enter__(self) -> _SpyUnitOfWork:
            super().__enter__()
            self.repo = _SpyRepo(self.repo)  # type: ignore[assignment]
            return self

    def factory(
        *, isolation: Isolation = Isolation.READ_COMMITTED, read_only: bool = False
    ) -> _SpyUnitOfWork:
        return _SpyUnitOfWork(engine, isolation=isolation, read_only=read_only)

    return factory, calls


def test_save_never_issues_find_nearest_on_201_or_409(engine: Engine) -> None:
    uow_factory, calls = _spy_uow_factory(engine)
    embedder = FakeEmbedder({"first save": PROBE, "second save": PROBE})
    policy = SimilarityPolicy(threshold=0.80)
    save = SavePhrase(uow_factory, embedder, policy, phrase_max_length=280, default_page_size=50)
    first = save("first save")
    second = save("second save")  # same vector -> duplicate, unconfirmed -> 409
    assert first.phrase is not None
    assert second.conflict is not None and second.conflict.is_duplicate is True
    assert calls["find_nearest"] == 0


# --- Guard 2b continued: a tiny ef_search makes HNSW miss a stored near-
# identical phrase (control, forced via enable_seqscan=off); the exact scan
# -- and therefore SavePhrase, which never reads ef_search -- still finds
# it and answers 409, not 201. HNSW's own layer-assignment randomness is
# Postgres-internal (independent of our Python seed), so any ONE corpus
# build only misses with high (empirically ~80-100%), not guaranteed,
# probability; retried across a few independent builds below rather than
# pinned to one seed that could occasionally flake (apply-progress.md's
# Unit 5b section has the full empirical reliability measurement).

def _adversarial_recall_miss_corpus(engine: Engine, rng: random.Random) -> Vector:
    with engine.connect() as conn:
        conn.execute(text("TRUNCATE phrases RESTART IDENTITY"))
        conn.commit()
    query = _random_unit_vector(rng)

    def _perturbed(base: Vector, eps: float) -> Vector:
        out = [c + rng.uniform(-eps, eps) for c in base]
        norm = math.sqrt(sum(c * c for c in out))
        return [c / norm for c in out]

    target = _perturbed(query, 0.35)
    rows = [(f"filler{i}", _random_unit_vector(rng)) for i in range(3000)]
    confuser_center = _perturbed(query, 0.315)
    rows += [(f"confuser{i}", _perturbed(confuser_center, 0.02)) for i in range(80)]
    rows.append(("target", target))
    _seed_raw(engine, rows)
    return query


def _find_a_genuine_recall_miss(
    engine: Engine, attempts: int = 8
) -> tuple[Vector, Neighbor | None]:
    for seed in range(attempts):
        query = _adversarial_recall_miss_corpus(engine, random.Random(seed))
        with engine.connect() as conn:
            conn.execute(text("SELECT set_config('enable_seqscan', 'off', true)"))
            hnsw = PgVectorPhraseRepository(conn, ef_search=1).find_nearest(query)
            exact = PgVectorPhraseRepository(conn).find_nearest_exact(query)
            conn.rollback()
        assert exact is not None and exact.text == "target"  # the corpus itself is always sound
        if hnsw is None or hnsw.text != "target":
            return query, hnsw
    pytest.fail(f"HNSW found the target on all {attempts} independent corpus builds")


def test_recall_miss_hnsw_alone_is_wrong_but_save_still_answers_409(engine: Engine) -> None:
    query, hnsw = _find_a_genuine_recall_miss(engine)
    assert hnsw is None or hnsw.text != "target"  # control: HNSW alone is wrong

    uow_factory = PgVectorUnitOfWorkFactory(engine)
    embedder = FakeEmbedder({"near duplicate save": query})
    policy = SimilarityPolicy(threshold=0.10)
    save = SavePhrase(uow_factory, embedder, policy, phrase_max_length=280, default_page_size=50)
    result = save("near duplicate save")
    assert result.phrase is None
    assert result.conflict is not None and result.conflict.is_duplicate is True


# --- Oracle: same 1e-5 tolerance/rationale as Unit 5a's find_matches oracle.

def test_find_nearest_exact_agrees_with_the_pure_python_oracle_within_1e5(engine: Engine) -> None:
    rng = random.Random(3)
    query, *stored = [_random_unit_vector(rng) for _ in range(6)]
    _seed_raw(engine, [(f"o{i}", v) for i, v in enumerate(stored)])
    with engine.connect() as conn:
        neighbor = PgVectorPhraseRepository(conn).find_nearest_exact(query)
        conn.rollback()
    assert neighbor is not None
    expected = min(cosine_distance(query, v) for v in stored)
    assert abs(neighbor.distance - expected) < 1e-5


# --- Concurrency: advisory lock across two REAL connections.

def _hold_lock_in_background(
    engine: Engine, *, release: threading.Event, rollback: bool = False
) -> tuple[threading.Event, threading.Event]:
    acquired = threading.Event()
    released = threading.Event()

    def hold() -> None:
        with engine.connect() as conn:
            PgVectorPhraseRepository(conn).lock_for_write()
            acquired.set()
            release.wait()
            conn.rollback() if rollback else conn.commit()
            released.set()

    threading.Thread(target=hold, daemon=True).start()
    acquired.wait(timeout=5)
    return acquired, released


def test_advisory_lock_serializes_two_real_connections(engine: Engine) -> None:
    release = threading.Event()
    _hold_lock_in_background(engine, release=release)
    order: list[str] = []

    def second() -> None:
        with engine.connect() as conn:
            PgVectorPhraseRepository(conn).lock_for_write()  # blocks until release()
            order.append("second-acquired")
            conn.rollback()

    t2 = threading.Thread(target=second)
    t2.start()
    order.append("about-to-release")
    release.set()
    t2.join(timeout=5)
    assert order == ["about-to-release", "second-acquired"]


def test_lock_timeout_produces_an_error_with_nothing_persisted(engine: Engine) -> None:
    release = threading.Event()
    _hold_lock_in_background(engine, release=release)
    try:
        with engine.connect() as conn:
            with pytest.raises(LockTimeout):
                PgVectorPhraseRepository(conn, lock_timeout_ms=50).lock_for_write()
            conn.rollback()
    finally:
        release.set()
    with engine.connect() as conn:
        count = conn.execute(text("SELECT count(*) FROM phrases")).scalar_one()
        conn.rollback()
    assert count == 0


def test_lock_released_after_the_holder_rolls_back_on_failure(engine: Engine) -> None:
    release = threading.Event()
    _, released = _hold_lock_in_background(engine, release=release, rollback=True)
    release.set()
    assert released.wait(timeout=5)
    with engine.connect() as conn:
        PgVectorPhraseRepository(conn, lock_timeout_ms=200).lock_for_write()  # must not raise
        conn.rollback()


def _concurrent_saves(
    engine: Engine,
    embedder: FakeEmbedder,
    texts: tuple[str, str],
    *,
    confirm_duplicate: bool = False,
) -> tuple[SaveResult, SaveResult]:
    uow_factory = PgVectorUnitOfWorkFactory(engine)
    policy = SimilarityPolicy(threshold=0.80)
    results: dict[int, SaveResult] = {}

    def save_at(i: int) -> None:
        save = SavePhrase(
            uow_factory, embedder, policy, phrase_max_length=280, default_page_size=50
        )
        results[i] = save(texts[i], confirm_duplicate=confirm_duplicate)

    threads = [threading.Thread(target=save_at, args=(i,)) for i in range(2)]
    for t in threads:
        t.start()
    for t in threads:
        t.join(timeout=10)
    return results[0], results[1]


@pytest.mark.parametrize(
    ("texts", "vectors"),
    [
        (("same text", "same text"), {"same text": PROBE}),
        (
            ("similar one", "similar two"),
            {"similar one": PROBE, "similar two": vector_at_distance(0.05)},
        ),
    ],
    ids=["identical", "similar-but-distinct"],
)
def test_concurrent_unconfirmed_saves_yield_exactly_one_201(
    engine: Engine, texts: tuple[str, str], vectors: dict[str, Vector]
) -> None:
    results = _concurrent_saves(engine, FakeEmbedder(vectors), texts)
    successes = [r for r in results if r.phrase is not None]
    conflicts = [r for r in results if r.conflict is not None]
    assert len(successes) == 1
    assert len(conflicts) == 1


def test_concurrent_confirmed_saves_of_near_duplicate_texts_both_succeed(engine: Engine) -> None:
    embedder = FakeEmbedder({"confirmed alpha": PROBE, "confirmed beta": vector_at_distance(0.05)})
    results = _concurrent_saves(
        engine, embedder, ("confirmed alpha", "confirmed beta"), confirm_duplicate=True
    )
    assert all(r.phrase is not None for r in results)
    statuses = {r.phrase.validation_status for r in results}  # type: ignore[union-attr]
    assert statuses == {ValidationStatus.UNIQUE, ValidationStatus.DUPLICATE_CONFIRMED}


# --- Barrier snapshot: two threading.Event + after_statement, no sleeps
# (design.md's deterministic technique). REPEATABLE READ fixes one snapshot
# for find_nearest + find_matches; a READ COMMITTED control shows the
# divergence, proving the test can fail.

def _barrier_validate(
    engine: Engine, isolation: Isolation, closer_text: str
) -> tuple[object, object]:
    paused, resume = threading.Event(), threading.Event()

    def hook(n: int) -> None:
        if n == 1:
            paused.set()
            resume.wait()

    uow_factory = PgVectorUnitOfWorkFactory(engine, after_statement=hook)
    outcome: dict[str, object] = {}

    def run() -> None:
        with uow_factory(isolation=isolation, read_only=True) as uow:
            outcome["neighbor"] = uow.repo.find_nearest(PROBE)
            outcome["page"] = uow.repo.find_matches(PROBE, max_distance=2.0, limit=10, cursor=None)

    t = threading.Thread(target=run)
    t.start()
    paused.wait(timeout=5)
    _seed_raw(engine, [(closer_text, PROBE)])  # committed by a second, real connection
    resume.set()
    t.join(timeout=5)
    return outcome["neighbor"], outcome["page"]


def test_repeatable_read_snapshot_survives_a_concurrent_commit(engine: Engine) -> None:
    _seed_raw(engine, [("original", vector_at_distance(0.5))])
    neighbor, page = _barrier_validate(engine, Isolation.REPEATABLE_READ, "new_closer")
    assert neighbor.text == "original"  # type: ignore[union-attr]
    assert all(m.text != "new_closer" for m in page.items)  # type: ignore[union-attr]


def test_read_committed_control_sees_the_concurrent_commit(engine: Engine) -> None:
    _seed_raw(engine, [("original", vector_at_distance(0.5))])
    _, page = _barrier_validate(engine, Isolation.READ_COMMITTED, "new_closer")
    assert any(m.text == "new_closer" for m in page.items)  # type: ignore[union-attr]
