"""`app.main` builds `Settings()` (no default for `DATABASE_URL`) at IMPORT
time (design.md's fail-fast intent). Supplies one harmless value before any
contract test imports `app.main`.

The placeholder cannot simply be left in place after collection: pytest
imports every `conftest.py` and test module during collection, before any
marker filtering happens, so this line always runs even for a `-m
integration`-only invocation. `tests/integration/*`'s own `database_url`
fixtures read `os.environ.get("DATABASE_URL", <real default>)` lazily, at
fixture-setup time -- which happens after collection finishes. Left
unattended, the placeholder set here would win over their real default and
every integration test would try to connect as the fake `contract` role.
`pytest_collection_finish` runs once collection is complete, before any
fixture executes, so removing the placeholder there closes the window
without affecting `tests/contract/*` itself (its `app.main` imports already
ran during collection, placeholder value and all).

Cross-reference (fix-pass, review finding #5): `tests/integration/
test_endpoints_pgvector.py` ALSO sets `DATABASE_URL` at module scope (via
`os.environ.setdefault`, a real dev-DB default, not a placeholder -- it never
cleans up after itself since there's nothing fake to leak). This module and
that one are unaware of each other; their combined behaviour depends on
pytest's collection order (whichever runs first wins, via `setdefault`/the
membership check above). Currently harmless: both fallback values are
legitimate for their own module, and `tests/contract/*` never reads
`Settings.database_url` for real I/O (every contract test overrides
`Settings` with its own DSN before use). Fragile if that assumption ever
changes -- see `test_endpoints_pgvector.py`'s own cross-reference comment.
"""

import os

_DATABASE_URL_VAR = "DATABASE_URL"
_PLACEHOLDER = "postgresql+psycopg://contract:contract@localhost:5432/contract"

_we_set_it = _DATABASE_URL_VAR not in os.environ
if _we_set_it:
    os.environ[_DATABASE_URL_VAR] = _PLACEHOLDER


def pytest_collection_finish(session):  # noqa: ARG001 -- required pytest hook signature
    if _we_set_it and os.environ.get(_DATABASE_URL_VAR) == _PLACEHOLDER:
        del os.environ[_DATABASE_URL_VAR]
