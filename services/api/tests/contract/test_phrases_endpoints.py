"""Contract tests for `POST /phrases`, `POST /phrases/matches` (tasks.md
7.1/7.2) and `GET /phrases` (tasks.md 7b.1/7b.2, folded in here per the
task's own instruction), against the real `create_app()` wiring with fakes
and the in-memory repo (precedent: `test_validate_health.py`). The OpenAPI
scenarios live in `tests/contract/test_openapi.py`; the three real-Postgres
scenarios live in `tests/integration/test_endpoints_pgvector.py`.
"""

from __future__ import annotations

from datetime import UTC, datetime

import pytest
from fastapi.testclient import TestClient

from app.main import create_app
from app.modules.phrases.adapters.in_memory_repository import InMemoryUnitOfWorkFactory
from app.modules.phrases.container import build_phrases_container
from app.modules.phrases.contracts import (
    DuplicateTextConflict,
    NewPhrase,
    UnitOfWorkFactory,
    ValidationStatus,
)
from app.modules.phrases.domain.cursor import encode_cursor
from app.modules.similarity.adapters.caching import CachingEmbeddingProvider
from app.modules.similarity.adapters.failing import FailingEmbedder
from app.modules.similarity.adapters.fake import FakeEmbedder
from app.modules.similarity.contracts import (
    EmbeddingProvider,
    EmbeddingTimeout,
    EmbeddingUnavailable,
    SimilarityPolicy,
)
from app.platform.errors import error_envelope
from app.platform.settings import Settings
from tests.contract_suite.vectors import PROBE, vector_at_distance
from tests.unit.phrases._uow_spies import ConflictRepo, ProxyUnitOfWorkFactory

pytestmark = pytest.mark.contract

_QUERY_TEXT = "query text"
_VALID_CURSOR = encode_cursor(t=_QUERY_TEXT, d=0.05, i=1, th=0.80)
_LARGE_MATCH_SET = [(f"m{i}", 0.01 + i * 0.001) for i in range(120)]  # all above threshold


def _client(
    *,
    embedder: EmbeddingProvider | None = None,
    uow_factory: UnitOfWorkFactory | None = None,
    cache_capacity: int = 0,
    matches_page_size: int = 50,
    phrases_list_limit: int = 200,
) -> tuple[TestClient, EmbeddingProvider, UnitOfWorkFactory]:
    settings = Settings(
        database_url="postgresql+psycopg://test:test@localhost:5432/test",
        matches_page_size=matches_page_size,
        phrases_list_limit=phrases_list_limit,
    )
    app = create_app(settings)
    inner = embedder if embedder is not None else FakeEmbedder({_QUERY_TEXT: PROBE, "hola": PROBE})
    wrapped: EmbeddingProvider = (
        CachingEmbeddingProvider(inner, capacity=cache_capacity) if cache_capacity > 0 else inner
    )
    factory = uow_factory if uow_factory is not None else InMemoryUnitOfWorkFactory()
    app.state.phrases = build_phrases_container(
        embedder=wrapped,
        uow_factory=factory,
        policy=SimilarityPolicy(threshold=settings.similarity_threshold),
        phrase_max_length=settings.phrase_max_length,
        matches_page_size=settings.matches_page_size,
        phrases_list_limit=settings.phrases_list_limit,
    )
    return TestClient(app, raise_server_exceptions=False), inner, factory


def _seed(factory: object, *entries: tuple[str, float]) -> None:
    with factory() as uow:  # type: ignore[operator]
        for text, distance in entries:
            uow.repo.add(
                NewPhrase(
                    text=text,
                    normalized_text=text,
                    embedding=vector_at_distance(distance),
                    similarity_score=None,
                    most_similar_phrase_id=None,
                    validation_status=ValidationStatus.UNIQUE,
                    validated_at=datetime.now(UTC),
                )
            )
        uow.commit()


def _walk_pages(client: TestClient, cursor: str, sizes: list[int]) -> None:
    """Continues `POST /phrases/matches` calls; each page's item count must
    match `sizes` in order, and only the last has `has_more=False`."""
    for index, expected_count in enumerate(sizes):
        response = client.post("/phrases/matches", json={"text": _QUERY_TEXT, "cursor": cursor})
        assert response.status_code == 200
        data = response.json()["data"]
        assert len(data["matches"]) == expected_count
        is_last = index == len(sizes) - 1
        assert data["has_more"] is (not is_last)
        cursor = data["next_cursor"]


