"""Unit 6b.2 contract tests: `POST /phrases/validate` + `GET /health`,
against the real `create_app()` wiring, with fakes and the in-memory repo
wired directly onto `app.state` (`main.py`'s production app leaves these
unset/not-ready until Unit 8) -- same precedent as `test_framework_errors.py`.
"""

from __future__ import annotations

from dataclasses import asdict
from datetime import UTC, datetime

import pytest
from fastapi.testclient import TestClient

from app.main import create_app
from app.modules.phrases.adapters.in_memory_repository import InMemoryUnitOfWorkFactory
from app.modules.phrases.container import build_phrases_container
from app.modules.phrases.contracts import NewPhrase, UnitOfWorkFactory, ValidationStatus
from app.modules.similarity.adapters.caching import CachingEmbeddingProvider
from app.modules.similarity.adapters.failing import FailingEmbedder
from app.modules.similarity.adapters.fake import FakeEmbedder
from app.modules.similarity.contracts import (
    EmbeddingProvider,
    EmbeddingTimeout,
    EmbeddingUnavailable,
    SimilarityPolicy,
)
from app.platform.health import HealthState
from app.platform.settings import Settings
from tests.contract_suite.vectors import PROBE, vector_at_distance

pytestmark = pytest.mark.contract

_QUERY_TEXT = "query text"


