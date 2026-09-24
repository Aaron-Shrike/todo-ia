"""Advisory-lock helper (tasks.md 5b.2, design.md's module tree: "db.py --
engine, session, advisory-lock helper"). Only the lock helper lives here so
far -- engine/session construction needs `Settings.DATABASE_URL` (Unit 6),
out of scope here. Framework-light (plain `text()`, no settings import).
"""

from __future__ import annotations

from sqlalchemy import Connection, text

ADVISORY_LOCK_KEY = "phrases:validate_and_insert"
"""One global key (design.md D3): different-text near-duplicates make a
text-keyed lock pointless. A single key serializes all saves."""


def acquire_write_lock(connection: Connection, *, lock_timeout_ms: int) -> None:
    """`SET LOCAL lock_timeout` then `pg_advisory_xact_lock`, both via
    `set_config(..., true)` so they never leak across a pooled connection.
    Raises SQLSTATE `55P03` if the wait exceeds `lock_timeout_ms`; the
    caller maps that to `LockTimeout`."""
    connection.execute(
        text("SELECT set_config('lock_timeout', :ms, true)"), {"ms": str(lock_timeout_ms)}
    )
    connection.execute(
        text("SELECT pg_advisory_xact_lock(hashtext(:key))"), {"key": ADVISORY_LOCK_KEY}
    )
