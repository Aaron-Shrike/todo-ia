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
os.environ.setdefault("DATABASE_URL", "postgresql+psycopg://todo_ia:todo_ia@localhost:5432/todo_ia")

from app.main import create_app  # noqa: E402 -- must follow the env var default above
from app.modules.phrases.adapters.pgvector_repository import PgVectorUnitOfWorkFactory
from app.modules.phrases.container import build_phrases_container
from app.modules.similarity.adapters.fake import FakeEmbedder
from app.modules.similarity.contracts import SimilarityPolicy
from app.platform.settings import Settings
from tests.contract_suite.vectors import PROBE

pytestmark = pytest.mark.integration

_API_ROOT = Path(__file__).resolve().parents[2]
_QUERY_TEXT = "query text"


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


def _client(engine: Engine) -> TestClient:
    settings = Settings(database_url=_database_url())
    app = create_app(settings)
    app.state.phrases = build_phrases_container(
        embedder=FakeEmbedder({_QUERY_TEXT: PROBE}),
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
