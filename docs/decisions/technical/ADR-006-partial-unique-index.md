---
id: ADR-006
title: Partial unique index on normalized_text for identity integrity
type: technical
---

# ADR-006: Partial unique index on `normalized_text`

**ADOPTED**: a partial unique index on `normalized_text` `WHERE
validation_status = 'unique'`, on top of the advisory lock. Supersedes the
earlier "no unique index" decision without contradicting its rationale
(confirmed duplicates are outside the index and stay allowed; an
unconfirmed identical text is never inserted as `unique` because the
server returns 409).

This is integrity, not performance: it makes "no unconfirmed identical
phrase is stored twice" a database guarantee. A unique violation maps to a
single bounded retry, in a fresh transaction, that lands on the normal 409
`DUPLICATE_CONFIRMATION_REQUIRED` path, never a 500. Semantic
(non-identical) near-duplicates are not covered; that residual race is
documented in the Concurrency section.
