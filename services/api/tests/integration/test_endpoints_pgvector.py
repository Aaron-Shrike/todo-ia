"""Integration contract tests for `POST /phrases` against REAL Postgres
(tasks.md 7.3): 201, then 409, then a concurrent-identical-save pair.
Real `create_app()` + `PgVectorUnitOfWorkFactory`, `FakeEmbedder` (the real
provider is Unit 8's job -- same precedent as `test_nearest_and_uow.py`).
Routes are plain `def` handlers, so FastAPI runs each in its own worker
thread (`run_in_threadpool`) -- concurrent calls genuinely race on the lock.
"""

from __future__ import annotations

import os
from collections.abc import Iterator
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import pytest
from alembic import command
from alembic.config import Config
from fastapi.testclient import TestClient
from sqlalchemy import Engine, create_engine, text

# `app.main` builds `Settings()` at IMPORT time (see `tests/contract/
# conftest.py`'s docstring). This is the only `tests/integration/*` module
# importing `app.main`, so it needs `DATABASE_URL` set before that import
# even without `tests/contract` collected first. Same real default every
# fixture below falls back to -- nothing fake to leak or clean up.
#
# Cross-reference (fix-pass, review finding #5): `tests/contract/conftest.py`
# ALSO sets `DATABASE_URL` at module scope (a fake `contract:contract`
# placeholder, cleaned up in its `pytest_collection_finish` hook), and the two
# mechanisms are unaware of each other -- their combined effect depends on
# pytest's collection order. Currently harmless: whichever file's import runs
# first via `os.environ.setdefault`/membership-check wins, both fallback
# values are legitimate for their own module, and `tests/contract/*` never
# reads `Settings.database_url` for real I/O (it always overrides `Settings`
# with its own `test:test@localhost` DSN in `_client()`, see
# `test_phrases_endpoints.py`). Fragile if that ever changes -- see
# `tests/contract/conftest.py`'s own cross-reference comment.
#
# The literal below is intentionally NOT hoisted into a shared module-level
# constant (fix-pass, review finding #4): a plain `NAME = "..."` assignment
# here would itself be a non-import statement ahead of every `app.*` import
# below, which ruff's E402 (module-level-import-not-at-top-of-file) check
# does NOT exempt the way it exempts this bare `os.environ.setdefault(...)`
# call (verified: `Expr` statements like this one are pycodestyle's
# documented `sys.path`-manipulation exception; plain assignments are not) --
# every import in this file would then need its own E402 suppression
# comment. Instead, `_database_url()` below reads `DATABASE_URL`
# unconditionally: this line has already guaranteed it is set by the time any
# fixture calls `_database_url()`, so a second copy of the fallback literal
# there was unreachable dead code, not a genuine second source of truth.
os.environ.setdefault("DATABASE_URL", "postgresql+psycopg://todo_ia:todo_ia@localhost:5432/todo_ia")

from app.main import create_app  # noqa: E402 -- must follow the env var default above
from app.modules.phrases.adapters.pgvector_repository import PgVectorUnitOfWorkFactory
from app.modules.phrases.container import build_phrases_container
from app.modules.similarity.adapters.fake import FakeEmbedder
from app.modules.similarity.contracts import SimilarityPolicy, Vector
from app.platform.settings import Settings
from tests.contract_suite.vectors import PROBE, orthogonal_vector

pytestmark = pytest.mark.integration

_API_ROOT = Path(__file__).resolve().parents[2]
_QUERY_TEXT = "query text"


def _database_url() -> str:
    # `os.environ.setdefault(...)` above already guarantees `DATABASE_URL` is
    # set by the time any fixture calls this -- no second fallback literal
    # needed here (fix-pass, review finding #4; see the comment above).
    base = os.environ["DATABASE_URL"]
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


def _client(engine: Engine, *, vectors: dict[str, Vector] | None = None) -> TestClient:
    settings = Settings(database_url=_database_url())
    app = create_app(settings)
    app.state.phrases = build_phrases_container(
        embedder=FakeEmbedder(vectors if vectors is not None else {_QUERY_TEXT: PROBE}),
        uow_factory=PgVectorUnitOfWorkFactory(engine),
        policy=SimilarityPolicy(threshold=settings.similarity_threshold),
        phrase_max_length=settings.phrase_max_length,
        matches_page_size=settings.matches_page_size,
    )
    return TestClient(app, raise_server_exceptions=False)


def test_post_phrases_returns_201_then_409_for_a_duplicate(engine: Engine) -> None:
    client = _client(engine)
    first = client.post("/phrases", json={"text": _QUERY_TEXT})
    assert first.status_code == 201
    assert first.json()["data"]["validation"]["status"] == "unique"
    second = client.post("/phrases", json={"text": _QUERY_TEXT})
    assert second.status_code == 409
    assert second.json()["error"]["code"] == "DUPLICATE_CONFIRMATION_REQUIRED"


def test_concurrent_identical_saves_yield_exactly_one_201_and_one_409(engine: Engine) -> None:
    client = _client(engine)
    with ThreadPoolExecutor(max_workers=2) as pool:
        futures = [
            pool.submit(client.post, "/phrases", json={"text": _QUERY_TEXT}) for _ in range(2)
        ]
        statuses = sorted(future.result().status_code for future in futures)
    assert statuses == [201, 409]
    with engine.connect() as conn:
        assert conn.execute(text("SELECT count(*) FROM phrases")).scalar_one() == 1


def test_get_phrases_returns_newest_first_against_real_postgres(engine: Engine) -> None:
    # Unit 7b fix-pass, task 2: the exact regression this test guards
    # against -- `PgVectorPhraseRepository` did not implement `list_recent`
    # (see apply-progress.md's Unit 7b "Discovered gap" note), so this
    # endpoint 500'd with an `AttributeError` against real Postgres despite
    # every contract test (against the in-memory adapter only) passing.
    #
    # Unit 14 finding: this test was written but, by the Unit 7b fix-pass's
    # own admission, never actually RUN before (no docker/Postgres in that
    # environment). It failed on its very first real execution -- not with
    # the `list_recent` bug it was written to catch, but one step earlier:
    # the module's shared `_client()` only pre-seeded `FakeEmbedder` with a
    # vector for `_QUERY_TEXT` ("query text"), so saving "first" raised
    # `KeyError` inside `FakeEmbedder.embed`, a test-fixture bug, not a
    # production one. Fixed by giving THIS test its own client with a
    # distinct, pairwise-orthogonal vector per phrase (see
    # `orthogonal_vector` in `tests/contract_suite/vectors.py`), so none of
    # the three saves is ever flagged a duplicate of another.
    phrases = ("first", "second", "third")
    client = _client(
        engine, vectors={text: orthogonal_vector(i) for i, text in enumerate(phrases)}
    )
    for phrase_text in phrases:
        response = client.post("/phrases", json={"text": phrase_text})
        assert response.status_code == 201
    response = client.get("/phrases")
    assert response.status_code == 200
    items = response.json()["data"]["items"]
    assert [item["text"] for item in items] == ["third", "second", "first"]
