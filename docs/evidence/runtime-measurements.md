# Runtime image size and embed() latency evidence (tasks.md 8.4)

Generated 2026-09-23 via a real `docker build`/`docker run`/`docker compose up` session (Docker
confirmed available and used for real; see apply-progress.md's Unit 8 follow-up section for how the
environment was assembled). Closes the two halves of task 8.4 that were still open after Unit 14/16
(image size was already informally captured in ADR-003/ADR-008 prose; `embed()` p50/p95 and the
warm-vs-cold HTTP timing pair had never been measured anywhere).

## API image size

```
$ docker build -t todo-ia-api services/api   # fully cached rebuild, confirms the image is current
$ docker images todo-ia-api
REPOSITORY    TAG       IMAGE ID       SIZE
todo-ia-api   latest    f02787c07942   10.4GB
$ docker inspect todo-ia-api:latest --format '{{.Size}}'
4400446152
```

**10.4 GB disk usage / 4.4 GB content size** (`docker inspect .Size`, the closer analogue to a
traditional single "SIZE" value — Docker Desktop's `docker images` disk-usage column double-counts
shared base layers). Same figures Unit 16 already cited from the Unit 14 build; re-confirmed here
by an independent rebuild (100% cache hits, no stale layers) rather than trusted from a prior
session's cached number. This is a reused-cache measurement, not a from-clean `--no-cache` build —
still the best available number, per ADR-003's own caveat.

## `embed()` p50/p95 latency (real model, no HTTP overhead)

Ran a one-off timing loop (not a pytest test — a simple script per this task's relaxed scope) inside
a container from `todo-ia-api:latest`, with the offline env vars set
(`HF_HUB_OFFLINE=1`/`TRANSFORMERS_OFFLINE=1`/`SENTENCE_TRANSFORMERS_HOME=/opt/models`) so
`load_sentence_transformer` resolves the baked `paraphrase-multilingual-MiniLM-L12-v2` checkpoint
(revision `e8f8c211226b894fcb81acc59f3b34ba3efd5f42`) from the image's own cache with zero network
calls. 3 warmup calls (discarded), then 50 timed `embed()` calls over 10 rotating ES/EN texts drawn
from the calibration fixture's own pairs.

| Metric | Value |
| --- | --- |
| Cold model load (`SentenceTransformer(...)` construction) | 5,892.0 ms |
| n samples | 50 |
| min | 11.01 ms |
| **p50** | **13.23 ms** |
| **p95** | **15.12 ms** |
| max | 16.07 ms |
| mean | 13.22 ms |
| stdev | 1.17 ms |

This replaces design.md's ADR-003/Verification-Status "~50 ms CPU forward pass, ESTIMATE,
unmeasured" — the real p95 (15.12 ms) is roughly 3x faster than the estimate on this host's CPU. One
local run, single container, no concurrent load; a production capacity estimate should re-measure on
the actual target host and under concurrency (`EMBEDDING_MAX_CONCURRENCY=2`).

## Warm-vs-cold HTTP timing (`POST /phrases/validate`, `POST /phrases`)

Measured against the real, fully running Docker Compose stack (`docker compose up -d db migrate
api`, real Postgres/pgvector + the real baked model, no `FakeEmbedder`), `curl -w "%{time_total}"`,
5 pairs per endpoint. "Cold" = first request for a text never embedded before (`CachingEmbeddingProvider`
miss, real `embed()` call); "warm" = a second request for the *same* text immediately after (cache
hit, `embed()` skipped entirely) — same pattern ADR-011 names as the cache's load-bearing case.

### `POST /phrases/validate`

| Pair | Cold (ms) | Warm (ms) |
| --- | --- | --- |
| 1 | 23.52 | 7.13 |
| 2 | 19.77 | 6.13 |
| 3 | 23.52 | 8.72 |
| 4 | 21.47 | 6.37 |
| 5 | 22.50 | 6.74 |
| **avg** | **22.16** | **7.02** |

### `POST /phrases` (cold = 201 first save; warm = repeat of the same text, 409 conflict, embedding
cache hit on the comparison path)

| Pair | Cold (ms) | Warm (ms) |
| --- | --- | --- |
| 1 | 25.02 | 8.45 |
| 2 | 21.89 | 8.10 |
| 3 | 22.39 | 8.24 |
| 4 | 22.59 | 8.25 |
| 5 | 22.11 | 8.19 |
| **avg** | **22.80** | **8.25** |

**Warm-vs-cold saving**: roughly 15 ms saved per request on cache hit for both endpoints (~68%
latency reduction on `/phrases/validate`, ~64% on `/phrases`), consistent with the raw `embed()`
p50/p95 measured above (~13-15 ms) being skipped entirely on a cache hit — the remaining ~7-8 ms
warm floor is FastAPI/DB round-trip overhead, not embedding cost. This is the first real number for
ADR-011's own "measured warm-vs-cold saving from the cache" — previously UNMEASURED.

## Summary (for ADR-003 / ADR-011 / design.md's Verification Status table)

| Item | Was | Now |
| --- | --- | --- |
| API image size | 10.4 GB / 4.4 GB (Unit 14/16, informal) | Same, independently re-confirmed by a fresh cached rebuild |
| ~50 ms CPU forward pass estimate | ESTIMATE, unmeasured | **p50 13.23 ms / p95 15.12 ms**, real measurement |
| Warm-vs-cold cache saving | UNMEASURED | **~15 ms/request saved (~65-68%)**, real measurement |

One local run on one host, no concurrent load; not a production capacity benchmark. Both halves of
task 8.4 are now closed with real, non-fabricated numbers.
