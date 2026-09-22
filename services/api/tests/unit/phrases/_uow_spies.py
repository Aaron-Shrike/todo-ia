"""Test-only `UnitOfWorkFactory`/`PhraseRepository` proxies shared by
`test_validate_phrase.py` and `test_save_phrase.py` (Unit 3). Not in
tasks.md's literal file list -- added for the same reason Unit 1 added
`tests/unit/__init__.py` files: avoids re-implementing the same
proxy/counting plumbing per test file. Wraps the real
`InMemoryUnitOfWorkFactory` instead of hand-rolling a second fake
repository, so the wrapped methods stay behind the real ones.
"""

from __future__ import annotations

from typing import Any


class _RepoProxy:
    """Delegates every method to `inner` unless overridden below."""

    def __init__(self, inner: Any) -> None:
        self._inner = inner

    def __getattr__(self, name: str) -> Any:
        return getattr(self._inner, name)


class WrongNearestRepo(_RepoProxy):
    """`find_nearest` always returns a fixed, deliberately WRONG neighbour
    -- proves `ValidatePhrase`'s reconciliation rule prefers `matches[0]`
    (design.md's "Reconciliation rule")."""

    def __init__(self, inner: Any, neighbor: Any) -> None:
        super().__init__(inner)
        self._neighbor = neighbor

    def find_nearest(self, q: Any) -> Any:
        return self._neighbor


class CountingRepo(_RepoProxy):
    """Counts calls to the three read methods -- proves `SavePhrase` never
    calls `find_nearest` (design.md Guard 2b) and that both `ValidatePhrase`
    and `ListMatches` issue a live `find_matches` per call, cache or not."""

    def __init__(self, inner: Any) -> None:
        super().__init__(inner)
        self.find_matches_calls = 0
        self.find_nearest_calls = 0
        self.find_nearest_exact_calls = 0

    def find_matches(self, *args: Any, **kwargs: Any) -> Any:
        self.find_matches_calls += 1
        return self._inner.find_matches(*args, **kwargs)

    def find_nearest(self, *args: Any, **kwargs: Any) -> Any:
        self.find_nearest_calls += 1
        return self._inner.find_nearest(*args, **kwargs)

    def find_nearest_exact(self, *args: Any, **kwargs: Any) -> Any:
        self.find_nearest_exact_calls += 1
        return self._inner.find_nearest_exact(*args, **kwargs)


class ConflictRepo(_RepoProxy):
    """`add` raises `DuplicateTextConflict` for the first N calls (or
    forever, if `remaining[0] is None`), then delegates -- covers
    `SavePhrase`'s bounded-retry path (ADR-006). `remaining` is a shared,
    single-element list: `SavePhrase`'s retry opens a FRESH `UnitOfWork`
    (design.md), so a fresh `ConflictRepo` is constructed per `__enter__`
    (see `ProxyUnitOfWork`) -- the shared list is what makes the underlying
    "constraint" persist across that fresh transaction, the way a real
    unique-index violation would."""

    def __init__(self, inner: Any, *, remaining: list[int | None], error: Exception) -> None:
        super().__init__(inner)
        self._remaining = remaining
        self._error = error
        self.add_calls = 0

    def add(self, phrase: Any) -> Any:
        self.add_calls += 1
        n = self._remaining[0]
        if n is None or n > 0:
            if n is not None:
                self._remaining[0] = n - 1
            raise self._error
        return self._inner.add(phrase)


class ProxyUnitOfWork:
    def __init__(self, inner: Any, wrap: Any) -> None:
        self._inner = inner
        self._wrap = wrap
        self.repo: Any = None

    def __enter__(self) -> ProxyUnitOfWork:
        self._inner.__enter__()
        self.repo = self._wrap(self._inner.repo)
        return self

    def __exit__(self, *exc: Any) -> None:
        self._inner.__exit__(*exc)

    def commit(self) -> None:
        self._inner.commit()

    def rollback(self) -> None:
        self._inner.rollback()


class ProxyUnitOfWorkFactory:
    """Wraps an `InMemoryUnitOfWorkFactory`, replacing `.repo` on every
    `__enter__` with `wrap(repo)` -- same store, spied methods."""

    def __init__(self, inner_factory: Any, wrap: Any) -> None:
        self._inner_factory = inner_factory
        self._wrap = wrap

    def __call__(self, **kwargs: Any) -> ProxyUnitOfWork:
        return ProxyUnitOfWork(self._inner_factory(**kwargs), self._wrap)
