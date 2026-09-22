"""Test-only `UnitOfWorkFactory`/`PhraseRepository` proxies shared across
Unit 3's test files. Not in tasks.md's literal file list -- avoids
re-implementing the same proxy plumbing per test file. Wraps the real
`InMemoryUnitOfWorkFactory` instead of hand-rolling a second fake
repository, so the wrapped methods stay behind the real ones.

Grown incrementally as later Unit 3 sub-units need more doubles: this PR
(`feat/pv-03a-validate`) adds only what `test_validate_phrase.py` needs;
`feat/pv-03c-save` adds `CountingRepo`/`ConflictRepo` for `SavePhrase`.
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
