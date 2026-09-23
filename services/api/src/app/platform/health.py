"""`GET /health` readiness (tasks.md 6b.1, design.md's "GET /health
(readiness)"). The handler ONLY reads `request.app.state.health` -- it
issues ZERO embeddings by construction (nothing here can reach an
`EmbeddingProvider`); the model is warmed once, in `main.py`'s lifespan
hook, never per request. `embedding_cache` is a plain `dict` (not
`similarity`'s `CacheStats`) so `platform` never imports a `similarity`
adapter -- the composition root does that translation.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass

from fastapi import APIRouter, Request
from starlette.responses import JSONResponse

from app.platform.errors import error_envelope


@dataclass(frozen=True)
class HealthState:
    """Assembled once by `main.py`'s lifespan hook or a test's own setup."""

    check_database: Callable[[], bool]
    model_ready: bool
    dimensions: int
    embedding_model: str
    embedding_cache: Callable[[], dict[str, int] | None]


def build_health_payload(state: HealthState) -> tuple[int, dict[str, object]]:
    """`model` is the readiness string; 200 only when DB and model are both
    ready, else 503 `NOT_READY` with per-component `details`.

    Fix-pass finding #3 (resilience WARNING): `state.check_database()` used
    to be called with no `try`/`except` around it. The real production
    implementation (`platform/embedding_boot.py::check_database_reachable`)
    only ever catches `sqlalchemy.exc.OperationalError` and lets any other
    exception propagate -- a sibling connectivity failure (pool-exhaustion
    `TimeoutError`, a driver `InterfaceError`) would fall through this
    handler uncaught, straight to `main.py`'s generic `CatchAllMiddleware`,
    producing a `500 INTERNAL_ERROR` instead of the designed `503 NOT_READY`
    diagnostic contract (D15). ANY exception from the check -- not just a
    `bool` `False` -- now maps to `database: "unavailable"`, so `/health`
    always tells a caller WHICH dependency is down instead of crashing."""
    try:
        database_ok = state.check_database()
    except Exception:
        database_ok = False
    model = "ready" if state.model_ready else "unavailable"
    if database_ok and state.model_ready:
        data: dict[str, object] = {
            "status": "ok",
            "database": "ok",
            "model": model,
            "dimensions": state.dimensions,
            "embedding_model": state.embedding_model,
        }
        cache = state.embedding_cache()
        if cache is not None:
            data["embedding_cache"] = cache
        return 200, {"data": data}

    details: dict[str, object] = {
        "database": "ok" if database_ok else "unavailable",
        "model": model,
        "dimensions": state.dimensions,
        "embedding_model": state.embedding_model,
    }
    return 503, error_envelope("NOT_READY", "service is not ready", details)


router = APIRouter()


@router.get("/health")
def get_health(request: Request) -> JSONResponse:
    status_code, body = build_health_payload(request.app.state.health)
    return JSONResponse(status_code=status_code, content=body)