# --- POST /phrases/matches ---------------------------------------------


def test_matches_pagination_walk_from_validate() -> None:
    client, _, factory = _client(matches_page_size=50)
    _seed(factory, *_LARGE_MATCH_SET)
    first = client.post("/phrases/validate", json={"text": _QUERY_TEXT})
    data = first.json()["data"]
    assert len(data["matches"]) == 50
    assert data["has_more"] is True
    _walk_pages(client, data["next_cursor"], [50, 20])


def test_matches_response_has_no_verdict_fields() -> None:
    client, _, factory = _client(matches_page_size=1)
    _seed(factory, ("a", 0.05), ("b", 0.06))
    first = client.post("/phrases/validate", json={"text": _QUERY_TEXT})
    cursor = first.json()["data"]["next_cursor"]
    assert cursor is not None
    response = client.post("/phrases/matches", json={"text": _QUERY_TEXT, "cursor": cursor})
    assert response.status_code == 200
    assert set(response.json()["data"]) == {"matches", "next_cursor", "has_more"}


@pytest.mark.parametrize(
    "cursor",
    [
        encode_cursor(t="a different comparison form", d=0.05, i=1, th=0.80),
        encode_cursor(t=_QUERY_TEXT, d=0.05, i=1, th=0.90),
        "not-a-cursor!!",
        encode_cursor(t=_QUERY_TEXT, d=-1.0, i=1, th=0.80),
    ],
    ids=["different-text", "different-threshold", "malformed-base64url", "field-out-of-range"],
)
def test_matches_invalid_cursor_is_400(cursor: str) -> None:
    client, _, _ = _client()
    response = client.post("/phrases/matches", json={"text": _QUERY_TEXT, "cursor": cursor})
    assert response.status_code == 400
    assert response.json()["error"]["code"] == "INVALID_CURSOR"


@pytest.mark.parametrize(
    ("body", "field", "reason"),
    [
        ({"text": _QUERY_TEXT}, "cursor", "required"),
        ({"text": _QUERY_TEXT, "cursor": _VALID_CURSOR, "limit": 0}, "limit", "out_of_range"),
        ({"text": _QUERY_TEXT, "cursor": _VALID_CURSOR, "limit": 51}, "limit", "out_of_range"),
    ],
    ids=["missing-cursor", "limit-too-low", "limit-too-high"],
)
def test_matches_schema_violations_are_422(
    body: dict[str, object], field: str, reason: str
) -> None:
    client, _, _ = _client(matches_page_size=50)
    response = client.post("/phrases/matches", json=body)
    assert response.status_code == 422
    assert response.json()["error"]["details"]["fields"][0] == {"field": field, "reason": reason}


@pytest.mark.parametrize(
    ("error", "status_code", "code"),
    [
        (EmbeddingUnavailable(), 503, "EMBEDDING_UNAVAILABLE"),
        (EmbeddingTimeout(), 504, "EMBEDDING_TIMEOUT"),
    ],
)
def test_matches_provider_failure_returns_503_or_504(
    error: Exception, status_code: int, code: str
) -> None:
    # Mirror of `test_save_provider_failure_never_persists` (fix-pass, review
    # finding #1): `ListMatches.__call__` embeds the query text (after
    # decoding/binding the cursor) before ever touching the repository, same
    # ordering as `SavePhrase`, so a provider failure here must surface as
    # the same registered 503/504 -- never a 200 or an unregistered 500.
    failing = FailingEmbedder(FakeEmbedder({_QUERY_TEXT: PROBE}), fail_times=None, error=error)
    client, _, _ = _client(embedder=failing)
    response = client.post("/phrases/matches", json={"text": _QUERY_TEXT, "cursor": _VALID_CURSOR})
    assert response.status_code == status_code
    assert response.json()["error"]["code"] == code


