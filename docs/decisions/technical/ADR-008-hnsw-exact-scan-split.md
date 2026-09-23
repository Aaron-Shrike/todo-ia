---
id: ADR-008
title: HNSW only for find_nearest, exact scans for find_matches and save
type: technical
---

# ADR-008: HNSW only for `find_nearest`, exact scans elsewhere

HNSW **only for the unfiltered top-1 `find_nearest` of the validate
endpoint**; the threshold-filtered, paginated `find_matches` is an **exact
scan** (`enable_indexscan` off per transaction) because HNSW applies
`WHERE` after a bounded candidate window and would silently truncate the
match list.

**The write path is exact too:** `SavePhrase` derives its verdict and
recorded metadata from `find_nearest_exact` (an exact single-row scan with
the same planner settings as `find_matches`, inside the save transaction
under the advisory lock), never from HNSW, because an approximate recall
miss on save could store a duplicate as `unique`; the cost is one O(n) scan
per save, accepted at this scale (correctness of the write path over a
small cost, consistent with using exact scans wherever completeness
matters), and the scaling path is deferred. Non-vacuous recall/`EXPLAIN`
guards (corpus larger than `ef_search`, forced plan), plus save-path
`EXPLAIN`/spy and recall-miss tests.

## pgvector tag/version (measured, Unit 4, re-confirmed Unit 16)

`pgvector/pgvector:pg16` — **621 MB**, base Debian GNU/Linux 12 (bookworm),
Postgres **16.15**, extension version (`extversion`) **0.8.6**, well above
the 0.5.0 HNSW floor. Re-confirmed in Unit 16 against a fresh throwaway
container (`CREATE EXTENSION vector; SELECT extversion ...` → `0.8.6`).

## Exact-scan timings (measured, Unit 5a)

`docs/evidence/exact-scan-timings.md` records `EXPLAIN (ANALYZE, BUFFERS)`
against a seeded `phrases_test`: **500 rows → 0.529 ms**, **10,000 rows →
5.719 ms** execution time, both plans a `Seq Scan` feeding a bounded top-N
sort — no HNSW touched. Growth from 500 to 10,000 rows (20x) costs roughly
10.8x time, consistent with the O(n) cost model. This is a single local
run, single sample, no concurrent load — the evidence file itself flags
that a production-grade measurement should average several runs.

## Image-size notes

Shares the same measurement as ADR-003: `docker images todo-ia-api` (Unit
16) reports **10.4 GB disk usage / 4.4 GB content size** for
`todo-ia-api:latest`. This is the torch + sentence-transformers image the
write and read paths above both run inside; it is not a separate
pgvector-specific number, and it is not re-measured here to avoid
duplicating the same `docker images` call.

## Scaling path (verified to exist, still deferred)

pgvector >= 0.8 `hnsw.iterative_scan = strict_order` with a raised
`hnsw.max_scan_tuples` is the documented scaling path for `find_nearest`,
not adopted in this change. Unit 16 ran `SHOW hnsw.iterative_scan;`
against a fresh `pgvector/pgvector:pg16` container (extension loaded in the
same session first, since pgvector's GUCs are only registered once its
library is loaded into that backend) — the GUC **exists** on this image's
extension version (0.8.6) and its **default value is `off`**. This
confirms the setting is available should the scaling path ever be adopted;
it does not verify recall/latency behaviour under `strict_order`, which
stays unmeasured and deferred.
