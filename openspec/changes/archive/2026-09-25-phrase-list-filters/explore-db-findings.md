# Live DB findings: phrase-list-filters

Ran directly against the real running stack (`docker compose exec -T db psql
-U todo_ia -d todo_ia`), not simulated — the exploration sub-agent had no
Bash tool available and could not run this itself; the orchestrator ran it
after persisting `explore.md`.

## Row counts (real, as of this exploration)

```
 validation_status  | count
---------------------+-------
 unique              | 20001
 duplicate_confirmed |     3
---------------------+-------
 total               | 20004
```

Highly skewed: `duplicate_confirmed` is ~0.015% of the table. This is a
realistic shape for the actual feature (most users don't confirm a
duplicate), not an artifact of test seeding — it directly stress-tests the
"filter to a rare value" case that matters most for the index decision.

## EXPLAIN (ANALYZE, BUFFERS) — three queries, same shape as `list_page`'s
first-page query (`ORDER BY created_at DESC, id DESC LIMIT :limit+1`, no
cursor predicate — first page is also the cheapest case for any filter, so
these numbers are a floor, not a ceiling)

### Baseline — unfiltered (today's actual query)

```
Limit (actual time=0.057..0.084 rows=11 loops=1)
  Buffers: shared hit=6
  -> Index Only Scan using phrases_created_at_id_idx on phrases
       Heap Fetches: 6
Execution Time: 0.115 ms
```

Uses `phrases_created_at_id_idx` exactly as designed. 6 buffer hits.

### `WHERE validation_status = 'duplicate_confirmed'` (rare value, 3/20004 rows)

```
Limit (actual time=10.260..10.267 rows=3 loops=1)
  Buffers: shared hit=5007
  -> Sort (Sort Key: created_at DESC, id DESC)
       -> Seq Scan on phrases
            Filter: (validation_status = 'duplicate_confirmed'::text)
            Rows Removed by Filter: 20001
Execution Time: 10.291 ms
```

No index on `validation_status` exists, so the planner has no cheaper option
than a full Seq Scan + Sort of the entire table — **5007 buffer hits vs. 6
for the unfiltered query, ~90x more I/O**, even though only 3 rows match.
Filtering to the common value (`unique`) would look cheap by comparison
(most rows pass the filter, closer to the unfiltered plan), but the rare-value
case is the one that matters for a correctness/scale argument, since a status
filter's whole selling point is finding the rare `duplicate_confirmed` rows.

### `WHERE normalized_text ILIKE '%vaca lola%'` (rare substring)

```
Limit (actual time=32.430..32.436 rows=2 loops=1)
  Buffers: shared hit=5007
  -> Sort (Sort Key: created_at DESC, id DESC)
       -> Seq Scan on phrases
            Filter: (normalized_text ~~* '%vaca lola%'::text)
            Rows Removed by Filter: 20002
Execution Time: 32.462 ms
```

Same Seq Scan + Sort shape, same 5007 buffers, and slower in wall-clock
(32ms vs 10ms) because `ILIKE` per-row evaluation costs more than an equality
check. No index today can serve a leading-wildcard `ILIKE '%...%'` at all
(a plain btree can't; would need `pg_trgm`'s GIN/GIST trigram index).

## What this means for design

- At the **current** ~20k-row scale, 10-30ms for a filtered first page is
  not user-visible-slow, but it is already a full-table Seq Scan — this
  degrades roughly linearly (or worse, once sort spills past `work_mem`) as
  the table grows. 100k rows ≈ 50-150ms; 1M rows would be a real problem.
- The unfiltered/no-filter path is completely unaffected (still hits the
  existing index) — this only matters when a filter is actually active.
- Concrete design-phase decision, informed by these numbers: whether to add
  (a) a plain btree index on `validation_status` (or a partial index
  `WHERE validation_status = 'duplicate_confirmed'`, given the skew — cheap,
  small, directly fixes the status-filter case) and/or (b) a `pg_trgm` GIN
  index on `normalized_text` for the text filter (bigger schema change: new
  extension + index build on a 20k-row table now, larger later) — or to
  explicitly accept the current cost at today's scale and revisit later.
  This exploration does not decide it; it hands design real numbers instead
  of a guess.
