"""Unit tests for `platform/embedding_boot.py` (tasks.md 8.2, design.md
"Dimension coherence check at startup": "read the column typmod and compare
against `provider.dimensions` and `EMBEDDING_DIMENSIONS`; mismatch aborts
boot"). `check_dimension_coherence` is a PURE comparison over three
already-gathered integers, so it is fully unit-testable without a live
database -- `read_vector_column_dimensions` and `check_database_reachable`
(the actual `pg_attribute`/`SELECT 1` queries) are thin, no-branching SQL
calls and are NOT exercised here: no Postgres instance is available in this
environment (`sqlalchemy` itself is not even installed in this dev venv --
see apply-progress.md's Unit 8 section), same category of gap as Unit 4's
deferred typmod-reader test.
"""

from __future__ import annotations

import pytest

from app.platform.embedding_boot import EmbeddingDimensionMismatch, check_dimension_coherence

pytestmark = pytest.mark.unit


def test_three_agreeing_dimensions_pass_silently() -> None:
    check_dimension_coherence(typmod=384, provider_dimensions=384, configured_dimensions=384)


@pytest.mark.parametrize(
    ("typmod", "provider_dimensions", "configured_dimensions"),
    [
        (768, 384, 384),  # column was created for a different model
        (384, 768, 384),  # provider dimension drifted from the column
        (384, 384, 768),  # EMBEDDING_DIMENSIONS misconfigured against both
        # Reliability suggestion #12: two fields disagree AT ONCE (not just
        # one) -- typmod and provider agree with each other but NOT with
        # the configured value, a boundary case the single-field cases above
        # never exercise.
        (768, 768, 384),
    ],
)
def test_any_single_disagreement_raises(
    typmod: int, provider_dimensions: int, configured_dimensions: int
) -> None:
    with pytest.raises(EmbeddingDimensionMismatch) as excinfo:
        check_dimension_coherence(
            typmod=typmod,
            provider_dimensions=provider_dimensions,
            configured_dimensions=configured_dimensions,
        )
    assert excinfo.value.typmod == typmod
    assert excinfo.value.provider_dimensions == provider_dimensions
    assert excinfo.value.configured_dimensions == configured_dimensions
