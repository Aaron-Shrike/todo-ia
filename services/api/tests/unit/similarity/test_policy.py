"""Unit tests for `SimilarityPolicy` (tasks.md Unit 1 / 1.2), tables from
`specs/semantic-validation/spec.md`'s Cosine similarity / Threshold decision
scenarios. `.score`/`.includes` take a raw DISTANCE (`distance = 1 - cosine`,
D13), so each row converts the spec's "raw cosine" to a distance first.
`in_matches` is the same `includes()` decision `find_matches` applies.
"""

import pytest

from app.modules.similarity.domain.policy import ROUNDING_UNIT, SimilarityPolicy


def _distance_from_cosine(raw_cosine: float) -> float:
    return 1.0 - raw_cosine


@pytest.mark.parametrize(
    ("raw_cosine", "expected_score", "expected_is_duplicate"),
    [
        (0.79996, 0.8000, True),  # Rounding consistency (spec); t=0.80 inclusive
        (0.79994, 0.7999, False),  # just below t - eps
        (-0.3, 0.0, False),  # Negative cosine is clamped (spec)
        (1.0000000002, 1.0, True),  # Float overshoot is clamped (spec)
    ],
)
def test_score_and_includes_at_default_threshold(
    raw_cosine: float, expected_score: float, expected_is_duplicate: bool
) -> None:
    policy = SimilarityPolicy(threshold=0.80)
    distance = _distance_from_cosine(raw_cosine)
    assert policy.score(distance) == expected_score
    assert policy.includes(distance) is expected_is_duplicate


@pytest.mark.parametrize(
    ("raw_cosine", "expected_is_duplicate"),
    [
        (0.7999, False),  # t - eps
        (0.8000, True),  # exactly t (inclusive)
        (0.8001, True),  # t + eps
    ],
)
def test_threshold_boundary_inclusive(raw_cosine: float, expected_is_duplicate: bool) -> None:
    policy = SimilarityPolicy(threshold=0.80)
    assert policy.includes(_distance_from_cosine(raw_cosine)) is expected_is_duplicate


def test_threshold_zero_admits_everything() -> None:
    # Clamped scores are never negative, so a zero threshold admits every
    # stored phrase, even one whose raw cosine was negative (score 0.0).
    policy = SimilarityPolicy(threshold=0.0)
    assert policy.includes(_distance_from_cosine(-0.3)) is True


@pytest.mark.parametrize(
    ("raw_cosine", "expected_is_duplicate"),
    [
        (0.79996, False),  # score 0.8000 < threshold 0.80005
        (0.80006, True),  # score 0.8001 >= threshold 0.80005
    ],
)
def test_threshold_with_more_than_four_decimals(
    raw_cosine: float, expected_is_duplicate: bool
) -> None:
    # A naive binary-float comparison of 0.8000 >= 0.80005 can misbehave;
    # SimilarityPolicy compares Decimal(str(x)) to stay exact.
    policy = SimilarityPolicy(threshold=0.80005)
    assert policy.includes(_distance_from_cosine(raw_cosine)) is expected_is_duplicate


def test_max_distance_widened_bound_and_threshold_zero_special_case() -> None:
    # 1 - 0.80 + ROUNDING_UNIT = 0.2001; threshold 0 -> 2.0 (full raw-distance
    # range), since a clamped score of 0 admits every stored phrase.
    assert SimilarityPolicy(threshold=0.80).max_distance() == pytest.approx(
        1.0 - 0.80 + ROUNDING_UNIT
    )
    assert SimilarityPolicy(threshold=0.0).max_distance() == 2.0
