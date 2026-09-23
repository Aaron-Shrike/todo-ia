---
id: ADR-015
title: UnitOfWork port with two isolation levels
type: technical
---

# ADR-015: `UnitOfWork` port and two isolation levels

The application layer opens transactions through a port (isolation level,
commit, rollback), never through an adapter. Validate: `REPEATABLE READ
READ ONLY` (plain `READ ONLY` under `READ COMMITTED` would give each
statement its own snapshot). Save: `READ COMMITTED`, so the statement
after the advisory-lock wait sees the commit the lock waited for. A
bounded `lock_timeout` keeps a stuck holder from pinning every save.
