"""Unit tests for `platform/health.py::build_health_payload` (Unit 8
fix-pass, resilience WARNING finding #3). `HealthState.check_database` is a
plain `Callable[[], bool]` -- the real production implementation
(`platform/embedding_boot.py::check_database_reachable`) only ever RETURNS
`False`, never raises (it catches `OperationalError` internally), but a
sibling SQLAlchemy exception (`sqlalchemy.exc.TimeoutError` from
connection-pool exhaustion, a driver-specific `InterfaceError`) used to
propagate straight through `build_health_payload` with no `try`/`except`
around the call, past `health.py`'s router, all the way to `main.py`'s
generic `CatchAllMiddleware` -- producing a `500 INTERNAL_ERROR` instead of
the designed `503 NOT_READY` + per-component `details` (design.md D15).
These tests use a plain fake `check_database` that raises a non-
`OperationalError` exception -- proving the fix at the `build_health_payload`
call site, independent of which SQLAlchemy exception type a real connectivity
failure happens to raise.
"""

from __future__ import annotations

import pytest

from app.platform.health import HealthState, build_health_payload

pytestmark = pytest.mark.unit

_DIMENSIONS = 384
_EMBEDDING_MODEL = "org/checkpoint"


def _state(*, check_database: object, model_ready: bool = True) -> HealthState:
    return HealthState(
        check_database=check_database,  # type: ignore[arg-type]
        model_ready=model_ready,
        dimensions=_DIMENSIONS,
        embedding_model=_EMBEDDING_MODEL,
        embedding_cache=lambda: None,
    )


def test_database_check_raising_a_non_operational_error_still_yields_not_ready() -> None:
    class _ConnectionPoolExhausted(Exception):
        """Stands in for `sqlalchemy.exc.TimeoutError` -- a real
        connectivity failure that is NOT an `OperationalError`."""

    def _raising() -> bool:
        raise _ConnectionPoolExhausted("pool exhausted")

    status_code, body = build_health_payload(_state(check_database=_raising))

    assert status_code == 503
    assert body["error"]["code"] == "NOT_READY"
    assert body["error"]["details"]["database"] == "unavailable"


def test_database_check_raising_still_reports_model_ready_state_in_details() -> None:
    # Triangulation: a DIFFERENT exception type and a DIFFERENT model_ready
    # value than the first test, proving the fix generalizes rather than
    # special-casing one exception class.
    class _DriverInterfaceError(Exception):
        """Stands in for a driver-specific `InterfaceError`."""

    def _raising() -> bool:
        raise _DriverInterfaceError("driver gone away")

    status_code, body = build_health_payload(_state(check_database=_raising, model_ready=False))

    assert status_code == 503
    assert body["error"]["details"]["database"] == "unavailable"
    assert body["error"]["details"]["model"] == "unavailable"


def test_database_check_returning_true_still_reports_ready_as_before() -> None:
    # Safety net / approval test: the non-raising path must keep behaving
    # exactly as it did before this fix.
    status_code, body = build_health_payload(_state(check_database=lambda: True))

    assert status_code == 200
    assert body["data"]["status"] == "ok"
    assert body["data"]["database"] == "ok"
