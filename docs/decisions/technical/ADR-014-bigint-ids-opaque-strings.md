---
id: ADR-014
title: BIGINT ids inside, opaque strings on the wire
type: technical
---

# ADR-014: `BIGINT` ids inside, opaque strings on the wire

Ids are `BIGINT` inside and opaque strings on the wire, because JavaScript
cannot safely hold the full range and a string id keeps a future
UUID/ULID switch out of the contract.
