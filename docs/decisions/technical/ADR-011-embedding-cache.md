---
id: ADR-011
title: Bounded per-process embedding cache behind the EmbeddingProvider port
type: technical
---

# ADR-011: Bounded per-process embedding cache

*(Classification note: this entry keeps its "brief asked / we decided /
because" framing below because that is how it was originally reasoned
about, but it is filed under `type: technical` and lives in
`docs/decisions/technical/`, not at the top level. Typing it
`beyond-brief` would have made six top-level entries and broken the "exactly
five" requirement (ADR-001..005 are the five phrase-management topics).
The honest classification is technical anyway: the cache does not change
what the product does, it changes how often a pure function runs.)*

**The brief did not ask for** any caching or performance work — it asked
for a validation flow.

**We decided** to add a bounded, per-process LRU **inside an
`EmbeddingProvider` decorator** (`CachingEmbeddingProvider`, key
`(model_id, comparison_form)`, 512 entries ≈ 1 MB (estimate), LRU eviction,
lock on the dict but never around the forward pass), and to cache
**nothing else**.

**Because** the flow visibly recomputed the same pure function twice —
once per matches page 2..n, and once more on the second leg of a blind
Save — while every *other* candidate for caching (the verdict, the match
page, a client-supplied score) goes stale the moment a phrase is inserted
and would turn a correctness property into a race. Caching a pure
deterministic function is the only optimization here that is **observably
free**: cold and warm produce byte-identical responses,
`EMBEDDING_CACHE_SIZE=0` reverts it, and the similarity query still runs
on every single request.

**Limits accepted and documented**: the cache is per process, so N workers
means N caches and a hit rate ≈ 1/N — correctness is unaffected (the
keyset tolerates a recomputed vector), only latency. A shared cache is a
possible future step if more than one replica is ever run; it is not
designed here.

Real p95 embedding latency and the measured warm-vs-cold saving from the
cache are **UNMEASURED** — see ADR-003's "What it costs" section; no unit
timed `embed()` p50/p95 or a warm/cold `POST /phrases/validate` +
`POST /phrases` pair against the real model.
