"""Pure SEQUENCING core of the production boot flow (Unit 8 fix-pass,
reliability CRITICAL finding #2: `main.py::_lifespan`'s ordering had zero
test coverage because it mixed pure sequencing decisions with concrete I/O
-- real `create_engine`, real `PgVectorUnitOfWorkFactory` -- in one function
body with lazy inline imports, which made even the ORDER untestable with
fakes: importing `app.main` at all needs `sqlalchemy` installed (confirmed
absent in this dev venv).

This module has no such dependency. `run_boot_sequence` takes every I/O step
as an INJECTED callable, so the documented order -- load the model, check
dimensions (a mismatch short-circuits everything after it), warm up, build
the container/flip health -- is fully unit-tested (`tests/unit/platform/
test_boot_sequence.py`) with plain fakes, no sqlalchemy/postgres/torch
required. `main.py::_lifespan` is the thin wrapper that supplies the REAL
callables to this function; the real sqlalchemy/postgres calls THEMSELVES
remain genuinely untested here -- no docker/live Postgres is available in
this environment, a gap that stays documented rather than faked into false
confidence (see apply-progress.md's Unit 8 section).
"""

from __future__ import annotations

from collections.abc import Callable
from typing import TypeVar

_Provider = TypeVar("_Provider")
_Container = TypeVar("_Container")


def run_boot_sequence(
    *,
    load_model: Callable[[], _Provider],
    check_dimensions: Callable[[_Provider], None],
    warmup: Callable[[_Provider], None],
    build_container: Callable[[_Provider], _Container],
) -> _Container:
    """Runs the four boot steps in the documented order and returns
    whatever `build_container` returns. `check_dimensions` raising (in
    production: `EmbeddingDimensionMismatch`) propagates out of this
    function BEFORE `warmup`/`build_container` are ever called -- that
    short-circuit IS the sequencing invariant this function exists to
    guarantee, proved directly under test rather than only documented in a
    docstring."""
    provider = load_model()
    check_dimensions(provider)
    warmup(provider)
    return build_container(provider)
