# Architecture

This document explains how `todo-ia` is built: the monorepo layout, the hexagonal module structure
and its enforced boundaries, the embedding microservice seam, the three similarity read shapes,
keyset pagination, the embedding cache invariant, the save concurrency sequence, and residual
risks. For *why* each of these choices was made, see the ADRs under `docs/decisions/` (linked from
the README) — this document describes the resulting shape, the ADRs argue for it.

## Monorepo layout

```
todo-ia/
├── docker-compose.yml          # root: one command, no -f flag, runs the whole stack
├── .env.example                # every configurable var, defaults documented in README
├── Makefile                    # up, test, test-unit, test-slow, evidence, types
├── apps/web/                   # Next.js + TypeScript (own Dockerfile, own package.json)
├── services/api/               # FastAPI (own Dockerfile, own pyproject.toml)
│   ├── src/app/
│   ├── migrations/             # Alembic, raw SQL
│   └── tests/
├── infra/                      # compose-adjacent assets: db init script, smoke test
└── docs/
    ├── architecture.md         # this file
    ├── decisions/              # exactly five beyond-brief ADRs (ADR-001..005)
    │   └── technical/          # ten technical ADRs (ADR-006..015)
    ├── evidence/                # calibration.md, exact-scan-timings.md
    └── openapi.json            # snapshotted API contract
```

`apps/` and `services/` are service-typed, not layer-typed: each directory is an independently
deployable unit with its own build. Migrations live under `services/api/migrations/`, not `infra/`
— the schema is owned by the `phrases` module, and the `migrate` compose service reuses the API
image (not a second one), so migration and runtime code always share the same version.

## Hexagonal modules and import-linter contracts

Inside `services/api/src/app/`:

```
main.py                       # app factory = composition root
platform/                     # cross-cutting, owns no business rule
├── settings.py                # pydantic-settings, fail-fast startup validation
├── db.py                       # engine, session, advisory-lock helper
├── errors.py                   # DomainError -> HTTP registry, envelope
└── health.py                   # GET /health
modules/
├── similarity/
│   ├── contracts.py            # PUBLISHED: EmbeddingProvider, Vector, SimilarityPolicy, errors
│   ├── domain/                 # cosine.py, policy.py, vector.py, errors.py
│   ├── adapters/                # sentence_transformers.py, bounded.py, caching.py, fake.py, failing.py
│   └── container.py
└── phrases/
    ├── contracts.py            # PUBLISHED: PhraseRepository, UnitOfWork, Phrase, Match, Page
    ├── domain/                 # phrase.py, normalization.py, errors.py
    ├── application/             # validate_phrase.py, list_matches.py, save_phrase.py, list_phrases.py
    ├── adapters/                 # pgvector_repository.py, in_memory_repository.py
    ├── api/                      # router.py, schemas.py
    └── container.py
```