def test_matches_database_unreachable_is_500() -> None:
    # Mirror of `test_save_database_unreachable_is_500_and_persists_nothing`
    # (fix-pass, review finding #1): embedding succeeds, then
    # `self._uow_factory()` raises -- same unregistered-exception path as
    # `SavePhrase`'s, so it must surface as the same generic 500
    # `INTERNAL_ERROR`, never an unhandled crash.
    def _broken(*, isolation: object = None, read_only: bool = False) -> None:
        raise RuntimeError("connection refused")

    client, _, _ = _client(uow_factory=_broken)  # type: ignore[arg-type]
    response = client.post("/phrases/matches", json={"text": _QUERY_TEXT, "cursor": _VALID_CURSOR})
    assert response.status_code == 500
    assert response.json()["error"]["code"] == "INTERNAL_ERROR"


# --- POST /phrases -------------------------------------------------------


def test_save_created_unique_records_null_metadata_and_normalizes_text() -> None:
    client, _, _ = _client()
    response = client.post("/phrases", json={"text": "  Hola​  "})
    assert response.status_code == 201
    data = response.json()["data"]
    assert data["text"] == "Hola"  # normalized
    validation = data["validation"]
    assert validation["status"] == "unique"
    assert validation["score"] is None
    assert validation["most_similar_phrase_id"] is None
    assert validation["validated_at"]


def test_save_created_confirmed_records_score_and_neighbor() -> None:
    client, _, factory = _client()
    _seed(factory, ("existing", 0.05))  # score .95, duplicate at t=.80
    response = client.post("/phrases", json={"text": _QUERY_TEXT, "confirm_duplicate": True})
    assert response.status_code == 201
    validation = response.json()["data"]["validation"]
    assert validation["status"] == "duplicate_confirmed"
    assert validation["score"] == 0.95
    assert validation["most_similar_phrase_id"] == "1"


def test_save_conflict_shape_and_payload_completeness() -> None:
    client, _, factory = _client(matches_page_size=50)
    _seed(factory, ("a", 0.05), ("b", 0.10), ("c", 0.15))  # 3 matches, all above threshold
    response = client.post("/phrases", json={"text": _QUERY_TEXT})
    assert response.status_code == 409
    body = response.json()
    assert set(body) == {"error"}
    error = body["error"]
    assert error["code"] == "DUPLICATE_CONFIRMATION_REQUIRED"
    assert isinstance(error["message"], str)
    details = error["details"]
    assert details["threshold"] == 0.80
    assert details["score"] == 0.95
    assert details["most_similar"] == {"id": "1", "text": "a", "score": 0.95}
    scores = [m["score"] for m in details["matches"]]
    assert len(scores) == 3
    assert scores == sorted(scores, reverse=True)
    assert details["has_more"] is False
    assert details["next_cursor"] is None
    with factory(read_only=True) as uow:  # type: ignore[operator]
        assert len(uow.repo.list_recent(10)) == 3  # nothing new persisted


def test_save_409_envelope_matches_error_envelope_shape() -> None:
    # Drift guard (fix-pass, review finding #6): `save_phrase`'s 409 body is
    # a hand-built `{"error": {...}}` dict, built inline to dodge an
    # import-linter violation instead of importing
    # `app.platform.errors.error_envelope` (see router.py's module note).
    # Assert the two stay structurally in sync -- same key set, same nesting
    # -- so a future field rename/add to `error_envelope` gets caught here
    # instead of silently diverging.
    client, _, factory = _client()
    _seed(factory, ("existing", 0.05))
    response = client.post("/phrases", json={"text": _QUERY_TEXT})
    assert response.status_code == 409
    body = response.json()
    expected = error_envelope(
        body["error"]["code"], body["error"]["message"], body["error"]["details"]
    )
    assert set(body) == set(expected)
    assert set(body["error"]) == set(expected["error"])


def test_save_large_match_set_on_409_next_cursor_usable_with_matches() -> None:
    client, _, factory = _client(matches_page_size=50)
    _seed(factory, *_LARGE_MATCH_SET)
    response = client.post("/phrases", json={"text": _QUERY_TEXT})
    assert response.status_code == 409
    details = response.json()["error"]["details"]
    assert len(details["matches"]) == 50
    assert details["has_more"] is True
    _walk_pages(client, details["next_cursor"], [50, 20])


