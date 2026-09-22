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
from app.platform.settings import Settings

pytestmark = pytest.mark.contract

_ORIGIN = "http://localhost:3000"
_DISALLOWED_ORIGIN = "http://evil.example"


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

    class _Probe(BaseModel):
        text: str

    @app.post("/probe")
    def _probe(body: _Probe) -> dict[str, object]:
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
