"""Unit test for `main.py`'s Unit 8 addition: `create_app` gains an
OPTIONAL `lifespan` parameter, defaulting to `None` so every existing test
(which calls `create_app(settings)` with no lifespan and sets `app.state.
phrases`/`app.state.health` directly -- see `test_validate_health.py`'s
`_client()`, unchanged) keeps behaving identically. This test only proves
the passthrough wiring -- it never EXECUTES a lifespan (no live database or
real model is available in this environment; the production `_lifespan`
orchestration itself is documented, not exercised, in apply-progress.md's
Unit 8 section)."""

from __future__ import annotations

import os

# `app.main` builds a module-level `Settings()` (no default for
# `DATABASE_URL`) at IMPORT time. `tests/contract/conftest.py` supplies a
# placeholder for every test collected under `tests/contract/`, but this
# file is the first module under `tests/unit/` to import `app.main` in
# isolation (running it alone, rather than as part of the full suite where
# `tests/contract`'s conftest already ran) -- same defensive fix as
# `tests/integration/test_endpoints_pgvector.py`'s own cross-referenced
# note (apply-progress.md's Unit 7 section): a real-looking default via
# `setdefault`, not a placeholder needing cleanup.
os.environ.setdefault("DATABASE_URL", "postgresql+psycopg://test:test@localhost:5432/test")

from collections.abc import AsyncIterator  # noqa: E402
from contextlib import asynccontextmanager  # noqa: E402

import pytest  # noqa: E402
from fastapi import FastAPI  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402

from app.main import create_app  # noqa: E402
from app.platform.settings import Settings  # noqa: E402

pytestmark = pytest.mark.unit

_DATABASE_URL = "postgresql+psycopg://test:test@localhost:5432/test"


def test_create_app_with_no_lifespan_behaves_exactly_as_before() -> None:
    app = create_app(Settings(database_url=_DATABASE_URL))

    assert app.state.health.model_ready is False  # unchanged Unit 6b default


def test_create_app_actually_runs_a_provided_lifespan_on_startup() -> None:
    # A behavioural check, not an identity check on FastAPI's internal
    # `lifespan_context` (Starlette wraps it in its own `merged_lifespan`
    # closure -- an implementation detail, not something to couple a test
    # to): the fake lifespan flips a flag on `app.state`, and `TestClient`
    # used as a context manager is what actually TRIGGERS a FastAPI
    # lifespan (a bare `TestClient(app)` call, used everywhere else in this
    # codebase, does NOT -- which is exactly why production's real
    # `_lifespan` never runs during any existing test).
    @asynccontextmanager
    async def _fake_lifespan(app: FastAPI) -> AsyncIterator[None]:
        app.state.fake_lifespan_ran = True
        yield

    app = create_app(Settings(database_url=_DATABASE_URL), lifespan=_fake_lifespan)
    assert not hasattr(app.state, "fake_lifespan_ran")  # not yet -- lifespan hasn't started

    with TestClient(app):
        assert app.state.fake_lifespan_ran is True
