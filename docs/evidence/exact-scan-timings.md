# Exact-scan `find_matches` timings (tasks.md 5a.3)

Raw `EXPLAIN (ANALYZE, BUFFERS)` measurements for `find_matches`'s exact
scan (`enable_indexscan = off`, page 1, `limit = 50`, `max_distance = 1.0`)
against `phrases_test`, run locally via `docker compose up -d db migrate`
(pgvector/pgvector:pg16, Postgres 16.15, extversion 0.8.6 — same image as
Unit 4's `4.0` measurement). Input for ADR-008 (Unit 16); not a pytest
assertion, an estimate per tasks.md's "VERIFY (estimate)" wording.

Fixture: N synthetic rows at evenly spread, grid-edge-avoiding distances
(`vector_at_distance`, 384-dim, zero-padded — same helper the contract
suite uses), queried against `PROBE`.

## N = 500

```
Limit  (cost=220.78..220.90 rows=51 width=56) (actual time=0.473..0.481 rows=51 loops=1)
  ->  Sort  (cost=220.78..224.19 rows=1367 width=56) (actual time=0.472..0.475 rows=51 loops=1)
        Sort Method: top-N heapsort  Memory: 28kB
        ->  Seq Scan on phrases  (cost=0.00..175.17 rows=1367 width=56) (actual time=0.009..0.367 rows=500 loops=1)
Planning Time: 0.312 ms
Execution Time: 0.529 ms
```

## N = 10,000

```
Limit  (cost=4415.22..4415.34 rows=51 width=56) (actual time=5.682..5.688 rows=51 loops=1)
  ->  Sort  (cost=4415.22..4483.55 rows=27333 width=56) (actual time=5.681..5.683 rows=51 loops=1)
        Sort Method: top-N heapsort  Memory: 28kB
        ->  Seq Scan on phrases  (cost=0.00..3503.33 rows=27333 width=56) (actual time=0.005..4.579 rows=10000 loops=1)
Planning Time: 0.138 ms
Execution Time: 5.719 ms
```

## Summary

| N | Plan | Execution Time |
| --- | --- | --- |
| 500 | `Seq Scan` + top-N heapsort, no HNSW | 0.529 ms |
| 10,000 | `Seq Scan` + top-N heapsort, no HNSW | 5.719 ms |

Both plans confirm `find_matches` never touches `phrases_embedding_hnsw_idx`
(D1/D8) — a `Seq Scan` feeding a bounded top-N sort, exactly design.md's
"sequential scan plus a top-N sort" description. Growth from 500 -> 10,000
rows (20x) is roughly linear (~10.8x execution time), consistent with the
documented O(n) cost model (design.md's "Honest cost model"): milliseconds
at 500 rows, low single-digit milliseconds at 10⁴ rows — well inside the
"milliseconds to tens of milliseconds" estimate design.md's Verification
Status table carried as unmeasured before this unit. One local run, single
sample, no concurrent load; a proper ADR-008 measurement (Unit 16) should
average several runs and note hardware.
