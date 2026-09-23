"""Pure-logic tests for `pgvector_repository.py`'s `deserialize_vector`
(Unit 7b fix-pass, task 2) -- grouped under `tests/integration/`, marked
`pytest.mark.integration`, and NOT actually dependent on a live Postgres
connection: `pgvector_repository.py` imports `sqlalchemy` at module level,
and this dev venv does not have `sqlalchemy` installed (confirmed via
`python -c "import sqlalchemy"` -> `ModuleNotFoundError`; same gap Unit 8's
apply-progress.md section first documented), so any test file importing
this module -- pure logic or not -- fails to COLLECT outside a
docker/sqlalchemy-capable session. Living in `tests/unit/` would break this
project's own standard safety-net command (`pytest tests/unit
tests/contract_suite tests/contract -m "not integration and not slow"`),
which excludes `tests/integration/` from the path list entirely (not just by
marker) for exactly this reason -- see `test_endpoints_pgvector.py`'s own
docstring precedent for the same class of environment constraint.

**Not executed in this session** (no `sqlalchemy` installed, no docker):
correctness verified only by careful reading -- `deserialize_vector` is the
literal, straightforward inverse of the already-integration-tested
`serialize_vector` (`test_find_matches.py`, `test_nearest_and_uow.py`), and
both tests below were written RED-first per Strict TDD (confirmed failing
with `ModuleNotFoundError: No module named 'sqlalchemy'` before
`deserialize_vector` existed -- the same failure this whole module hits
today, not a `list_recent`-shaped RED; see apply-progress.md's Unit 7b
fix-pass section for the full discussion of why a real RED/GREEN execution
was not possible here).
"""

from __future__ import annotations

import pytest

from app.modules.phrases.adapters.pgvector_repository import (
    deserialize_vector,
    serialize_vector,
)

pytestmark = pytest.mark.integration


def test_deserialize_vector_parses_the_bracketed_csv_text_form() -> None:
    assert deserialize_vector("[0.1,0.25,-0.3]") == (0.1, 0.25, -0.3)


def test_deserialize_vector_round_trips_through_serialize_vector() -> None:
    # Triangulation: a DIFFERENT vector than the hardcoded-looking one above,
    # driven through the real `serialize_vector` this time -- proves the two
    # functions are genuine inverses, not just individually plausible.
    original = (0.987654, -0.000123, 1.0, 0.0)
    assert deserialize_vector(serialize_vector(original)) == original
