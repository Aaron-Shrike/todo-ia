"""Doc-check test for the decision log (tasks.md 16.4; design.md's
"Beyond the Brief" Decision Log).

Two independent concerns, deliberately kept in separate test functions:

1. ADR file/front-matter structure under `docs/decisions/` -- this is
   Unit 16's own scope and runs now.
2. README.md linking every ADR by filename -- README.md is Unit 15's
   deliverable, deliberately written AFTER Unit 16 so it can link real
   files instead of placeholders. That assertion is marked `xfail(strict=
   True)` below with the reason spelled out; Unit 15 must remove the
   `xfail` decorator once README.md exists and links every ADR, not
   delete or weaken the assertion.
"""

from __future__ import annotations

from pathlib import Path

import pytest
import yaml

# tests/unit/test_decision_log.py -> tests -> api -> services -> repo root
# (same depth as tests/slow/test_calibration.py's EVIDENCE_PATH).
REPO_ROOT = Path(__file__).resolve().parents[4]
DECISIONS_DIR = REPO_ROOT / "docs" / "decisions"
TECHNICAL_DIR = DECISIONS_DIR / "technical"
README_PATH = REPO_ROOT / "README.md"


def _front_matter(path: Path) -> dict:
    text = path.read_text(encoding="utf-8")
    assert text.startswith("---\n"), f"{path} is missing YAML front matter"
    _, raw, _ = text.split("---\n", 2)
    return yaml.safe_load(raw)


def _top_level_adr_files() -> list[Path]:
    """Top-level `docs/decisions/*.md` only -- excludes `technical/` by
    construction, since `Path.glob("*.md")` does not recurse."""
    return sorted(p for p in DECISIONS_DIR.glob("*.md") if p.is_file())


def _technical_adr_files() -> list[Path]:
    return sorted(p for p in TECHNICAL_DIR.glob("*.md") if p.is_file())


def test_exactly_five_beyond_brief_adrs_at_top_level() -> None:
    files = _top_level_adr_files()
    assert len(files) == 5, (
        f"expected exactly 5 top-level ADRs (ADR-001..005), found "
        f"{[f.name for f in files]}"
    )


def test_every_top_level_adr_is_type_beyond_brief() -> None:
    files = _top_level_adr_files()
    assert files, "no top-level ADR files found under docs/decisions/"
    wrong = [f.name for f in files if _front_matter(f).get("type") != "beyond-brief"]
    assert not wrong, f"top-level ADRs missing front-matter type: beyond-brief: {wrong}"


def test_technical_adrs_are_present_and_typed_technical() -> None:
    """Structural check only (dir non-empty, every present file typed
    `technical`) -- deliberately no hard count here. Unit 16 ships ADR-006..
    009 (4 files); Unit 16b adds ADR-010..015 to reach the full 10. Unit 16b
    tightens this into an exact-count assertion once all ten exist (see
    apply-progress.md's Unit 16 resolution note)."""
    files = _technical_adr_files()
    assert files, "no technical ADR files found under docs/decisions/technical/"
    wrong = [f.name for f in files if _front_matter(f).get("type") != "technical"]
    assert not wrong, f"technical ADRs missing front-matter type: technical: {wrong}"


@pytest.mark.xfail(
    reason=(
        "README.md is Unit 15's deliverable, deliberately deferred until after "
        "Unit 16 so it can link real ADR files instead of placeholders (see "
        "apply-progress.md's Unit 16 section). Remove this xfail once Unit 15 "
        "writes README.md and links every ADR by filename/anchor."
    ),
    strict=True,
)
def test_readme_links_every_adr() -> None:
    assert README_PATH.exists(), "README.md does not exist yet (Unit 15)"
    content = README_PATH.read_text(encoding="utf-8")
    all_adrs = _top_level_adr_files() + _technical_adr_files()
    missing = [f.name for f in all_adrs if f.name not in content]
    assert not missing, f"README.md does not link: {missing}"
