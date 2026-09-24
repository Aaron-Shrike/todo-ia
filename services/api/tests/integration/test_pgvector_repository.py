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

The original `deserialize_vector` tests were **not executed** in the Unit
7b fix-pass session (no `sqlalchemy` installed, no docker) -- see
apply-progress.md's Unit 7b fix-pass section. Unit 1 (`phrase-list-filters`)
re-synced this venv (`pip install -e ".[dev]"`) so `sqlalchemy` IS
installed here, and the whole file, including the `_status_predicate`/
`_contains_pattern`/`build_list_page_query`/`build_count_list_query` SQL-
shape additions below, runs and was RED-then-GREEN'd for real in that
session -- still no live Postgres needed, still marked `integration` only
by this module's own long-standing convention (grouped with its sibling
DB-dependent files, not because these particular tests need a database).
"""

from __future__ import annotations

import pytest

from app.modules.phrases.adapters.pgvector_repository import (
    _contains_pattern,
    _status_predicate,
    build_count_list_query,
    build_list_page_query,
    deserialize_vector,
    serialize_vector,
)
from app.modules.phrases.contracts import ValidationStatus

pytestmark = pytest.mark.integration


def test_deserialize_vector_parses_the_bracketed_csv_text_form() -> None:
    assert deserialize_vector("[0.1,0.25,-0.3]") == (0.1, 0.25, -0.3)


def test_deserialize_vector_round_trips_through_serialize_vector() -> None:
    # Triangulation: a DIFFERENT vector than the hardcoded-looking one above,
    # driven through the real `serialize_vector` this time -- proves the two
    # functions are genuine inverses, not just individually plausible.
    original = (0.987654, -0.000123, 1.0, 0.0)
    assert deserialize_vector(serialize_vector(original)) == original


# --- Unit 1, task 1.3: pure SQL-shape tests for the filter builders -------
# design.md D4: the status value is an inlined SQL LITERAL, never bound as
# `:status` -- these tests prove the exact rendered text, since that's the
# whole point of the decision (a bound param would defeat the partial
# index under a generic plan; see Unit 2's EXPLAIN guard for the DB-level
# proof, not expressible here without a live Postgres connection).


def test_status_predicate_inlines_the_enum_value_as_a_sql_literal() -> None:
    assert (
        _status_predicate(ValidationStatus.DUPLICATE_CONFIRMED)
        == "validation_status = 'duplicate_confirmed'"
    )
    assert _status_predicate(ValidationStatus.UNIQUE) == "validation_status = 'unique'"


def test_contains_pattern_escapes_backslash_percent_and_underscore() -> None:
    # Backslash first, so escaping `%`/`_` doesn't double-escape their own
    # backslashes.
    assert _contains_pattern("leche") == "%leche%"
    assert _contains_pattern("100%") == "%100\\%%"
    assert _contains_pattern("under_score") == "%under\\_score%"
    assert _contains_pattern("back\\slash") == "%back\\\\slash%"
    assert _contains_pattern("%_\\") == "%\\%\\_\\\\%"


def test_build_list_page_query_with_no_filters_and_no_cursor_is_byte_identical_to_today() -> None:
    # design.md: "With no filters and no cursor, the output is byte-
    # identical to today's query, so there is no plan regression on the
    # default path." Pinned against the literal pre-Unit-1 rendering.
    unfiltered_default = (
        "\nSELECT id, text, normalized_text, embedding::text AS embedding, similarity_score,\n"
        "       most_similar_phrase_id, validation_status, validated_at, created_at\n"
        "FROM phrases\n"
        "\nORDER BY created_at DESC, id DESC\n"
        "LIMIT :limit + 1\n"
    )
    assert build_list_page_query(has_cursor=False) == unfiltered_default


def test_build_list_page_query_renders_every_filter_plus_a_cursor() -> None:
    # design.md's own rendered sample, verbatim.
    query = build_list_page_query(
        has_cursor=True,
        status=ValidationStatus.DUPLICATE_CONFIRMED,
        has_text=True,
        has_min_score=True,
    )
    assert "WHERE validation_status = 'duplicate_confirmed'" in query
    assert "  AND normalized_text LIKE :text_pattern ESCAPE '\\'" in query
    assert "  AND similarity_score >= :min_score" in query
    assert "  AND (created_at, id) < (:cursor_created_at, :cursor_id)" in query
    assert "ORDER BY created_at DESC, id DESC" in query
    assert "LIMIT :limit + 1" in query
    # Fragment order matters (status, text, min_score, cursor -- design.md's
    # `_list_where`), and each `AND` must precede the next fragment's start.
    assert query.index("validation_status") < query.index("normalized_text LIKE")
    assert query.index("normalized_text LIKE") < query.index("similarity_score >=")
    assert query.index("similarity_score >=") < query.index("(created_at, id) <")


def test_build_list_page_query_omits_where_when_nothing_applies() -> None:
    query = build_list_page_query(
        has_cursor=False, status=None, has_text=False, has_min_score=False
    )
    assert "WHERE" not in query


def test_build_count_list_query_shares_the_same_where_fragments_as_list_page() -> None:
    count_query = build_count_list_query(
        status=ValidationStatus.DUPLICATE_CONFIRMED, has_text=True, has_min_score=True
    )
    assert count_query.startswith("SELECT count(*) FROM phrases")
    assert "WHERE validation_status = 'duplicate_confirmed'" in count_query
    assert "  AND normalized_text LIKE :text_pattern ESCAPE '\\'" in count_query
    assert "  AND similarity_score >= :min_score" in count_query
    # No cursor/order/limit -- this is a count, not a page.
    assert "cursor" not in count_query
    assert "ORDER BY" not in count_query
    assert "LIMIT" not in count_query


def test_build_count_list_query_with_no_filters_has_no_where_clause() -> None:
    assert build_count_list_query() == "SELECT count(*) FROM phrases\n"
