---
id: ADR-007
title: Keyset pagination for stable page semantics, re-embed per page
type: technical
---

# ADR-007: Keyset pagination, re-embedded per page

Re-embed per page for stateless match pagination; **keyset (never
`OFFSET`) for stable page semantics, not for speed** — `find_matches` is an
exact O(n) scan; keyset positions are `(floor(distance / 1e-6), id)` so a
recomputed query vector that drifts by an ulp neither repeats nor skips
rows (D16). Opaque cursor with strict field validation and a size cap; `400
INVALID_CURSOR` on any violation, or a cursor issued for a different
comparison form or threshold, decided **before** any embedding. Efficiency
of the re-embed is ADR-011's subject (the embedding cache), not a
weakening of this one.
