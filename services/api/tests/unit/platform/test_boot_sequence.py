"""Unit tests for `platform/boot_sequence.py::run_boot_sequence` (Unit 8
fix-pass, reliability CRITICAL finding #2). `main.py::_lifespan` used to mix
pure sequencing decisions with concrete I/O (real `create_engine`, real
`PgVectorUnitOfWorkFactory`) in one function body with lazy inline imports --
untestable even with fakes, since importing `app.main` at all needs
`sqlalchemy` installed (confirmed absent in this dev venv). `run_boot_
sequence` has NO such dependency: every step is an injected callable, so the
documented order -- load the model, check dimensions (a mismatch
short-circuits everything after it), warm up, build the container/flip
health -- is fully unit-testable here with plain fakes. `main.py::_lifespan`
is the thin wrapper that supplies the REAL callables; the real sqlalchemy/
postgres calls THEMSELVES remain genuinely untested (no docker/live Postgres
in this environment -- documented, not faked into false confidence, in
apply-progress.md's Unit 8 section).
"""

from __future__ import annotations

import pytest

from app.platform.boot_sequence import run_boot_sequence

pytestmark = pytest.mark.unit


class _DimensionMismatch(Exception):
    """Stands in for `platform.embedding_boot.EmbeddingDimensionMismatch`."""


def test_the_happy_path_calls_every_step_in_the_documented_order() -> None:
    calls: list[str] = []

    def load_model() -> str:
        calls.append("load_model")
        return "provider"

    def check_dimensions(provider: str) -> None:
        calls.append(f"check_dimensions({provider})")

    def warmup(provider: str) -> None:
        calls.append(f"warmup({provider})")

    def build_container(provider: str) -> str:
        calls.append(f"build_container({provider})")
        return "container"

    result = run_boot_sequence(
        load_model=load_model,
        check_dimensions=check_dimensions,
        warmup=warmup,
        build_container=build_container,
    )

    assert result == "container"
    assert calls == [
        "load_model",
        "check_dimensions(provider)",
        "warmup(provider)",
        "build_container(provider)",
    ]


def test_a_dimension_mismatch_short_circuits_warmup_and_build_container() -> None:
    warmup_called = False
    build_container_called = False

    def load_model() -> str:
        return "provider"

    def check_dimensions(provider: str) -> None:
        raise _DimensionMismatch("typmod/provider/configured disagree")

    def warmup(provider: str) -> None:
        nonlocal warmup_called
        warmup_called = True

    def build_container(provider: str) -> str:
        nonlocal build_container_called
        build_container_called = True
        return "container"

    with pytest.raises(_DimensionMismatch):
        run_boot_sequence(
            load_model=load_model,
            check_dimensions=check_dimensions,
            warmup=warmup,
            build_container=build_container,
        )

    assert warmup_called is False
    assert build_container_called is False


def test_the_loaded_provider_flows_unchanged_into_every_later_step() -> None:
    # Sequencing invariant (c): the SAME object `load_model` returns is the
    # one passed to `check_dimensions`, `warmup`, AND `build_container` --
    # not a re-derived or partially-applied one.
    sentinel = object()
    seen: list[object] = []

    def load_model() -> object:
        return sentinel

    def check_dimensions(provider: object) -> None:
        seen.append(provider)

    def warmup(provider: object) -> None:
        seen.append(provider)

    def build_container(provider: object) -> object:
        seen.append(provider)
        return "container"

    run_boot_sequence(
        load_model=load_model,
        check_dimensions=check_dimensions,
        warmup=warmup,
        build_container=build_container,
    )

    assert seen == [sentinel, sentinel, sentinel]


@pytest.mark.parametrize("failing_step", ["load_model", "warmup", "build_container"])
def test_a_failure_in_any_step_propagates_and_stops_the_sequence(failing_step: str) -> None:
    # Triangulation: the short-circuit contract is not special-cased to
    # `check_dimensions` alone -- a failure at ANY step propagates instead
    # of being swallowed, and no LATER step ever runs.
    calls: list[str] = []

    def load_model() -> str:
        calls.append("load_model")
        if failing_step == "load_model":
            raise RuntimeError("boom")
        return "provider"

    def check_dimensions(provider: str) -> None:
        calls.append("check_dimensions")

    def warmup(provider: str) -> None:
        calls.append("warmup")
        if failing_step == "warmup":
            raise RuntimeError("boom")

    def build_container(provider: str) -> str:
        calls.append("build_container")
        if failing_step == "build_container":
            raise RuntimeError("boom")
        return "container"

    with pytest.raises(RuntimeError):
        run_boot_sequence(
            load_model=load_model,
            check_dimensions=check_dimensions,
            warmup=warmup,
            build_container=build_container,
        )

    assert failing_step in calls
    assert calls[-1] == failing_step  # nothing after the failing step ran
