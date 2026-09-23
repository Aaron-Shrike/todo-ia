---
id: ADR-012
title: Two questions, two reads, one reconciliation rule
type: technical
---

# ADR-012: Two questions, two reads, one reconciliation rule

**Two questions, distinct reads.** `find_nearest` (unfiltered top-1, HNSW,
validate only) answers *what is the closest phrase* and `find_matches`
(threshold-filtered keyset, exact scan) answers *which phrases are
duplicates*; validate runs both in one `REPEATABLE READ` snapshot and takes
`score`/`most_similar` from `matches[0]` whenever matches exist
(reconciliation rule). Save asks the first question through
`find_nearest_exact` (the exact twin, no HNSW) and runs `find_matches` only
when it must build a 409 body. This is what makes a below-threshold
`most_similar` reportable — and recordable on the saved row — instead of
silently null. Rejected: one `find_matches(max_distance=1.0, limit=1)`
doing double duty.