def _client(
    *,
    embedder: EmbeddingProvider | None = None,
    uow_factory: UnitOfWorkFactory | None = None,
    cache_capacity: int = 512,
    model_ready: bool = True,
    database_ok: bool = True,
    matches_page_size: int = 50,
) -> tuple[TestClient, EmbeddingProvider, UnitOfWorkFactory]:
    settings = Settings(
        database_url="postgresql+psycopg://test:test@localhost:5432/test",
        matches_page_size=matches_page_size,
    )
    app = create_app(settings)

    inner = embedder if embedder is not None else FakeEmbedder({_QUERY_TEXT: PROBE})
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
    )

    def _cache_snapshot() -> dict[str, int] | None:
        return asdict(wrapped.stats) if isinstance(wrapped, CachingEmbeddingProvider) else None

    app.state.health = HealthState(
        check_database=lambda: database_ok,
        model_ready=model_ready,
        dimensions=settings.embedding_dimensions,
        embedding_model=settings.embedding_model,
        embedding_cache=_cache_snapshot,
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


# --- POST /phrases/validate -------------------------------------------------


def test_duplicate_found_returns_the_full_verdict_payload() -> None:
    client, _, factory = _client()
    _seed(factory, ("existing", 0.05))  # score 0.95, duplicate at t=0.80
    # A `cursor` key is included to prove it is silently ignored, not rejected.
    response = client.post(
        "/phrases/validate", json={"text": _QUERY_TEXT, "cursor": "not-a-real-cursor"}
    )
    assert response.status_code == 200
    assert set(response.json()) == {"data"}  # success envelope
    data = response.json()["data"]
    assert data["is_duplicate"] is True
    assert data["threshold"] == 0.80
    assert data["score"] == 0.95
    assert data["most_similar"] == {"id": "1", "text": "existing", "score": 0.95}
    assert data["matches"] == [{"id": "1", "text": "existing", "score": 0.95}]
    assert data["has_more"] is False
    assert data["next_cursor"] is None
    with factory(read_only=True) as uow:  # type: ignore[operator]
        assert len(uow.repo.list_recent(10)) == 1  # nothing new persisted


def test_empty_store_returns_a_null_verdict() -> None:
    client, _, _ = _client()
    response = client.post("/phrases/validate", json={"text": _QUERY_TEXT})
    assert response.status_code == 200
    assert response.json()["data"] == {
        "is_duplicate": False,
        "threshold": 0.80,
        "score": None,
        "most_similar": None,
        "matches": [],
        "next_cursor": None,
        "has_more": False,
        "total": 0,
    }


def test_page_1_carries_the_verdict_using_the_default_limit() -> None:
    # No `limit` in the body -> defaults to `matches_page_size` (design.md's
    # request-shape table), proving "Default limit" and "Page 1 carries the
    # verdict" together.
    client, _, factory = _client(matches_page_size=2)
    _seed(factory, ("a", 0.01), ("b", 0.02), ("c", 0.03))
    response = client.post("/phrases/validate", json={"text": _QUERY_TEXT})
    data = response.json()["data"]
    assert data["is_duplicate"] is True
    assert len(data["matches"]) == 2
    assert data["has_more"] is True
    assert data["next_cursor"] is not None


@pytest.mark.parametrize(
    ("limit", "expected_status", "expected_count"),
    [(1, 200, 1), (2, 200, 2), (0, 422, None), (3, 422, None)],
)
def test_limit_bounds_are_enforced_inclusively(
    limit: int, expected_status: int, expected_count: int | None
) -> None:
    client, _, factory = _client(matches_page_size=2)
    _seed(factory, ("a", 0.01), ("b", 0.02))
    response = client.post("/phrases/validate", json={"text": _QUERY_TEXT, "limit": limit})
    assert response.status_code == expected_status
    body = response.json()
    if expected_status == 200:
        assert len(body["data"]["matches"]) == expected_count
    else:
        assert body["error"]["details"]["fields"][0]["reason"] == "out_of_range"


@pytest.mark.parametrize("bad_limit", ["10", True, 10.5])
def test_strict_integer_limit_rejects_non_strict_values(bad_limit: object) -> None:
    client, _, _ = _client()
    response = client.post("/phrases/validate", json={"text": _QUERY_TEXT, "limit": bad_limit})
    assert response.status_code == 422
    assert response.json()["error"]["details"]["fields"][0]["reason"] == "invalid_type"


def test_database_unreachable_outside_health_is_500_internal_error() -> None:
    def _broken(*, isolation: object = None, read_only: bool = False) -> None:
        raise RuntimeError("connection refused")

    client, _, _ = _client(uow_factory=_broken)  # type: ignore[arg-type]
    response = client.post("/phrases/validate", json={"text": _QUERY_TEXT})
    assert response.status_code == 500
    assert response.json()["error"]["code"] == "INTERNAL_ERROR"


@pytest.mark.parametrize(
    ("error", "status_code", "code"),
    [
        (EmbeddingUnavailable(), 503, "EMBEDDING_UNAVAILABLE"),
        (EmbeddingTimeout(), 504, "EMBEDDING_TIMEOUT"),
    ],
)
def test_provider_failure_and_timeout_map_to_their_registered_codes(
    error: Exception, status_code: int, code: str
) -> None:
    failing = FailingEmbedder(FakeEmbedder({_QUERY_TEXT: PROBE}), fail_times=None, error=error)
    client, _, _ = _client(embedder=failing, cache_capacity=0)
    response = client.post("/phrases/validate", json={"text": _QUERY_TEXT})
    assert response.status_code == status_code
    assert response.json()["error"]["code"] == code


def test_cold_and_warm_validate_responses_are_byte_identical() -> None:
    client, embedder, factory = _client(cache_capacity=512)
    _seed(factory, ("existing", 0.05))
    first = client.post("/phrases/validate", json={"text": _QUERY_TEXT})
    second = client.post("/phrases/validate", json={"text": _QUERY_TEXT})
    assert first.content == second.content
    assert embedder.call_count == 1  # cold miss, then a cache hit


# --- GET /health --------------------------------------------------------


def test_health_ready_returns_every_required_key_and_issues_zero_embeddings() -> None:
    client, embedder, _ = _client()
    response = client.get("/health")
    assert response.status_code == 200
    data = response.json()["data"]
    assert data["status"] == "ok"
    assert data["database"] == "ok"
    assert data["model"] == "ready"
    assert data["dimensions"] == 384
    assert data["embedding_model"]
    assert set(data["embedding_cache"]) == {"hits", "misses", "evictions", "size", "capacity"}
    assert embedder.call_count == 0


@pytest.mark.parametrize(
    ("model_ready", "database_ok", "expected_model", "expected_database"),
    [(False, True, "unavailable", "ok"), (True, False, "ready", "unavailable")],
)
def test_health_not_ready_reports_which_component_is_down(
    model_ready: bool, database_ok: bool, expected_model: str, expected_database: str
) -> None:
    client, _, _ = _client(model_ready=model_ready, database_ok=database_ok)
    response = client.get("/health")
    assert response.status_code == 503
    body = response.json()
    assert body["error"]["code"] == "NOT_READY"
    assert body["error"]["details"]["model"] == expected_model
    assert body["error"]["details"]["database"] == expected_database