Each module owns `domain` (pure business rules), `application` (use cases), `adapters`
(infrastructure implementations of the module's contracts) and, for `phrases`, `api` (HTTP layer).
Only `contracts.py` is published for another module to import.

Boundaries are enforced by `import-linter` in CI, not by convention — a violation fails the build:

| Rule | Contract |
| --- | --- |
| `similarity` MUST NOT import `phrases` | independence contract |
| `phrases` MAY import **only** `similarity.contracts` | forbidden contract on `similarity.domain/adapters/api` |
| `*.domain` MUST NOT import `fastapi`, `sqlalchemy`, `torch`, `sentence_transformers` | forbidden contract — domain stays framework-free |
| `*.application` MUST NOT import `*.adapters` or `*.api` | layers contract — use cases depend on ports, not implementations |
| only `main.py` and `*/container.py` may import `*.adapters` | composition root — wiring is centralized, not scattered |

## The embedding microservice seam (and its honest limit)

`EmbeddingProvider` is the extraction point. To split `similarity` into its own service: add an
`HttpEmbeddingAdapter` implementing the same protocol and change one line in the composition root.
Nothing in `domain` or `application` moves. The contract that service would expose:

```
POST /embeddings  {"texts": ["..."], "model": "..."} -> {"vectors": [[...]], "dim": 384, "model": "..."}
GET  /health      -> {"data": {"status": "ok", "model": "...", "dimensions": 384}}
```

**Honest limit**: only *embedding generation* is extractable this way. Similarity *search*
(`find_nearest`, `find_nearest_exact`, `find_matches`) is executed by pgvector next to the data and
cannot follow the embedder out of the API without either shipping vectors over the wire per query or
duplicating the corpus into a second store. The module is "portable" for computing a vector, not for
searching one — see `ADR-002`.

## Three similarity read shapes

Two distinct questions are answered by three repository methods, never one method with a flag:

| Method | Question | Index | Used by |
| --- | --- | --- | --- |
| `find_nearest` | What is the closest stored phrase (unfiltered top-1)? | HNSW (`hnsw.ef_search` configurable) | `POST /phrases/validate` only |
| `find_nearest_exact` | Same question, exact twin | exact scan (`enable_indexscan` off, same planner settings as `find_matches`) | `POST /phrases` (save) — the verdict and recorded metadata never depend on approximate recall |
| `find_matches` | Which phrases are duplicates (threshold-filtered, paginated)? | exact scan | `POST /phrases/validate` (page 1) and `POST /phrases/matches` (pages 2..n) |

HNSW is used in exactly one place: `find_nearest` on the validate endpoint. It is not used for
`find_matches` because an HNSW scan applies `WHERE` *after* a bounded candidate window — a
threshold-filtered, paginated list served from it would silently truncate once matches exceed that
window, which breaks the "complete match list" requirement. It is not used on the write path either:
a recall miss there could let a duplicate through as `unique`, so `SavePhrase` always reads through
the exact `find_nearest_exact`.

**Reconciliation rule**: on validate, both reads run inside one `REPEATABLE READ READ ONLY`
snapshot; `score`/`most_similar` come from `matches[0]` whenever matches exist, and from
`find_nearest` only when nothing crosses the threshold (the specs still require reporting the best
neighbour even when it is below threshold).

## Keyset pagination

Match pages are keyset-paginated on `(distance asc, id asc)`, never `OFFSET`. The cursor carries the
normalized text (re-embedded per page, see the cache section below), the threshold and the last row's
distance/id, opaque and size-capped; any violation or a cursor issued for a different comparison form
or threshold returns `400 INVALID_CURSOR`, decided **before** any embedding happens.

Keyset buys **semantics, not speed**: `find_matches` is an exact O(n) scan regardless of page number
(the predicate filters rows, it does not seek), so page 40 costs the same order as page 1. What
keyset guarantees is that a phrase inserted between two requests cannot shift rows across a page
boundary the way an `OFFSET` page would (repeating or skipping rows), and the cursor needs no server
state.

**Tolerance grid**: exact float equality on distance breaks the moment a recomputed query vector
drifts by an ulp (cache eviction, another worker, BLAS reduction order). The keyset key is instead
`(floor(distance / 1e-6), id)` — a tolerance band quantized into a grid, which restores a total order
while absorbing that drift. Residual: two non-identical rows within 1e-6 of each other **and** of the
cursor, straddling a grid edge under drift, could still flip bucket — accepted as far below the 1e-4
display unit and the 1e-5 oracle tolerance, so no reported score is ever affected.

## The embedding cache invariant: never cache verdicts or pages

A bounded per-process LRU (`CachingEmbeddingProvider`, default 512 entries, key
`(model_id, comparison_form)`) sits behind the `EmbeddingProvider` port and caches **one thing only**:
the pure text→vector forward pass. It removes the two places that repeated it — matches pages 2..n
re-embedding the cursor's text, and a blind Save (pressing *Guardar* without validating first)
embedding the same text twice, once per HTTP call.

**Non-negotiable invariant**: `embed` is a pure, deterministic function of `(model, comparison_form)`,
so a cache hit and a cache miss always produce the same vector, and cold vs. warm always produce the
byte-identical HTTP response. Three things follow, each guarded by a test:

1. **Never cache a verdict** (`is_duplicate`, `score`, `most_similar`) — it depends on the current
   corpus, which changes on every insert.
2. **Never cache a match page** — both endpoints always re-run the similarity query against live
   data; only the query *vector* is reused.
3. **Never trust a client-supplied score** — the cursor carries ordering data only; save always
   recomputes the verdict under the advisory lock.

A repository-call counter test asserts a warm cache still issues the live queries every request (one
`find_nearest` + one `find_matches` on validate, one `find_nearest_exact` and zero `find_nearest` on
save, one `find_matches` per match page) — the cache can never be "optimized" into skipping a query.
`EMBEDDING_CACHE_SIZE=0` disables it entirely and every test still passes, which is the kill switch.
The cache is per-process: with `N` workers or containers, hit rate degrades to roughly `1/N`, but
correctness is unaffected because a recomputed vector differing by an ulp is absorbed by the keyset
tolerance grid above (see `ADR-011`).

## Blind-save sequence

Pressing *Guardar* without validating first still makes two real HTTP calls, but costs exactly one
embedding forward pass when the cache is warm:

```
1. POST /phrases/validate   "Validando..."    cache MISS → 1 forward pass
                                               + find_nearest (live) + find_matches (live, page 1)
2. POST /phrases            "Revalidando..."  cache HIT  (same comparison form, zero forward passes)
                                               + advisory lock
                                               + find_nearest_exact (live, exact scan)
                                               + INSERT (or find_matches → 409 body)
3. 201 → machine returns to idle at once: text cleared, "Frase guardada." announced,
         list refreshed in the background. No label is shown after the 201.
```

Both HTTP calls stay genuinely real — "Revalidando..." narrates a fresh similarity query plus the
locked insert, work that is truly in flight, it just no longer pays for a redundant forward pass.

## Transactions and locking

Two isolation levels, opened through a `UnitOfWork` port (never a raw adapter import from the
application layer):

- **Validate**: `REPEATABLE READ READ ONLY`. Both reads (`find_nearest`, `find_matches`) share one
  snapshot — plain `READ ONLY` under the default `READ COMMITTED` would give each statement its own
  snapshot, which could let the two reads disagree if a writer commits between them.
- **Save**: `READ COMMITTED`. A repeatable-read snapshot is fixed at the transaction's first
  statement; if that came before the wait on the advisory lock, it would freeze *before* the commit
  the lock was waiting for — exactly the commit the check must see.

Save sequence, in order:

```
embed() happens BEFORE BEGIN, outside any transaction  -- a slow model never holds the write lock
BEGIN (READ COMMITTED)
  SET LOCAL lock_timeout = LOCK_TIMEOUT_MS
  SELECT pg_advisory_xact_lock(hashtext('phrases:validate_and_insert'))   -- one global key
  find_nearest_exact(q)          -- exact scan, unfiltered top-1
  verdict = clamped, rounded score >= threshold
  if verdict and not confirm_duplicate:
      find_matches(q, page 1)    -- only to fill the 409 details payload
      ROLLBACK                   -- 409, nothing persisted
  else:
      INSERT phrases (..., similarity_score, most_similar_phrase_id, ...)
      COMMIT                     -- lock released automatically
```

The lock is global (one key for all saves), not per-text: semantic duplicates have *different* text
by definition, so a text-keyed lock would protect nothing. Validate takes no lock at all — it is
advisory only. A bounded `lock_timeout` (`LOCK_TIMEOUT_MS`, default 5000ms) keeps a stuck holder from
pinning every save indefinitely; a timeout maps to `500 INTERNAL_ERROR` with nothing persisted.

`similarity_score` and `most_similar_phrase_id` are recorded from `find_nearest_exact`
**regardless of the verdict** — a `unique` row whose closest neighbour scored 0.55 still stores
`(0.55, <that id>)`; only an empty store yields `(NULL, NULL)`.

**Two layers of integrity, honestly scoped** (`ADR-006`):

- *Identical text* (same `normalized_text`, status `unique`): guaranteed by a partial unique index
  (`phrases_unique_normalized_text_uidx ... WHERE validation_status = 'unique'`) — a database
  guarantee that survives even a lock-bypassing path. A unique violation maps to one bounded retry in
  a fresh transaction, landing on the normal 409 path, never a 500.
- *Semantic near-duplicates* (different text, high similarity): **not** covered by any index or
  constraint — "cosine >= threshold" cannot be expressed that way. Protected only by the advisory
  lock and application logic.

## Residual risks

- **Semantic near-duplicate race**: a path that bypasses the advisory lock, or the window between a
  reader validating and a similar phrase being committed since, can still land two unconfirmed
  near-duplicates — the database has no constraint that catches this, unlike the identical-text case.
  Accepted and documented, not silently possible.
- **Exact scans are O(n) per page/save**: `find_matches` (per page) and `find_nearest_exact` (per
  save) scan every stored row. Accepted at target scale; `docs/evidence/exact-scan-timings.md` records
  measured timings at 500 and 10,000 rows. The documented, unverified, deferred scaling path is
  pgvector ≥ 0.8's `hnsw.iterative_scan = strict_order`.
- **Keyset grid edge case**: two non-identical rows within `1e-6` of each other and of the cursor,
  straddling a grid boundary under float drift, could still flip bucket order (see "Keyset
  pagination" above) — far below any reported precision, but not mathematically impossible.
- **Cache hit rate degrades under multiple workers/replicas**: correctness is unaffected, only
  latency; a shared cache is a possible future step, not designed here (`ADR-011`).
- **p95 embedding latency is unmeasured**: no unit timed `embed()` p50/p95 against the running model;
  only cold-build and container-start-to-healthy times are measured (`ADR-003`).
- **A running forward pass cannot be cancelled** after `EmbeddingTimeout` — `BoundedEmbeddingProvider`
  bounds concurrency and fails fast on new requests, but a stuck call keeps its executor slot until it
  finishes on its own.
