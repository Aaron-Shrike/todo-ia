"""ES/EN calibration: scores `tests/fixtures/calibration.yaml` against the
REAL sentence-transformers model (Unit 9.1/9.2; design.md "ES/EN calibration
fixture"; specs/semantic-validation/spec.md "Cross-language calibration").

Running this file (`make evidence`, i.e. `pytest tests/slow/test_calibration
.py -q`) regenerates `docs/evidence/calibration.md` -- the brief's Hugging
Face integration evidence deliverable -- including the task 9.2 cased-vs-
casefolded margin measurement. A MANUAL evidence step, never part of CI;
excluded from `make test-unit` by the `slow` marker (same as Unit 8's
`test_sentence_transformers.py` real-model test).

NOT executed in this apply batch: `pip install torch==2.14.0` (the pinned
version) fails here -- PyTorch publishes no macOS x86_64 wheel for ANY
recent release (checked 2.6.0-2.14.0 on PyPI; arm64-only), and this venv is
`macosx-14.0-x86_64`. Network (PyPI, huggingface.co) and disk were NOT the
blocker (both confirmed fine) -- see apply-progress.md's Unit 9 section for
the full transcript. Written so an Apple-Silicon/Linux/docker session can
run it as-is.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path

import pytest
import yaml

from app.modules.phrases.domain.normalization import comparison_form, display_form
from app.modules.similarity.adapters.sentence_transformers import (
    SentenceTransformersEmbedder,
    load_sentence_transformer,
)
from app.modules.similarity.domain.cosine import cosine_distance, cosine_similarity
from app.modules.similarity.domain.policy import SimilarityPolicy
from app.platform.settings import Settings

FIXTURE_PATH = Path(__file__).resolve().parent.parent / "fixtures" / "calibration.yaml"
# tests/slow/test_calibration.py -> tests -> api -> services -> repo root.
EVIDENCE_PATH = Path(__file__).resolve().parents[4] / "docs" / "evidence" / "calibration.md"

# Required: `-m "not slow"` in ci.yml won't exclude an unmarked test, and
# `--collect-only` (which doesn't execute fixtures) won't catch that gap.
pytestmark = pytest.mark.slow


@dataclass(frozen=True)
class Pair:
    id: str
    a: str
    b: str
    note: str
    casefold_probe: bool = False


@dataclass(frozen=True)
class ScoredPair:
    pair: Pair
    score: float
    margin: float  # score - threshold; sign only meaningful relative to the gate direction


@dataclass(frozen=True)
class CasefoldProbeResult:
    pair: Pair
    cased_cosine: float
    cased_score: float
    casefolded_score: float
    cased_margin: float
    casefolded_margin: float


def _load_fixture() -> dict[str, list[Pair]]:
    raw = yaml.safe_load(FIXTURE_PATH.read_text(encoding="utf-8"))
    return {
        category: [Pair(**entry) for entry in entries] for category, entries in raw.items()
    }


def _score_comparison_form(
    embedder: SentenceTransformersEmbedder, policy: SimilarityPolicy, pair: Pair
) -> float:
    """Production-shaped score: `comparison_form(display_form(text))` before
    embedding, matching every real call site -- not `comparison_form` alone
    on the raw string, which skips its step 1-2 preconditions."""
    vector_a = embedder.embed(comparison_form(display_form(pair.a)))
    vector_b = embedder.embed(comparison_form(display_form(pair.b)))
    return policy.score(cosine_distance(vector_a, vector_b))


def _casefold_probe(
    embedder: SentenceTransformersEmbedder, policy: SimilarityPolicy, pair: Pair, threshold: float
) -> CasefoldProbeResult:
    """Task 9.2: scores the SAME pair twice -- once on the cased display
    form (bypassing `embed()`'s documented comparison-form precondition on
    purpose, for measurement only -- never done in production code) and
    once on the casefolded comparison form -- to measure how much
    separating margin casefolding costs on this cased checkpoint (design.md
    "Accepted cost", ADR-003 open question)."""
    cased_a = embedder.embed(display_form(pair.a))
    cased_b = embedder.embed(display_form(pair.b))
    cased_cosine = cosine_similarity(cased_a, cased_b)
    cased_score = policy.score(cosine_distance(cased_a, cased_b))

    casefolded_score = _score_comparison_form(embedder, policy, pair)

    return CasefoldProbeResult(
        pair=pair,
        cased_cosine=round(cased_cosine, 4),
        cased_score=cased_score,
        casefolded_score=casefolded_score,
        cased_margin=round(cased_score - threshold, 4),
        casefolded_margin=round(casefolded_score - threshold, 4),
    )


@dataclass(frozen=True)
class CalibrationReport:
    settings: Settings
    policy: SimilarityPolicy
    duplicate: list[ScoredPair]
    distinct: list[ScoredPair]
    expected_weakness: list[ScoredPair]
    casefold_probes: list[CasefoldProbeResult]


def _table(header: str, sep: str, rows: list[str]) -> list[str]:
    return [header, sep, *rows]


def _scored_rows(scored_pairs: list[ScoredPair]) -> list[str]:
    row = "| `{}` | {} | {} | {} | {:+.4f} | {} |".format
    return [
        row(s.pair.id, s.pair.a, s.pair.b, s.score, s.margin, s.pair.note) for s in scored_pairs
    ]


def _render_evidence_markdown(report: CalibrationReport) -> str:
    generated_at = datetime.now(UTC).strftime("%Y-%m-%d %H:%M UTC")
    threshold = report.settings.similarity_threshold
    lines = [
        "# ES/EN calibration evidence (tasks.md 9.1/9.2)",
        "",
        f"Generated {generated_at} by `make evidence`, scored against the real "
        f"`{report.settings.embedding_model}` model, revision "
        f"`{report.settings.embedding_model_revision}` -- the brief's Hugging Face "
        f"integration evidence deliverable. `SIMILARITY_THRESHOLD` at run time: "
        f"**{threshold}**.",
        "",
        "## Duplicate pairs (hard-gated: score >= threshold)",
        "",
        *_table(
            "| id | a | b | score | margin | note |",
            "| --- | --- | --- | --- | --- | --- |",
            _scored_rows(report.duplicate),
        ),
        "",
        "## Distinct pairs (hard-gated: score < threshold)",
        "",
        *_table(
            "| id | a | b | score | margin | note |",
            "| --- | --- | --- | --- | --- | --- |",
            _scored_rows(report.distinct),
        ),
        "",
        "## Expected weakness pairs (reported, NEVER gated)",
        "",
        "Negation pairs are a known, documented weakness of sentence embeddings on "
        'this checkpoint (design.md\'s "Accepted cost"): reported for visibility, '
        "never hard-gated.",
        "",
        *_table(
            "| id | a | b | score | note |",
            "| --- | --- | --- | --- | --- |",
            [
                f"| `{s.pair.id}` | {s.pair.a} | {s.pair.b} | {s.score} | {s.pair.note} |"
                for s in report.expected_weakness
            ],
        ),
        "",
        "## Cased vs. casefolded margin (task 9.2)",
        "",
        "`paraphrase-multilingual-MiniLM-L12-v2` is a **cased** checkpoint; production "
        "always embeds the casefolded comparison form. This table measures how much "
        "separating margin casefolding costs versus the raw display form, same pair(s).",
        "",
        *_table(
            "| id | cased cosine | cased score | cased margin | casefolded score | "
            "casefolded margin |",
            "| --- | --- | --- | --- | --- | --- |",
            [
                f"| `{p.pair.id}` | {p.cased_cosine} | {p.cased_score} | "
                f"{p.cased_margin:+.4f} | {p.casefolded_score} | {p.casefolded_margin:+.4f} |"
                for p in report.casefold_probes
            ],
        ),
        "",
        "Design.md's ADR-003 estimated the cased-variant cosine "
        "(`case_and_spacing_variant`, display forms) at **~0.98, unmeasured**; the row "
        "above is the first real measurement. If casefolding materially narrows the "
        "margin around the threshold, the decision rule applies: change "
        "`SIMILARITY_THRESHOLD`'s default (and `.env.example`, the spec, and an "
        "ADR-003 note) as a recorded spec change -- never silently, never by bending "
        "the fixture.",
        "",
    ]
    return "\n".join(lines) + "\n"


@pytest.fixture(scope="module")
def calibration_report() -> CalibrationReport:
    settings = Settings(
        database_url="postgresql+psycopg://test:test@localhost:5432/test",
        embedding_model_revision="e8f8c211226b894fcb81acc59f3b34ba3efd5f42",
    )
    embedder = load_sentence_transformer(settings)
    policy = SimilarityPolicy(threshold=settings.similarity_threshold)
    fixture = _load_fixture()

    def _score_all(category: str) -> list[ScoredPair]:
        scored = []
        for pair in fixture.get(category, []):
            score = _score_comparison_form(embedder, policy, pair)
            scored.append(
                ScoredPair(
                    pair=pair, score=score, margin=round(score - settings.similarity_threshold, 4)
                )
            )
        return scored

    duplicate = _score_all("duplicate")
    distinct = _score_all("distinct")
    expected_weakness = _score_all("expected_weakness")

    casefold_probes = [
        _casefold_probe(embedder, policy, pair, settings.similarity_threshold)
        for pair in fixture.get("duplicate", [])
        if pair.casefold_probe
    ]

    report = CalibrationReport(
        settings=settings,
        policy=policy,
        duplicate=duplicate,
        distinct=distinct,
        expected_weakness=expected_weakness,
        casefold_probes=casefold_probes,
    )

    EVIDENCE_PATH.parent.mkdir(parents=True, exist_ok=True)
    EVIDENCE_PATH.write_text(_render_evidence_markdown(report), encoding="utf-8")

    return report


def test_the_real_model_is_deterministic(calibration_report: CalibrationReport) -> None:
    """Sanity check ahead of the gated assertions below: embedding the same
    text twice must produce an identical score, otherwise the fixture's
    hard gates would be testing noise, not the model."""
    settings = calibration_report.settings
    embedder = load_sentence_transformer(settings)
    text = comparison_form("Comprar leche")

    assert embedder.embed(text) == embedder.embed(text)


def test_duplicate_pairs_score_at_or_above_the_threshold(
    calibration_report: CalibrationReport,
) -> None:
    # Same Decimal predicate production gates on, not a float reimplementation.
    threshold = calibration_report.settings.similarity_threshold
    policy = calibration_report.policy
    failures = [
        (scored.pair.id, scored.score)
        for scored in calibration_report.duplicate
        if not policy.is_duplicate(scored.score)
    ]
    assert not failures, (
        f"duplicate pairs scored below the configured threshold ({threshold}): {failures} "
        "-- see docs/evidence/calibration.md for the full table"
    )


def test_distinct_pairs_score_below_the_threshold(
    calibration_report: CalibrationReport,
) -> None:
    threshold = calibration_report.settings.similarity_threshold
    policy = calibration_report.policy
    failures = [
        (scored.pair.id, scored.score)
        for scored in calibration_report.distinct
        if policy.is_duplicate(scored.score)
    ]
    assert not failures, (
        f"distinct pairs scored at or above the configured threshold ({threshold}): {failures} "
        "-- see docs/evidence/calibration.md for the full table"
    )


def test_expected_weakness_pairs_are_reported_not_gated(
    calibration_report: CalibrationReport,
) -> None:
    """No pass/fail assertion on the score itself -- negation pairs are a
    KNOWN, documented weakness of sentence embeddings (design.md's
    "Accepted cost"), reported in the evidence table, never gated. The only
    thing this test asserts is that the fixture actually has entries and
    that scoring ran (a non-empty, well-formed score for every pair), so a
    silently-empty category can't hide as a false "pass"."""
    assert calibration_report.expected_weakness, "expected_weakness fixture category is empty"
    for scored in calibration_report.expected_weakness:
        assert 0.0 <= scored.score <= 1.0


def test_evidence_file_was_written(calibration_report: CalibrationReport) -> None:
    assert EVIDENCE_PATH.exists()
    content = EVIDENCE_PATH.read_text(encoding="utf-8")
    assert "ES/EN calibration evidence" in content
    assert calibration_report.settings.embedding_model in content
