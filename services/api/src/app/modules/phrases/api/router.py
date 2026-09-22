# NOTE: NO `from __future__ import annotations` here on purpose.
# `_ValidateRequest` is nested inside `build_validate_router()` so its
# field bounds close over the caller's settings; postponed evaluation would
# turn those into unresolved strings FastAPI can't reach via closure locals
# -- the exact bug the Unit 6 fix-pass found (see test_framework_errors.py).
"""`POST /phrases/validate` (tasks.md 6b.1, design.md's Data Flow /
"Request shapes"). Reads its `ValidatePhrase` off `request.app.state.phrases`
(assembled by `phrases/container.py`) -- imports no adapter (import-linter's
`composition-root-owns-adapters` contract forbids it for `phrases.api`).
"""

from fastapi import APIRouter, Request
from pydantic import BaseModel, ConfigDict

from app.modules.phrases.api.schemas import PhraseId, page_limit, raw_phrase_text
from app.modules.phrases.container import PhrasesContainer


class _ScoredPhrase(BaseModel):
    """Shared shape of `most_similar` and each `matches[]` entry."""

    id: PhraseId
    text: str
    score: float


class _ValidateData(BaseModel):
    is_duplicate: bool
    threshold: float
    score: float | None
    most_similar: _ScoredPhrase | None
    matches: list[_ScoredPhrase]
    next_cursor: str | None
    has_more: bool


class _ValidateResponse(BaseModel):
    data: _ValidateData


def build_validate_router(*, phrase_max_length: int, matches_page_size: int) -> APIRouter:
    router = APIRouter()

    class _ValidateRequest(BaseModel):
        # `cursor` is silently ignored, not a schema violation (design.md D9).
        model_config = ConfigDict(extra="ignore")

        text: raw_phrase_text(phrase_max_length)  # type: ignore[valid-type]
        limit: page_limit(matches_page_size) | None = None  # type: ignore[valid-type]

    @router.post("/phrases/validate", response_model=_ValidateResponse)
    def validate_phrase(body: _ValidateRequest, request: Request) -> _ValidateResponse:
        container: PhrasesContainer = request.app.state.phrases
        limit = body.limit if body.limit is not None else matches_page_size
        verdict = container.validate_phrase(body.text, limit=limit)

        most_similar = (
            _ScoredPhrase(**vars(verdict.most_similar)) if verdict.most_similar else None
        )
        matches = [_ScoredPhrase(**vars(m)) for m in verdict.matches]
        return _ValidateResponse(
            data=_ValidateData(
                is_duplicate=verdict.is_duplicate,
                threshold=verdict.threshold,
                score=verdict.score,
                most_similar=most_similar,
                matches=matches,
                next_cursor=verdict.next_cursor,
                has_more=verdict.has_more,
            )
        )

    return router