@pytest.mark.parametrize("bad_flag", ["yes", 1, "true"])
def test_save_non_boolean_confirm_duplicate_rejected(bad_flag: object) -> None:
    client, _, factory = _client()
    response = client.post("/phrases", json={"text": _QUERY_TEXT, "confirm_duplicate": bad_flag})
    assert response.status_code == 422
    fields = response.json()["error"]["details"]["fields"]
    assert fields[0] == {"field": "confirm_duplicate", "reason": "invalid_type"}
    with factory(read_only=True) as uow:  # type: ignore[operator]
        assert uow.repo.list_recent(10) == []


@pytest.mark.parametrize(
    ("error", "status_code", "code"),
    [
        (EmbeddingUnavailable(), 503, "EMBEDDING_UNAVAILABLE"),
        (EmbeddingTimeout(), 504, "EMBEDDING_TIMEOUT"),
    ],
)
def test_save_provider_failure_never_persists(
    error: Exception, status_code: int, code: str
) -> None:
    failing = FailingEmbedder(FakeEmbedder({_QUERY_TEXT: PROBE}), fail_times=None, error=error)
    client, _, factory = _client(embedder=failing)
    response = client.post("/phrases", json={"text": _QUERY_TEXT, "confirm_duplicate": True})
    assert response.status_code == status_code
    assert response.json()["error"]["code"] == code
    with factory(read_only=True) as uow:  # type: ignore[operator]
        assert uow.repo.list_recent(10) == []


def test_save_database_unreachable_is_500_and_persists_nothing() -> None:
    def _broken(*, isolation: object = None, read_only: bool = False) -> None:
        raise RuntimeError("connection refused")

    client, _, _ = _client(uow_factory=_broken)  # type: ignore[arg-type]
    response = client.post("/phrases", json={"text": _QUERY_TEXT})
    assert response.status_code == 500
    assert response.json()["error"]["code"] == "INTERNAL_ERROR"


def test_save_unique_violation_on_insert_maps_to_409_never_500() -> None:
    # `remaining=[None]` -- `add()` raises on every attempt (spec's
    # "Persistent violation still yields 409"): SavePhrase's bounded retry
    # (Unit 3) is exhausted and falls back to `_forced_conflict`, which must
    # still resolve to 409, never propagate as an unhandled 500.
    inner_factory = InMemoryUnitOfWorkFactory()
    remaining: list[int | None] = [None]
    error = DuplicateTextConflict(_QUERY_TEXT)
    factory = ProxyUnitOfWorkFactory(
        inner_factory, lambda repo: ConflictRepo(repo, remaining=remaining, error=error)
    )
    client, _, _ = _client(uow_factory=factory)  # type: ignore[arg-type]
    response = client.post("/phrases", json={"text": _QUERY_TEXT})
    assert response.status_code == 409
    assert response.json()["error"]["code"] == "DUPLICATE_CONFIRMATION_REQUIRED"


# --- GET /phrases (tasks.md 7b.1/7b.2) ------------------------------------


def test_list_phrases_empty_store() -> None:
    client, _, _ = _client()
    response = client.get("/phrases")
    assert response.status_code == 200
    assert response.json() == {"data": {"items": []}}


def test_list_phrases_newest_first_with_metadata() -> None:
    client, _, factory = _client()
    _seed(factory, ("a", 0.05), ("b", 0.10))  # ids 1, 2 -- both `unique`, null metadata
    response = client.get("/phrases")
    assert response.status_code == 200
    items = response.json()["data"]["items"]
    assert [item["text"] for item in items] == ["b", "a"]  # newest (highest id) first
    for item in items:
        assert set(item) == {"id", "text", "created_at", "validation"}
        assert set(item["validation"]) == {
            "status",
            "score",
            "most_similar_phrase_id",
            "validated_at",
        }
        assert item["validation"]["status"] == "unique"
        assert item["validation"]["score"] is None
        assert item["validation"]["most_similar_phrase_id"] is None


def test_list_phrases_hard_cap() -> None:
    client, _, factory = _client(phrases_list_limit=2)
    _seed(factory, *[(f"p{i}", 0.05 + i * 0.001) for i in range(5)])
    response = client.get("/phrases")
    assert response.status_code == 200
    items = response.json()["data"]["items"]
    assert len(items) == 2
    assert [item["text"] for item in items] == ["p4", "p3"]  # newest first, capped
