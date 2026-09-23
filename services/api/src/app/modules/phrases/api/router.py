# NOTE: NO `from __future__ import annotations` here on purpose.
# Every request model below is nested inside its factory function so its
# field bounds close over the caller's settings; postponed evaluation would
# turn those into unresolved strings FastAPI can't reach via closure locals
# -- the exact bug the Unit 6 fix-pass found (see test_framework_errors.py).
"""`POST /phrases/validate` (tasks.md 6b.1) plus `POST /phrases` and
`POST /phrases/matches` (tasks.md 7.1, design.md's Data Flow / "Request
shapes"). `GET /phrases` and the OpenAPI documentation pass are deferred to
Unit 7b (tasks.md's Unit 7 seam note: over budget even after a trim pass).
Every route reads its use case off `request.app.state.phrases` (assembled
by `phrases/container.py`) -- imports no adapter (import-linter's
`composition-root-owns-adapters` contract forbids it for `phrases.api`).
"""

from datetime import datetime
from typing import Annotated

from fastapi import APIRouter, Request
from pydantic import BaseModel, ConfigDict, Field, StrictBool
from starlette.responses import JSONResponse

from app.modules.phrases.api.schemas import PhraseId, page_limit, raw_phrase_text
from app.modules.phrases.application._shared import MatchView, MostSimilarView, VerdictView
from app.modules.phrases.container import PhrasesContainer
from app.modules.phrases.contracts import Phrase

# NOTE: the error envelope is built inline below, NOT via
# `app.platform.errors.error_envelope`: that module imports
# `similarity.domain.errors`, and import-linter checks the FULL transitive
# chain -- `phrases.api -> platform.errors -> similarity.domain` would break
# the `phrases-only-similarity-contracts` contract.


class _ScoredPhrase(BaseModel):
    """Shared shape of `most_similar` and each `matches[]` entry."""

    id: PhraseId
    text: str
    score: float


def _scored_phrase(view: MatchView | MostSimilarView) -> _ScoredPhrase:
    """Explicit field-by-field mapping from the application layer's
    `MatchView`/`MostSimilarView` to the wire `_ScoredPhrase` (fix-pass,
    review finding #2: replaces `_ScoredPhrase(**vars(view))`, used at 5
    call sites, so a field rename/add on either side fails at mypy
    type-check time instead of silently at runtime)."""
    return _ScoredPhrase(id=view.id, text=view.text, score=view.score)


class _ValidationOut(BaseModel):
    status: str
    score: float | None
    most_similar_phrase_id: PhraseId | None
    validated_at: datetime


class _PhraseOut(BaseModel):
    """The 201 body of `POST /phrases`."""

    id: PhraseId
    text: str
    created_at: datetime
    validation: _ValidationOut


def _phrase_out(phrase: Phrase) -> _PhraseOut:
    return _PhraseOut(
        id=phrase.id,
        text=phrase.text,
        created_at=phrase.created_at,
        validation=_ValidationOut(
            status=phrase.validation_status.value,
            score=phrase.similarity_score,
            most_similar_phrase_id=phrase.most_similar_phrase_id,
            validated_at=phrase.validated_at,
        ),
    )


def _verdict_details(verdict: VerdictView) -> dict[str, object]:
    """The validate-shaped 409 `details` payload (design.md: "The 409 body
    carries a complete validate response")."""
    most_similar = (
        _scored_phrase(verdict.most_similar).model_dump(mode="json")
        if verdict.most_similar is not None
        else None
    )
    matches = [_scored_phrase(m).model_dump(mode="json") for m in verdict.matches]
    return {
        "threshold": verdict.threshold,
        "score": verdict.score,
        "most_similar": most_similar,
        "matches": matches,
        "next_cursor": verdict.next_cursor,
        "has_more": verdict.has_more,
    }


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

        most_similar = _scored_phrase(verdict.most_similar) if verdict.most_similar else None
        matches = [_scored_phrase(m) for m in verdict.matches]
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


class _MatchesData(BaseModel):
    matches: list[_ScoredPhrase]
    next_cursor: str | None
    has_more: bool


class _MatchesResponse(BaseModel):
    data: _MatchesData


class _PhraseResponse(BaseModel):
    data: _PhraseOut


def build_phrases_router(*, phrase_max_length: int, matches_page_size: int) -> APIRouter:
    """`POST /phrases`, `POST /phrases/matches` (tasks.md 7.1)."""
    router = APIRouter()

    class _SaveRequest(BaseModel):
        model_config = ConfigDict(extra="ignore")

        text: raw_phrase_text(phrase_max_length)  # type: ignore[valid-type]
        confirm_duplicate: StrictBool = False

    class _MatchesRequest(BaseModel):
        model_config = ConfigDict(extra="ignore")

        text: raw_phrase_text(phrase_max_length)  # type: ignore[valid-type]
        cursor: Annotated[str, Field(description="Opaque; clients MUST NOT parse it.")]
        limit: page_limit(matches_page_size) | None = None  # type: ignore[valid-type]

    @router.post("/phrases", status_code=201, response_model=_PhraseResponse)
    def save_phrase(body: _SaveRequest, request: Request) -> _PhraseResponse | JSONResponse:
        container: PhrasesContainer = request.app.state.phrases
        result = container.save_phrase(body.text, confirm_duplicate=body.confirm_duplicate)
        if result.conflict is not None:
            return JSONResponse(
                status_code=409,
                content={
                    "error": {
                        "code": "DUPLICATE_CONFIRMATION_REQUIRED",
                        "message": "a similar phrase already exists; confirm to save it anyway",
                        "details": _verdict_details(result.conflict),
                    }
                },
            )
        if result.phrase is None:
            # Invariant: `SaveResult` sets exactly one of `phrase`/`conflict`
            # (see `SavePhrase.SaveResult`'s docstring); `conflict is None`
            # here already ruled out the conflict branch above, so `phrase`
            # MUST be set. A plain `assert` is stripped under `python -O`,
            # which would then hit `_phrase_out(None)` and fail with a less
            # clear `AttributeError` (fix-pass, review finding #3) -- raise
            # explicitly instead, so this stays checked in every build and
            # fails with a self-explanatory message if it's ever wrong.
            raise RuntimeError("SaveResult.phrase must be set when result.conflict is None")
        return _PhraseResponse(data=_phrase_out(result.phrase))

    @router.post("/phrases/matches", response_model=_MatchesResponse)
    def list_matches(body: _MatchesRequest, request: Request) -> _MatchesResponse:
        container: PhrasesContainer = request.app.state.phrases
        limit = body.limit if body.limit is not None else matches_page_size
        page = container.list_matches(body.text, cursor=body.cursor, limit=limit)
        return _MatchesResponse(
            data=_MatchesData(
                matches=[_scored_phrase(m) for m in page.matches],
                next_cursor=page.next_cursor,
                has_more=page.has_more,
            )
        )

    return router
