"""Unit 6.3: framework-level error handling and CORS, against the real
`create_app()` wiring. Settles design.md's "from memory" Starlette
handler/middleware-order uncertainty (last test below). No business
endpoint exists yet, so this file registers throwaway probe routes
directly on the app under test -- never the shared `app.main.app`.
"""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient
from pydantic import BaseModel

from app.main import create_app
from app.modules.phrases.api.schemas import raw_phrase_text
from app.platform.settings import Settings

pytestmark = pytest.mark.contract

_ORIGIN = "http://localhost:3000"
_DISALLOWED_ORIGIN = "http://evil.example"


class _Probe(BaseModel):
    text: str


class _RawTextProbe(BaseModel):
    text: raw_phrase_text(280)  # type: ignore[valid-type]


# Both probe models MUST live at module scope, not nested inside `_client()`:
# with `from __future__ import annotations` active, a route function's
# parameter annotations are unevaluated strings, and FastAPI/pydantic resolve
# them via the function's `__globals__` only (never the enclosing closure's
# locals). A locally-scoped model class is therefore unresolvable and FastAPI
# silently falls back to treating the parameter as a query param named
# "body" instead of a JSON body model -- a real bug caught while writing this
# file's newest test (it produced `{"field": "query", "reason": "required"}`
# instead of validating `text` at all). The pre-existing `/probe` route
# happened to never expose this because `test_malformed_json_is_422_
# validation_error` posts genuinely malformed JSON, which 422s during
# parsing itself, before the route's parameter types are ever consulted.


def _client(*, max_request_bytes: int = 1_048_576) -> TestClient:
    settings = Settings(
        database_url="postgresql+psycopg://test:test@localhost:5432/test",
        cors_origins=_ORIGIN,
        max_request_bytes=max_request_bytes,
    )
    app = create_app(settings)

    @app.get("/phrases")
    def _list_phrases() -> dict[str, object]:
        return {"data": []}

    @app.post("/probe")
    def _probe(body: _Probe) -> dict[str, object]:
        return {"data": body.text}

    @app.post("/probe-raw-text")
    def _probe_raw_text(body: _RawTextProbe) -> dict[str, object]:
        return {"data": body.text}

    @app.get("/boom")
    def _boom() -> None:
        raise RuntimeError("deliberate failure for the contract test")

    return TestClient(app, raise_server_exceptions=False)


def test_unknown_route_is_404_not_found() -> None:
    response = _client().get("/nope")
    assert response.status_code == 404
    assert response.json()["error"]["code"] == "NOT_FOUND"


def test_wrong_method_on_a_known_route_is_405_method_not_allowed() -> None:
    response = _client().delete("/phrases")
    assert response.status_code == 405
    assert response.json()["error"]["code"] == "METHOD_NOT_ALLOWED"


def test_unhandled_exception_is_500_internal_error_with_no_stack_trace() -> None:
    response = _client().get("/boom")
    assert response.status_code == 500
    assert response.json()["error"]["code"] == "INTERNAL_ERROR"
    assert "RuntimeError" not in response.text
    assert "Traceback" not in response.text


def test_malformed_json_is_422_validation_error() -> None:
    response = _client().post(
        "/probe", content=b"{not json", headers={"Content-Type": "application/json"}
    )
    assert response.status_code == 422
    assert response.json()["error"]["code"] == "VALIDATION_ERROR"


def test_oversized_body_is_413_payload_too_large() -> None:
    response = _client(max_request_bytes=4096).post("/probe", content=b"x" * 5000)
    assert response.status_code == 413
    assert response.json()["error"]["code"] == "PAYLOAD_TOO_LARGE"


def test_raw_length_cap_is_422_too_long_with_max_length_detail() -> None:
    """api-contract spec's "Raw length cap" scenario: a raw string over
    `4 * PHRASE_MAX_LENGTH` code points must be 422 `VALIDATION_ERROR` with
    `details.fields[0].reason == "too_long"` and `details.max_length ==
    PHRASE_MAX_LENGTH` (design.md line 937), NOT the generic
    `invalid_type` fallback with no detail."""
    response = _client().post("/probe-raw-text", json={"text": "a" * 1121})
    assert response.status_code == 422
    body = response.json()
    assert body["error"]["code"] == "VALIDATION_ERROR"
    assert body["error"]["details"]["fields"][0]["reason"] == "too_long"
    assert body["error"]["details"]["max_length"] == 280


def test_allowed_origin_is_echoed_on_a_normal_response() -> None:
    response = _client().get("/phrases", headers={"Origin": _ORIGIN})
    assert response.headers["access-control-allow-origin"] == _ORIGIN


def test_disallowed_origin_has_no_cors_header() -> None:
    response = _client().get("/phrases", headers={"Origin": _DISALLOWED_ORIGIN})
    assert "access-control-allow-origin" not in response.headers


def test_preflight_from_an_allowed_origin_is_accepted() -> None:
    response = _client().options(
        "/phrases",
        headers={
            "Origin": _ORIGIN,
            "Access-Control-Request-Method": "POST",
            "Access-Control-Request-Headers": "content-type",
        },
    )
    assert response.status_code == 200
    assert response.headers["access-control-allow-origin"] == _ORIGIN
    assert "POST" in response.headers["access-control-allow-methods"]
    assert "content-type" in response.headers["access-control-allow-headers"].lower()
    assert "access-control-allow-credentials" not in response.headers


def test_preflight_from_a_disallowed_origin_is_rejected() -> None:
    response = _client().options(
        "/phrases",
        headers={
            "Origin": _DISALLOWED_ORIGIN,
            "Access-Control-Request-Method": "POST",
        },
    )
    assert "access-control-allow-origin" not in response.headers


def test_a_forced_500_for_an_allowed_origin_still_carries_cors_headers() -> None:
    """`ServerErrorMiddleware` sits OUTSIDE every user middleware, so this
    only passes if `CatchAllMiddleware` is positioned INSIDE `CORSMiddleware`
    -- see `create_app`'s middleware registration order."""
    response = _client().get("/boom", headers={"Origin": _ORIGIN})
    assert response.status_code == 500
    assert response.headers["access-control-allow-origin"] == _ORIGIN
