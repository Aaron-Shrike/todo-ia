"""Shared view types and the tail-rule reconciliation helper for the Unit 3
use cases. Not in tasks.md's literal file list -- the "validate-shaped"
result (design.md: "The 409 body carries a complete validate response") is
built by `ValidatePhrase` and by `SavePhrase`'s 409 `details`, so it is
built once here instead of twice.
"""

from __future__ import annotations

from dataclasses import dataclass

from app.modules.phrases.contracts import Match, Page
from app.modules.phrases.domain.cursor import encode_cursor
from app.modules.phrases.domain.errors import EmptyPhraseText, PhraseTooLong
from app.modules.phrases.domain.normalization import comparison_form, display_form
from app.modules.similarity.contracts import SimilarityPolicy


@dataclass(frozen=True)
class MatchView:
    id: int
    text: str
    score: float


@dataclass(frozen=True)
class MostSimilarView:
    id: int
    text: str
    score: float


@dataclass(frozen=True)
class MatchesPage:
    matches: list[MatchView]
    next_cursor: str | None
    has_more: bool


@dataclass(frozen=True)
class VerdictView:
    """The validate-shaped result: `ValidatePhrase`'s return value AND
    `SavePhrase`'s 409 `details` payload."""

    is_duplicate: bool
    threshold: float
    score: float | None
    most_similar: MostSimilarView | None
    matches: list[MatchView]
    next_cursor: str | None
    has_more: bool


def normalize_and_check_length(text: str, *, max_length: int) -> tuple[str, str]:
    """Display + comparison form, rejecting empty/too-long BEFORE any
    embedding call (design.md's save/validate flow)."""
    display = display_form(text)
    comparison = comparison_form(display)
    if not comparison:
        raise EmptyPhraseText
    if len(comparison) > max_length:
        raise PhraseTooLong(max_length=max_length)
    return display, comparison


def build_matches_page(
    page: Page[Match], policy: SimilarityPolicy, *, comparison: str
) -> MatchesPage:
    """The tail rule: `find_matches`' widened SQL bound over-selects, so
    stop at the first row failing `policy.includes` (monotonic in distance)
    and force `has_more=False`/`next_cursor=None`, overriding the
    repository's own `+1`-probe answer."""
    kept: list[Match] = []
    truncated = False
    for item in page.items:
        if not policy.includes(item.distance):
            truncated = True
            break
        kept.append(item)

    has_more = False if truncated else page.has_more
    cursor = None if truncated else page.next_cursor
    views = [MatchView(id=m.id, text=m.text, score=policy.score(m.distance)) for m in kept]
    next_cursor = (
        encode_cursor(t=comparison, d=cursor.distance, i=cursor.id, th=policy.threshold)
        if cursor is not None
        else None
    )
    return MatchesPage(matches=views, next_cursor=next_cursor, has_more=has_more)
