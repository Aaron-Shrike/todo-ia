# Design: Phrase Validation with Semantic Duplicate Detection

> Size note: this design exceeds the usual 800-word budget on purpose. The change stands up a
> backend, a frontend, a database and infrastructure from zero, and the orchestrator requested an
> explicit decision on ~13 architectural forks. Every section below resolves a fork the apply phase
> would otherwise have to guess.
>
> Revision note: the efficiency requirement (no recomputation from scratch on pages 2..n or on the
> second leg of a blind Save) is resolved by **D10 / ADR-011** — see *Efficiency: the embedding
> cache*. Statelessness, keyset pagination and server-side re-validation are unchanged.
>
> Spec-reconciliation note: the specs under `specs/*/spec.md` are authoritative for **observable
> behaviour** (endpoint shapes, error codes, UI copy, rounding); this document is authoritative for
> **internals**. Seven places where the two disagreed are now resolved here: the unfiltered top-1
> query `find_nearest` (below-threshold `most_similar` and its recording on save), the rounding
> contract and its SQL/application split, the `/health` payload and the completed error table, the
> staged progress copy, the full validate-shaped `409` payload, the oracle tolerance (1e-5), and
> string-serialized ids. Each is called out in the section that owns it.
>
> Judgment-revision note: after adversarial review the design (a) serves `find_matches` with an
> **exact scan** and keeps HNSW only for the unfiltered top-1 `find_nearest` of the validate endpoint (D1/D12; there is no
> "page cost independent of `n`" claim any more), (b) runs the validate pair in a
> `REPEATABLE READ` read-only snapshot through a `UnitOfWork` port (D17), (c) clamps scores to
> [0, 1] before rounding (D13), (d) makes the keyset tolerant of sub-ulp query-vector drift (D16),
> and (e) fixes the `/health` key mapping (`model` = readiness string, `embedding_model` = model
> name), the UI state machine (no stage after the 201) and the decision-log layout
> (`docs/decisions/technical/`).
>
> Write-path revision (user-confirmed, Option 1): the `SavePhrase` verdict (`is_duplicate`, `score`,
> `most_similar`) and the metadata recorded on the row **no longer depend on the approximate HNSW
> read**. On save they come from an **exact** single-row nearest-neighbour read,
> `find_nearest_exact` (same planner settings as `find_matches`, no HNSW scan), taken inside the save
> transaction under the advisory lock. HNSW `find_nearest` remains the fast top-1 for
> `POST /phrases/validate` only. This closes the former "accepted residual" (see D1, D12, Concurrency,
> Risks, ADR-008/ADR-012).

## Technical Approach

A monorepo of **independently deployable services** wired by one root `docker-compose.yml`. Inside
the API, a **modular hexagonal** structure: two modules (`phrases`, `similarity`), each with its own
`domain / application / adapters / api` layers and its own published contract. The domain owns the
*meaning* of a similarity score (threshold policy, verdict); pgvector owns its *computation at
scale*; a pure-Python cosine stays in-tree as the in-memory adapter and as a test oracle that pins
the two to agree.

Both endpoints are stateless. `POST /phrases/validate` persists nothing; `POST /phrases`
recomputes the score server-side under an advisory lock and never trusts a client-supplied value.
Match pagination is keyset on `(raw distance asc, id asc)` — distances compared on a 1e-6 grid, see D16 — and carries no server state.

Two **distinct read shapes** back this, and conflating them was the design's largest gap against the
specs. `find_nearest` is an **unfiltered top-1** query that answers *what is the closest stored
phrase* — it is the source of `score` and `most_similar` whenever nothing matches (the specs require them even
when the best neighbour is **below** the threshold; when matches exist `matches[0]` wins, see the
reconciliation rule) on the **validate endpoint only**. The write path never uses it: `SavePhrase`
takes its verdict and the metadata it records from `find_nearest_exact`, the same single-row question
answered by an **exact scan** (no HNSW), so a recall miss can never let a duplicate through as `unique`.
`find_matches` is a **threshold-filtered keyset** query that answers *which phrases are duplicates*
and serves the paginated list; it is an **exact scan** (D1), so it can never miss a match the way
an approximate index can. They are separate repository methods, not one method with a flag.
`find_nearest_exact` is the exact twin of `find_nearest` (same unfiltered top-1 contract, same
`(distance, id)` order, exact plan) used wherever completeness matters, i.e. the write path.

Scores are clamped to [0, 1] and then rounded to 4 decimals, and that **clamped, rounded** value is
the only one the threshold decision, the response body and the stored row ever see; the raw double
survives solely as an ordering key.

Efficiency is a design property, not an afterthought: a bounded LRU decorator over
`EmbeddingProvider` (D10) removes the only work the flow was repeating — the *pure* text→vector
function — so matches pages 2..n and the second leg of a blind Save cost **zero** extra forward
passes, while every verdict and every match page is still recomputed against live data. The cache
is **process-local memoization, not protocol state**: no request depends on it existing, and
deleting it changes latency only.

## Repository Layout

```
todo-ia/
├── docker-compose.yml          # root: reviewer runs one command, no -f flag
├── .env.example
├── Makefile                    # up, test, test-unit, test-slow, evidence, types
├── apps/web/                   # Next.js + TS      (own Dockerfile, own package.json)
├── services/api/               # FastAPI           (own Dockerfile, own pyproject.toml)
│   ├── src/app/
│   ├── migrations/             # Alembic, raw SQL
│   └── tests/
├── infra/                      # compose-adjacent assets: db init, healthcheck scripts
└── docs/
    ├── architecture.md
    ├── decisions/              # exactly five beyond-brief ADRs (ADR-001..005)
    │   └── technical/          # technical ADRs (ADR-006..015); never counted as beyond-brief
    ├── evidence/               # calibration.md (HF integration evidence)
    └── openapi.json            # snapshotted contract
```

**Supersedes** the proposal's `backend/` + `frontend/` paths (Affected Areas table): the monorepo
decision makes service-typed directories (`apps/`, `services/`) the clearer signal that each unit
ships on its own.

**Migrations live in `services/api/migrations/`, not `infra/`.** The schema is owned by the
`phrases` module, and the `migrate` compose service reuses the **API image** rather than building a
second one — this guarantees migration/runtime version parity and removes a whole class of "the
migration container is stale" bugs. `infra/` holds only assets compose needs that belong to no
service.

## API Module Structure and Boundaries

```
services/api/src/app/
├── main.py                       # app factory = composition root
├── platform/                     # cross-cutting, owns no business rule
│   ├── settings.py               # pydantic-settings, fail-fast validation
│   ├── db.py                     # engine, session, advisory-lock helper
│   ├── errors.py                 # DomainError -> HTTP registry, envelope
│   └── health.py                 # GET /health
└── modules/
    ├── similarity/
    │   ├── contracts.py          # ← PUBLISHED: EmbeddingProvider, Vector, SimilarityPolicy, errors
    │   ├── domain/               # cosine.py, policy.py, vector.py, errors.py
    │   ├── adapters/             # sentence_transformers.py, bounded.py, caching.py, fake.py, failing.py
    │   └── container.py
    └── phrases/
        ├── contracts.py          # ← PUBLISHED: PhraseRepository, UnitOfWork, Phrase, Match, Page
        ├── domain/               # phrase.py, normalization.py, errors.py
        ├── application/          # validate_phrase.py, list_matches.py, save_phrase.py, list_phrases.py
        ├── adapters/             # pgvector_repository.py, in_memory_repository.py
        ├── api/                  # router.py, schemas.py
        └── container.py
```

**Boundary rules** (enforced by `import-linter` in CI, not by convention):

| Rule | Contract |
| --- | --- |
| `similarity` MUST NOT import `phrases` | independence contract |
| `phrases` MAY import **only** `similarity.contracts` | forbidden contract on `similarity.domain/adapters/api` |
| `*.domain` MUST NOT import `fastapi`, `sqlalchemy`, `torch`, `sentence_transformers` | forbidden contract |
| `*.application` MUST NOT import `*.adapters` or `*.api` | layers contract |
| only `main.py` and `*/container.py` may import `*.adapters` | composition root |

**Microservice seam.** The extraction point is `EmbeddingProvider`. To split `similarity` out, add
an `HttpEmbeddingAdapter` implementing the same protocol and change one line in the composition
root. Nothing in `domain` or `application` moves. The contract that service would expose:

```
POST /embeddings  {"texts": ["..."], "model": "..."} -> {"vectors": [[...]], "dim": 384, "model": "..."}
GET  /health      -> {"data": {"status": "ok", "model": "...", "dimensions": 384}}
```

**Honest limit of the seam:** only *embedding generation* is extractable. Similarity *search* is
executed by pgvector next to the data and cannot follow the embedder out without either shipping
vectors over the wire per query or duplicating the corpus. This is stated in ADR-002 rather than
pretending the whole module is portable.

## Architecture Decisions

| # | Decision | Chosen | Rejected | Rationale |
| --- | --- | --- | --- | --- |
| D1 | Vector index and scan strategy | **HNSW** `vector_cosine_ops` (`hnsw.ef_search` configurable) **only for the unfiltered top-1 `find_nearest` used by the validate endpoint**; **`find_matches` and the write-path `find_nearest_exact` are EXACT scans** (`SET LOCAL enable_indexscan = off` inside the query transaction). Recall-guard + `EXPLAIN` tests for `find_nearest`; `EXPLAIN`/spy tests proving save never uses HNSW | HNSW for both reads; IVFFlat; no index; a second index | An HNSW index scan returns at most `hnsw.ef_search` candidates and applies `WHERE` afterwards, so a threshold-filtered, paginated list served from it would silently truncate once matches exceed the candidate window — a correctness bug for a "complete match list" requirement. Forcing an exact plan for `find_matches` removes that failure mode. Chosen mechanism: the per-transaction planner setting `SET LOCAL enable_indexscan = off` (transaction-scoped, so it cannot leak into pooled connections; each repository method sets its own planner settings at its start so the two reads sharing one transaction never inherit each other's). The same exact-plan setting serves the write-path read `find_nearest_exact` (Option 1: the save verdict must not depend on approximate recall). Rejected alternative: an `ORDER BY (embedding <=> :q) + 0` expression trick, which is structurally index-proof but obscure and harder to justify to a reviewer than an explicit, EXPLAIN-tested planner setting. HNSW stays for the validate endpoint's `find_nearest` because top-1 is the canonical pgvector k-NN shape and the one place approximate search is cheap to guard, and there the exact `matches[0]` wins anyway (reconciliation rule). It is **not** used on the write path: a recall miss there could store a duplicate as `unique`, so `SavePhrase` uses the exact `find_nearest_exact` (Option 1) — correctness of the write path over a small O(n) cost at this scale, consistent with the earlier decision that exact scans are used wherever completeness matters. The scaling path (see *Per-page cost model*) is deferred. IVFFlat needs a trained list layout and loses recall as rows are appended one at a time. Honest cost: the exact scan is **O(n) per page** (see *Per-page cost model*), acceptable at this scale; the scaling path is documented there and deferred. |
| D2 | Match paging | **Re-embed per page**, cursor carries normalized text | Session/vector cache keyed by cursor; vector inside cursor | Keeps statelessness a real property, not a claim. No TTL on the *protocol*, no `CURSOR_EXPIRED` error, no UI branch for it. A 384-float cursor would be ~2 KB and client-tamperable. "Re-embed" is the **semantic contract**; D10 makes it cheap without weakening it. |
| D3 | Save concurrency | **`pg_advisory_xact_lock`, one global key** | Per-normalized-text lock; `SERIALIZABLE` | Semantic duplicates have *different* text by definition, so a text-keyed lock protects nothing. Global key serializes writes only (validate takes no lock); at this scale that is free. |
| D4 | Exact-duplicate integrity | **Partial unique index** `phrases_unique_normalized_text_uidx ON phrases (normalized_text) WHERE validation_status = 'unique'` (ADOPTED, ADR-006), **plus** the advisory lock and app logic | Plain unique index on `normalized_text`; no index (earlier decision, superseded); advisory lock alone | A plain unique index would reject legitimately confirmed duplicates. The *partial* index excludes `duplicate_confirmed` rows, so confirmed duplicates stay allowed, and an unconfirmed identical text is never inserted as `unique` (the server answers 409), so the earlier rationale is intact. Purpose is **integrity, not performance**: it makes "no unconfirmed identical phrase is stored twice" a database guarantee and a backstop to the lock and to application bugs. It does **not** cover semantic (non-identical) near-duplicates: those stay protected only by the lock plus application logic (residual race, see Concurrency). |
| D5 | Frontend call path | **Browser → API directly**; list first paint via Server Component using `API_INTERNAL_URL` | Next route handlers as BFF proxy | No secrets exist to hide (anonymous API), which is the only strong reason for a proxy. A proxy would couple API availability to the web container and defeat independent deployability. Cost accepted: CORS config + a build-time `NEXT_PUBLIC_API_URL`. |
| D6 | Embedding runtime | **sentence-transformers**, baked at build, behind `EmbeddingProvider` | ONNX/fastembed now; HF Inference API | See ADR-003. Migration is an adapter swap. |
| D7 | Integration DB | **Compose `db` service + `phrases_test` database** | testcontainers | Docker is already mandatory. Testcontainers adds a dep, needs Docker-socket access from the test process, and is the flakiest link on Windows/WSL. Same image as runtime = same pgvector build. Opt-in testcontainers fixture stays possible behind the same interface. |
| D8 | Primary key | **`BIGINT GENERATED ALWAYS AS IDENTITY`** | UUIDv4/v7 | Monotonic, cheap, and gives a natural stable tie-break for the keyset cursor. Enumerability is irrelevant for an anonymous local list. |
| D9 | Match paging transport | **Two endpoints**: `POST /phrases/validate` (verdict + page 1, **no `cursor` accepted**) and `POST /phrases/matches` (pages 2..n, `cursor` **required**) | One polymorphic endpoint | Avoids a response where `is_duplicate`/`most_similar` are sometimes null-by-protocol. Cleaner OpenAPI, trivial contract test, simpler typed client. Only `/phrases/matches` can produce `400 INVALID_CURSOR`; a `cursor` key in a validate body is silently ignored (page 1 is returned) because validate has no cursor to be wrong about. |
| D10 | Embedding recomputation | **`CachingEmbeddingProvider`**: bounded LRU decorator over `EmbeddingProvider`, keyed on `(model_id, comparison_form)` | No cache (recompute every call); `functools.lru_cache`; cache the verdict / the match page; a shared cache now | The work that repeats across pages 2..n and across the two legs of a blind Save is *one pure function*: text → vector. Caching it is the only recomputation we can remove **without** weakening any correctness property. `functools.lru_cache` cannot take the model into the key, cannot be instrumented, and outlives the provider instance. Caching a verdict or a page would go stale the moment another phrase is inserted — that is forbidden (see below). A shared cache is unjustified for a single local process (a possible future step, noted in ADR-011 only). |
| D11 | Embedding input | **the comparison form** (casefolded, whitespace-collapsed) | the display form (trim + NFC + strip only) | Only the comparison form makes an exact duplicate score a literal `1.0` and makes "normalization variants share one cache entry" true by construction. Cost: a cased checkpoint loses a little signal; measured in slice 9, and the fallback is a spec change, not a silent code change. |
| D12 | Nearest neighbour vs match list | **Three repository methods**: `find_nearest` (unfiltered top-1, HNSW, validate only), `find_nearest_exact` (the same unfiltered top-1 as an exact scan, save path only) and `find_matches` (threshold-filtered, keyset, exact) | One `find_matches(max_distance=1.0, limit=1)` call; deriving `most_similar` only from `matches[0]` | The specs require `score`/`most_similar` for the best stored phrase **even below the threshold**, and require `SavePhrase` to record that neighbour on a `unique` row (from the exact read, so the recorded neighbour and the verdict never depend on HNSW recall). Deriving them from the threshold-filtered list makes them null exactly when they are most informative. Passing `max_distance=1.0` to `find_matches` would work numerically but would overload one method with two different questions and two different index-usage profiles, and would make the "same threshold decides `matches`" invariant a caller convention instead of a method contract. |
| D13 | Clamped, rounded score vs SQL filter | **Domain clamps `score = min(1, max(0, 1 - distance))`, then rounds to 4 decimals**; SQL filters on a bound **widened by a full rounding unit** (`max_distance = 1 - threshold + u`, `u = 1e-4`; `2.0` when `threshold = 0`, because a clamped score of 0 admits every row) and the **application applies the exact comparison on `Decimal` values** | Rounding inside SQL (`round(1 - (embedding <=> :q))::numeric`); filtering on the naive `1 - threshold` bound; a bound widened by only `u/2` | A cosine distance lives in [0, 2], so a raw score can be negative; without the clamp a stored `similarity_score` could violate its `BETWEEN 0 AND 1` CHECK. The naive bound drops raw `0.79996`, which the specs say **is** a duplicate at `t = 0.80`. A `u/2` margin is a superset only in exact arithmetic: at float64 (and with pgvector's float32 distance error ~1e-7) a row exactly on the boundary can still fall out, so the margin is a full `u` (100 tolerance-grid cells, far above float error). Comparing `Decimal(str(rounded_score)) >= Decimal(str(threshold))` makes thresholds with more than 4 decimals (e.g. `0.80005`) exact instead of subject to binary-float surprises. Rounding in SQL kills nothing here but puts the rounding rule in two places with two half-way behaviours, so it stays rejected. The widened bound keeps the predicate on `embedding <=> :q` and leaves the domain as the single arbiter. |
| D14 | Id serialization | **`BIGINT` internally, decimal strings on the wire**, typed `string` and documented opaque in OpenAPI | numeric JSON ids | `Number.MAX_SAFE_INTEGER` < `BIGINT` max, and a string id keeps a future UUID/ULID swap out of the contract. One field serializer owns it; the domain never sees a string id. |
| D15 | `/health` payload | **`{status, database, model, dimensions, embedding_model, embedding_cache}`** with ONE key mapping everywhere: `model` = readiness string `"ready"` \| `"unavailable"`, `embedding_model` = model-name string; 503 = `NOT_READY` + per-component `details` using the same keys | the three spec-pinned fields only; a bare `{"status":"ok"}`; `model` = name and `embedding_model` = readiness (an earlier draft, inverted) | The api-contract spec is authoritative and pins `model` as the readiness string. `dimensions` catches a silent model swap; `embedding_cache` makes D10's hit/miss story inspectable without a metrics stack. Per-component `details` turn a red healthcheck into a diagnosis. The spec allows a superset of the pinned keys, so this is settled, not an open question. |
| D16 | Keyset key tolerance | The keyset key is `(bucket, id)` with `bucket = floor(distance / 1e-6)` (`KEY_EPSILON = 1e-6`), computed identically in SQL, in the in-memory repository and from the cursor's `d`; ordering is `ORDER BY bucket, id` | Exact float equality on `distance`; `(distance, id)` compared with an epsilon band | Exact float equality breaks the moment the recomputed query vector drifts by an ulp (cache eviction, another worker, thread-order in a BLAS reduction). A tolerance *band* (`abs(d - cursor_d) <= eps`) is not a total order, so it can skip rows; quantizing to a grid restores a total order while tolerating drift: two rows whose distances differ by less than `KEY_EPSILON` are ordered by `id`, and true ties (bit-identical stored vectors) move together under any drift. Residual, stated honestly: a row whose distance lies within the drift (~1e-7) of a grid edge *and* sits next to the cursor row can still flip bucket; that needs two non-identical rows within 1e-6 of each other, and the perturbed-vector test uses a fixture away from grid edges so it is deterministic. 1e-6 is far below the 1e-4 display unit and the 1e-5 oracle tolerance, so it changes no reported score. |
| D17 | Transactions in the application layer | **`UnitOfWork` port** in `phrases.contracts` (context manager with isolation level, `commit`, `rollback`); validate opens `REPEATABLE READ` read-only, save opens `READ COMMITTED` | `read_snapshot()` on the repository; SQLAlchemy sessions imported by use cases | `BEGIN READ ONLY` alone does **not** give one snapshot under the default `READ COMMITTED` (each statement gets its own), so the validate pair needs `ISOLATION LEVEL REPEATABLE READ`. Save deliberately stays `READ COMMITTED`: a repeatable-read snapshot is fixed at the first statement, which would freeze *before* a wait on the advisory lock ends and hide the commit the lock was waiting for. The port lets the application layer express BEGIN / ROLLBACK / fresh-transaction retry without importing an adapter, and lets the in-memory fake exercise the same retry path. |

### ADR-003 content: sentence-transformers now, ONNX/fastembed later

**Why now.** `sentence-transformers` is the reference implementation of
`paraphrase-multilingual-MiniLM-L12-v2`; its cosine scores are the *definition* the 0.80 threshold
is calibrated against. Lowest compatibility risk for a reviewer, no export step, no quantization
variable in play while the product's core decision boundary is being tuned.

**Not a deviation from "a Hugging Face model".** The checkpoint *is* a Hugging Face Hub model; it is
pinned by Hub **commit SHA** (`EMBEDDING_MODEL_REVISION`, a 40-hex build arg used by the Dockerfile
download and recorded in `model_id`), so a rebuilt image cannot silently pick up different weights.
What the decision changes is the *runtime*: local inference instead of the hosted Inference API.

**What it costs.** torch CPU + model weights dominate the API image (**measure and record in slice
8** — see Verification Status; the measured number becomes this ADR's baseline) and add a cold
start, mitigated by baking weights at build time and warming the model in the lifespan hook.

**Migration triggers** (any one is sufficient):
1. API image exceeds the agreed size ceiling for a target registry/deploy.
2. Cold start blocks a readiness-gated deployment (container start → `/health` ok).
3. RAM ceiling of a target host makes a torch process unviable.
4. p95 embedding latency becomes the dominant term in validate latency.

**What changes on migration.** `services/api/src/app/modules/similarity/adapters/onnx.py` +
one line in `container.py` + the `EMBEDDING_PROVIDER` env var. **No change** to domain,
application, `phrases`, API schemas, or the frontend.

**The gate that must not be skipped.** ONNX export and (especially) int8 quantization shift cosine
scores; near a 0.80 boundary a shift of ~1e-2 can flip a verdict. The migration PR MUST re-run the
ES/EN calibration fixture and diff per-pair scores against the recorded sentence-transformers
baseline, failing if any pair crosses the threshold or drifts beyond an agreed tolerance. Model
support in fastembed for this exact checkpoint is **unverified** (see Verification Status) — if it
is absent, the path is a manual `optimum` export, which the adapter boundary accommodates equally.

## Normalization, Scores and Ids

### Two normalization forms — one is embedded, the other is displayed

| Form | Produced by | Rules | Where it lives |
| --- | --- | --- | --- |
| **display form** | `normalization.display_form(raw)` | in order: (1) map whitespace controls (`\t \n \r \v \f`, U+001C..U+001F, U+0085) to one space; (2) strip U+200B, U+2060, U+FEFF and every remaining `Cc`; (3) NFC; (4) trim whitespace plus leading/trailing U+200C/U+200D. **ZWJ/ZWNJ inside the text are kept** (emoji sequences, Persian/Indic shaping) | column `text`, every API `text` field, the length check (code points, measured **after** trim) |
| **comparison form** | `normalization.comparison_form(display)` | `str.casefold()`, then **NFC again** (casefold can de-normalize), then internal whitespace collapsed to a single U+0020 | column `normalized_text`, **the embedding input**, the cache key, the cursor's `t` |

Mapping whitespace controls to a space *before* stripping the remaining `Cc` is what stops
`"Buy\tmilk"` from becoming `"Buymilk"`. NFC runs *after* stripping so a removed zero-width
character cannot block a composition, which keeps both forms idempotent; both idempotence
properties are tested.

The embedding input is the **comparison form**, not the display form. That is what makes the
exact-duplicate requirement literally true instead of approximately true: `"  comprar   LECHE "`
and `"Comprar leche"` both reduce to `"comprar leche"`, so their vectors are bit-identical and the
cosine is exactly `1.0` — a real cased model asked to compare the two *display* forms returns
≈ 0.98 (an **estimate from memory, unmeasured**), which no amount of 4-decimal rounding turns into 1.0. The same reduction is what makes
"normalization variants share one cache entry" hold by construction rather than by luck.

**Accepted cost**, stated rather than hidden: `paraphrase-multilingual-MiniLM-L12-v2` is a *cased*
checkpoint, so casefolding discards a little signal. The calibration fixture (slice 9) measures it
on cased ES/EN pairs. If the separating margin degrades materially, the fallback is to embed the
display form and give up the exact `1.0` — that is a **spec** change, so it must never be made
silently in code.

Both use cases normalize **once**, at the application boundary, and pass the comparison form
downward. `EmbeddingProvider.embed` documents that precondition; neither the provider nor the cache
owns a second copy of the rules. Rejection for empty-after-normalization and over-length happens on
the display form **before** any `embed()` call, so a rejected request costs zero forward passes.
Before normalization even starts, raw input longer than **4 × `PHRASE_MAX_LENGTH` code points** is
rejected with `too_long` (enforced as the schema's field bound, so it costs no normalization), and
the request body is capped by `MAX_REQUEST_BYTES` (413 `PAYLOAD_TOO_LARGE`) before it is parsed.

### Score rounding is the contract, not a formatting step

`u = 1e-4` (4 decimals) is the **rounding unit**, a domain constant — deliberately not
configuration. A cosine distance lives in [0, 2], so `1 - distance` can be negative (or overshoot 1
by float error); the domain therefore **clamps first**: `score = min(1, max(0, 1 - distance))`. Every
score that leaves the domain (reported in a response, compared against the threshold, written to
`similarity_score`) is `round(clamp(1 - distance), 4)`. That keeps the stored value inside the
column's `BETWEEN 0 AND 1` CHECK and means a threshold of `0` admits every stored phrase. The raw
double is an **ordering key only** and never reaches a client.

The tension this creates: the cheap filter lives in SQL over the *raw* distance, while the decision
lives in Python over the *clamped, rounded* score. A raw cosine of `0.79996` is a duplicate
(`0.8000 >= 0.80`), but its raw distance `0.20004` falls outside a naive `<= 1 - threshold` bound,
so SQL would silently drop a row the domain says is a match.

Resolution — **SQL is a deliberate superset; the application is the sole arbiter**:

| Layer | Rule |
| --- | --- |
| SQL (`find_matches`) | `WHERE embedding <=> :q <= :max_distance`, `max_distance = 1 - threshold + u` (`0.2001` at `t = 0.80`); `max_distance = 2.0` when `threshold = 0` (clamped scores of 0 all pass) |
| Application (`SimilarityPolicy`) | keep a row iff `Decimal(str(round(clamp(1 - distance), 4))) >= Decimal(str(threshold))`; the same predicate decides `is_duplicate` |

Any row the domain keeps has a raw score at least `threshold - u/2` (rounding moves a value by at
most `u/2`), i.e. a distance at most `1 - threshold + u/2`. The SQL bound is `u/2` looser than that,
which absorbs float64 arithmetic and pgvector's float32 error (~1e-7, three orders of magnitude
smaller than the margin). It only admits a thin band of rows the application then rejects, so SQL
and Python never need to agree on half-way rounding behaviour — only on an inequality that is
strictly *looser* on the SQL side. `find_nearest` needs none of this: it has no threshold predicate.

**The tail rule.** The rejected band sits at the far end of the ordering, so the application filter
is **monotonic along the ordering**: the first row that fails the comparison guarantees every later
row fails too. `find_matches` stops at that row, discards the rest and returns `has_more = false`. A
short page produced this way is a correct **final** page, never a gap — this is the one case where a
page may hold fewer than `limit` items while the `LIMIT :limit + 1` probe returned a full buffer,
and it is asserted by a boundary test. Monotonicity holds at the tolerance-grid granularity (D16):
rounding boundaries lie at multiples of `u/2 = 5e-5`, which are grid edges, so a bucket never
straddles one; residual float fuzz (~1e-10) is orders of magnitude below the float32 storage error
(~1e-7) and the 1e-5 oracle tolerance, and the boundary fixtures sit further than 1e-5 from any
boundary.

**Keyset stability.** The cursor carries the **raw** distance `d`, never the rounded score; the
keyset position is `(floor(d / 1e-6), id)` (D16). `max_distance` is re-derived on every page from
the cursor's `th` plus the constants `u`, so a page sequence's candidate set is reproducible across
requests; `u` being a constant rather than a setting is precisely what stops it drifting
mid-scroll. **Ordering, stated precisely:** the observable order is `(raw distance asc, id asc)`
with distances compared at 1e-6. Displayed 4-decimal scores are non-increasing along the list, but
two rows that *display* the same score generally have *different* raw distances and are ordered by
those distances, not by `id`; `id` breaks ties only between rows whose distances are equal at the
grid (e.g. bit-identical stored vectors). The tie fixture therefore stores bit-identical vectors
(`FakeEmbedder` returns the same vector object for the tied texts), and a separate fixture pins the
"displayed tie, distinct raw distance" order.

### Ids: `BIGINT` inside, opaque strings on the wire

`id` and `most_similar_phrase_id` are `BIGINT` in Postgres and `int` in the domain (D8: monotonic,
cheap, a stable keyset tie-break). At the API boundary they are serialized as **decimal strings**
(`"42"`) and parsed back on input; OpenAPI types them `string` and documents them as **opaque** —
clients MUST NOT do arithmetic on them, sort by them, or assume they are numeric. Two reasons:
JavaScript's `Number.MAX_SAFE_INTEGER` sits below `BIGINT`'s range, and a string id keeps a future
switch to UUID/ULID a serialization detail instead of a breaking contract change. One pydantic
field serializer on the API schemas owns the conversion, so the domain never sees a string id. The
cursor's `i` stays an integer — the cursor is opaque and no client parses it.

## Efficiency: the embedding cache (D10 / ADR-011)

The flow must not recompute everything from scratch on every request. Two paths repeat identical
work today: **matches pages 2..n** re-embed the cursor's text, and a **blind Save** (user presses
*Guardar* without validating) embeds the same text once in `POST /phrases/validate` and again in
`POST /phrases`. Both collapse to a single forward pass with a cache placed at the only layer where
it is provably safe.

### Where it lives

```
container.py:  provider = SentenceTransformersEmbedder(settings)
               provider = BoundedEmbeddingProvider(provider, timeout, max_concurrency)  # timeout + cap
               if settings.embedding_cache_size > 0:
                   provider = CachingEmbeddingProvider(provider, ...)   # ← outermost: hits never reach the executor
```

`services/api/src/app/modules/similarity/adapters/caching.py`. It **implements
`EmbeddingProvider`** and wraps another one, so `domain` and `application` never learn that a cache
exists — `ValidatePhrase` and `SavePhrase` keep calling `provider.embed(text)` and cannot branch on
hit/miss. Installing or removing it is one line in the composition root; `EMBEDDING_CACHE_SIZE=0`
disables it entirely and every test must still pass (that is the kill switch).

### Specification

| Property | Value |
| --- | --- |
| Key | `(provider.model_id, comparison_form)` — `model_id` is `"<EMBEDDING_MODEL>@<EMBEDDING_MODEL_REVISION>"` (the Hub commit SHA the image was built with) |
| Store | `collections.OrderedDict[tuple[str, str], Vector]`, `move_to_end` on hit |
| Bound | `EMBEDDING_CACHE_SIZE` entries (default **512**), evict **least-recently-used** on insert |
| Value | the exact `Vector` object the inner provider returned — stored as-is, never re-serialized |
| Failures | **never cached.** `EmbeddingUnavailable` / `EmbeddingTimeout` propagate and nothing is inserted — no negative caching, so a provider that fails once and recovers succeeds on the very next call |
| Concurrency | `threading.Lock` around dict mutation only; the inner `embed()` runs **outside** the lock |
| Footprint | 384 × float32 = **1 536 B** + key/obj overhead ≈ **2 KB/entry** (**estimate, unmeasured**) → default ≈ **1 MB** |

**Consistency with the spec (item 9).** semantic-validation requires only that the cache be
**bounded with eviction**, that the key include the model identifier, that responses be identical
cold and warm, and that failures not be cached. LRU-512 is one conforming eviction policy and is
kept as designed. Nothing here widens the spec — the design is strictly more specific than it.

**The key is the comparison form, not the raw input.** Normalization
(`domain/normalization.py`) already happens in the use case *before* `embed()` is called, and the
comparison form is what is embedded (see *Normalization, Scores and Ids*);
`EmbeddingProvider.embed` documents that precondition. So `"Comprar leche"`, `"comprar  LECHE"` and
`"Comprar leche "` collapse to one entry, and the cache does not own a second copy of the
normalization rules.

**`model_id` in the key** is what makes a model swap safe: after changing `EMBEDDING_MODEL` no
previously computed vector can be served for the new model, and a dimension change is caught at boot
by the existing typmod coherence check.

**Lock discipline.** The lock protects `OrderedDict` ordering/eviction, never the model
forward pass (estimated at ~50 ms on CPU, **unmeasured** — see Verification Status). Consequence: two threads missing on the same text concurrently will both compute it,
and the second insert simply overwrites an identical value. We accept that duplicated work instead
of adding single-flight — because the function is pure, a redundant computation is *invisible*,
while holding a lock across the forward pass would serialize the whole API. FastAPI runs sync
handlers in a threadpool, so this path really is multi-threaded; `async def` handlers would reach it
through `run_in_threadpool` with the same guarantee.

### Correctness invariant (non-negotiable)

> `embed` is a **pure, deterministic** function of `(model, comparison_form)`. Therefore a cache hit
> and a cache miss produce the *same vector*, and a cold cache and a warm cache produce the
> *byte-identical HTTP response*. The cache is an optimization with **zero** observable semantics.

Three things are consequently **forbidden**, and each is guarded by a test:

1. **Never cache a verdict.** `is_duplicate`, `score`, `most_similar` depend on the *current corpus*,
   which changes on every insert.
2. **Never cache a match page.** `POST /phrases/validate` and `POST /phrases/matches` ALWAYS re-run
   the similarity query against live data. Only the query *vector* is reused.
3. **Never trust a client-supplied score.** The cursor carries `{t, d, i, th}` for ordering only;
   `POST /phrases` recomputes the verdict under the advisory lock, exactly as before.

A repository-call counter test asserts that a warm cache still issues the live queries per request —
one `find_nearest` **and** one `find_matches` on validate, one `find_nearest_exact` (and **zero**
`find_nearest`) on save, one `find_matches` per match page — i.e. the cache can never be "optimized" into skipping a query.

### Blind Save sequence (one computation, two honest calls)

```
user presses Guardar from `idle`          cache            model
────────────────────────────────          ─────            ─────
1. POST /phrases/validate  "Validando..."  MISS  ──embed──► 1 forward pass
                                                            + find_nearest  (live)
                                                            + find_matches  (live, page 1)
2. POST /phrases           "Revalidando..." HIT  (same comparison form)
                                                            + advisory lock
                                                            + find_nearest_exact (live, exact scan)
                                                            + INSERT   (or find_matches → 409 body)
3. 201 → the machine returns to `idle` at once: text cleared, "Frase guardada." announced,
         list refreshed in the background. No label is shown after the 201.
```

**Exactly one embedding computation** when the cache is warm, while **both HTTP calls stay real**.
This is what keeps ADR-005 honest: "Revalidando..." narrates work that is genuinely in flight — a
fresh similarity query against current data plus the locked insert — it just no longer pays for a
redundant forward pass. The cost of a cold start or an eviction between the two calls is one extra
forward pass, i.e. behaviour equal to the pre-cache design.

### Per-page cost model (keyset, no OFFSET, exact scan)

| Request | Embeddings | DB work |
| --- | --- | --- |
| `POST /phrases/validate` (page 1) | 1 (cold) | one `REPEATABLE READ` snapshot: `find_nearest` (HNSW top-1, `LIMIT 1`) + `find_matches` (**exact scan**, `LIMIT limit + 1`) |
| `POST /phrases/matches` page *n≥2* | **0** (hit on `cursor.t`) | 1 exact scan, `LIMIT limit + 1` |
| `POST /phrases/matches`, evicted key | 1 (recompute) | identical |
| `POST /phrases` → 201 | **0** (hit) | exactly **2** statements after the lock: 1 exact top-1 (`find_nearest_exact`) + 1 `INSERT`; **0** HNSW reads; under the advisory lock |
| `POST /phrases` → 409 | **0** (hit) | exactly **2** reads after the lock: `find_nearest_exact` + `find_matches` (page 1 for the `details` payload), both exact; **0** HNSW reads and no `INSERT`; then `ROLLBACK` |

The second read on validate is the price of reporting a below-threshold `most_similar`. It costs no
extra embedding. On save the single read is exact, so it costs one O(n) scan (Option 1; see the honest
cost model) instead of an approximate index probe. `find_nearest` is **not** issued by `/phrases/matches` — pages 2..n carry no verdict
fields, so there is nothing for it to answer.

**Honest cost model.** `find_matches` is an exact scan (D1): every page computes the distance to
every stored row and keeps the best `limit + 1` that pass the keyset predicate. That is **O(n) work
per page, n = stored phrases**; the keyset predicate *filters* rows, it does not *seek*, so page 40
costs the same order as page 1 — it is **not** independent of `n` and HNSW does **not** serve this
`ORDER BY`. This is accepted at the target scale (a scan of ~10⁴ 384-dimension rows is expected to
take milliseconds to tens of milliseconds — an **estimate, unmeasured**; slice 5a records
`EXPLAIN (ANALYZE)` timings on the 500-row and a 10⁴-row fixture). What keyset still buys over
`OFFSET` is **semantics, not speed**: a page is defined by the position it continues from, so a phrase
inserted between two requests cannot shift rows across the boundary (an `OFFSET` page would repeat or
skip them), and the cursor needs no server state. Deep scrolling costs ~1 model forward pass per
*validated text* plus one O(n) scan per page.

**Scaling path (documented, deferred, UNVERIFIED).** pgvector >= 0.8 offers
`hnsw.iterative_scan = strict_order` with a raised `hnsw.max_scan_tuples`, which could let HNSW serve
the filtered, ordered list again. It is not adopted: it is unverified here, and post-filtering with a
scan-tuple cap can still truncate, which is exactly the failure this change removed. Revisit only with
a measured need. The same O(n) cost now applies once per save (`find_nearest_exact`); at this scale it
is accepted for write-path correctness, and any scaling work (an exact-verified candidate window, or
iterative scan) is **deferred** and must keep the "save verdict never depends on approximate recall"
invariant.

Eviction between pages is a latency event, never a correctness event: the recomputed vector may
differ from the original by an ulp and the keyset tolerates that (D16).

### Observability

`CacheStats(hits, misses, evictions, size, capacity)` lives on the decorator and is exposed two ways
(no new dependency):

- `GET /health` includes `data.embedding_cache: {hits, misses, evictions, size, capacity}` — a
  reviewer can *see* the second leg of a blind Save being a hit.
- One `DEBUG` log per miss (`embedding.cache.miss key_len=.. elapsed_ms=..`) and one `INFO` log the
  first time eviction occurs (capacity is undersized for the workload).

The four counters map 1:1 onto Prometheus counters if `prometheus-client` is ever added; we did not
add it for a local demo.

### Multi-worker behaviour

The cache is **per process**. With `uvicorn --workers N` or N API containers there are N caches:
round-robin routing makes the blind-Save hit probability ≈ `1/N` and pages 2..n likewise degrade.
**Correctness is unaffected** — a miss is a recomputation of a pure (near-deterministic) function,
and a recomputed query vector that differs by an ulp is absorbed by the keyset tolerance (D16).
**Bit-identical re-embedding is a non-requirement:** no invariant depends on it, so it is asserted
only as a single-process determinism smoke test. The compose deployment in scope runs a single
worker, so the modelled benefit is the real benefit. (A shared cache is a possible future step; it
is noted in ADR-011 and is not designed here.)

### Embedding timeout and concurrency bound (`BoundedEmbeddingProvider`)

`adapters/bounded.py` decorates the inner provider (the cache sits **outside** it, so hits never
touch it). It owns a `ThreadPoolExecutor(max_workers=EMBEDDING_MAX_CONCURRENCY)` and a
`threading.BoundedSemaphore(EMBEDDING_MAX_CONCURRENCY)`. `embed()` acquires the semaphore within
`EMBEDDING_TIMEOUT_SECONDS` (failure → `EmbeddingTimeout`, so requests can never queue unboundedly),
submits the inner call and waits on `future.result(timeout=EMBEDDING_TIMEOUT_SECONDS)`; a
`concurrent.futures.TimeoutError` becomes `EmbeddingTimeout`, any inner exception becomes/propagates
as `EmbeddingUnavailable`. The semaphore is released by the future's done-callback, **not** when the
caller times out.

**Honest limit:** a running `torch` forward pass is not cancellable. After a timeout the worker keeps
computing until it finishes and keeps its concurrency slot, so a stuck model saturates the bound and
later requests fail fast with `EmbeddingTimeout` instead of piling up threads. The late result is
discarded, never returned and therefore never cached. **Test:** a controllable slow fake blocked on a
`threading.Event` (no sleeps): with a tiny timeout the call raises `EmbeddingTimeout`; while the slot
is still held the next call fails fast; releasing the event frees the slot and a later call
succeeds; the inner call counter proves no extra work was queued.

## Data Model and Migrations

Alembic, hand-written raw SQL via `op.execute`, every revision with a working `downgrade`.

```sql
-- 0001_create_phrases
CREATE EXTENSION IF NOT EXISTS vector;

CREATE TABLE phrases (
  id                     BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
  text                   TEXT        NOT NULL,
  normalized_text        TEXT        NOT NULL,          -- NOT unique as a column; uniqueness is PARTIAL, see index below (D4 / ADR-006)
  embedding              vector(384) NOT NULL,          -- L2-normalized at write
  similarity_score       DOUBLE PRECISION NULL CHECK (similarity_score BETWEEN 0 AND 1),
  most_similar_phrase_id BIGINT      NULL REFERENCES phrases(id) ON DELETE RESTRICT, -- NOT `SET NULL`: nulling only this column would violate phrases_metadata_paired; no delete path exists
  validation_status      TEXT        NOT NULL
                           CHECK (validation_status IN ('unique','duplicate_confirmed')),
  validated_at           TIMESTAMPTZ NOT NULL,
  created_at             TIMESTAMPTZ NOT NULL DEFAULT now(),
  -- score and neighbour are recorded together or not at all; a `unique` row MAY carry both
  -- (a below-threshold nearest neighbour is recorded — see find_nearest_exact).
  CONSTRAINT phrases_metadata_paired CHECK (
    (similarity_score IS NULL) = (most_similar_phrase_id IS NULL)
  ),
  -- a confirmed duplicate always has a neighbour to point at
  CONSTRAINT phrases_confirmed_has_neighbor CHECK (
    validation_status <> 'duplicate_confirmed'
    OR (similarity_score IS NOT NULL AND most_similar_phrase_id IS NOT NULL)
  )
);

CREATE INDEX phrases_created_at_id_idx  ON phrases (created_at DESC, id DESC);
-- serves the unfiltered top-1 `find_nearest` (validate endpoint) ONLY; `find_matches` and
-- `find_nearest_exact` (save path) are exact scans and never use it (D1)
CREATE INDEX phrases_embedding_hnsw_idx ON phrases USING hnsw (embedding vector_cosine_ops);

-- Integrity backstop (ADR-006, ADOPTED): at most one `unique` row per normalized text.
-- `duplicate_confirmed` rows are outside the predicate, so confirmed duplicates stay allowed.
CREATE UNIQUE INDEX phrases_unique_normalized_text_uidx
  ON phrases (normalized_text) WHERE validation_status = 'unique';
```

`downgrade`: drop table (its indexes go with it), then `DROP EXTENSION vector`.

**What each index is for.** HNSW serves **only** `find_nearest` (approximate top-1 for the validate
endpoint, guarded by the recall test). `find_matches` and `find_nearest_exact` never use it: they are
exact scans. The embedding cache (D10) removes
embedding cost, and keyset pagination gives stable page semantics — **not** speed, since the scan
is O(n) per page. `phrases_unique_normalized_text_uidx` is purely for integrity; nothing queries
through it on the hot path. It is owned by migration `0001` (slice 4).

**The coherence constraints changed to match phrase-management.** The earlier
`unique ⇒ most_similar_phrase_id IS NULL` rule directly contradicted the spec's *Below-threshold
neighbor is recorded* scenario (a `unique` row with `similarity_score = 0.55` and
`most_similar_phrase_id = P.id`). It is replaced by two weaker, still-structural facts: score and
neighbour are always written **as a pair**, and a `duplicate_confirmed` row always has both. An
empty store still produces `(NULL, NULL)`, which the pair constraint permits. `similarity_score` is
the **clamped, rounded** 4-decimal value (always in [0, 1]) written by the domain (the `u = 1e-4` unit used in boundary tests),
so the stored history and the reported score are the same number.

### Match query and keyset pagination

Because vectors are L2-normalized, `score = 1 - (embedding <=> q)` before clamping, so **ordering by
distance ascending IS ordering by score descending**. `find_matches` is an **exact scan**: its
transaction sets `enable_indexscan = off` (D1), so the plan is a sequential scan plus a top-N sort,
never an HNSW candidate window. The threshold is expressed on the distance expression, never on the
derived score:

```sql
-- find_matches: threshold-filtered, keyset-paginated, EXACT. Serves `matches` on validate,
-- pages 2..n on /phrases/matches, and page 1 inside a 409 body.
-- Preceded in the same transaction by: SELECT set_config('enable_indexscan', 'off', true);
SELECT id, text, embedding <=> :q AS distance,
       floor((embedding <=> :q) / 1e-6) AS bucket           -- KEY_EPSILON grid (D16)
FROM phrases
WHERE embedding <=> :q <= :max_distance                     -- 1 - threshold + u  (2.0 at t = 0, D13)
  AND ( floor((embedding <=> :q) / 1e-6) >  :cursor_bucket  -- omitted on page 1
        OR (floor((embedding <=> :q) / 1e-6) = :cursor_bucket AND id > :cursor_id) )
ORDER BY bucket, id
LIMIT :limit + 1;                                           -- +1 row decides has_more
```

`:cursor_bucket` is `floor(cursor.d / 1e-6)`, computed in the application with the same IEEE
double arithmetic. The adapter returns raw distances; the **application** converts them to clamped,
rounded scores, applies the exact `Decimal` comparison, stops at the first failing row (the tail
rule) and only then decides `has_more`. `limit` is the effective page size (see *API Contract*),
never a hardcoded 50. The in-memory repository implements the same `(bucket, id)` ordering, so the
shared contract suite covers it.

### Nearest-neighbour query (`find_nearest`)

Separate, unfiltered, and the source of `score` / `most_similar` **on the validate endpoint** when
nothing matches (the write path uses the exact twin `find_nearest_exact`, below):

```sql
-- find_nearest: no threshold, no cursor, exactly one row (or none on an empty store)
-- Preceded in the same transaction by: SELECT set_config('enable_indexscan', 'on', true),
--                                              set_config('hnsw.ef_search', :ef_search, true);
SELECT id, text, embedding <=> :q AS distance
FROM phrases
ORDER BY embedding <=> :q, id
LIMIT 1;
```

**This is the one HNSW read, and it serves the validate endpoint only.** With no `WHERE` clause this is the canonical pgvector k-NN shape, so
the planner can serve `ORDER BY embedding <=> :q` from `phrases_embedding_hnsw_idx` and apply an
*incremental sort* on `id` within the leading-key group to make the tie-break deterministic. It is
approximate: recall is governed by `hnsw.ef_search`. Documented fallback if the two-key `ORDER BY`
ever defeats the planner: wrap a pure k-NN subquery (`ORDER BY embedding <=> :q LIMIT :k`, `k = 10`)
and re-sort by `(distance, id)` in an outer query — same result, same index, one extra sort of at
most `k` rows. On a small table Postgres would pick a sequential scan anyway (an unmeasured
expectation, see Verification Status), which is why the guard tests below force the arm under test.

### Exact nearest-neighbour query (`find_nearest_exact`, write path)

```sql
-- find_nearest_exact: same shape and tie-break as find_nearest, but an EXACT scan.
-- Preceded in the same transaction by: SELECT set_config('enable_indexscan', 'off', true);
-- (identical planner setting to find_matches, so no HNSW scan is used)
SELECT id, text, embedding <=> :q AS distance
FROM phrases
ORDER BY embedding <=> :q, id
LIMIT 1;
```

Used **only** by `SavePhrase`, inside the save transaction, after the advisory lock. The query text is
the same as `find_nearest`; only the planner setting differs, so the result is the true nearest
neighbour (a full distance computation plus top-1 sort, O(n)). Implementations MAY realize it as
`find_matches` with `limit = 1`, `max_distance = 2.0` (no effective threshold filter) and no cursor,
provided the same exact planner settings apply; a dedicated method is preferred because it keeps the
"no threshold" contract explicit and the raw `(distance, id)` order (no keyset bucket) intact.

**Planner and session settings on pooled connections.** `hnsw.ef_search`, `enable_indexscan` and
`lock_timeout` are applied with `set_config(name, value, true)` — the parameterizable equivalent of
`SET LOCAL` — at the start of every query transaction, by the repository method that needs them
(`find_nearest` sets `enable_indexscan=on` and `hnsw.ef_search`; `find_matches` and
`find_nearest_exact` set `enable_indexscan=off`; the save transaction sets `lock_timeout`). They are **transaction-scoped**,
so they vanish at commit/rollback and can never leak into another request through a pooled
connection; a plain connection-level `SET` or a startup `options` parameter is never used, and no
method relies on a setting another method made.

**Snapshot consistency.** `ValidatePhrase` issues `find_nearest` and `find_matches` inside **one
read transaction** opened as `BEGIN ISOLATION LEVEL REPEATABLE READ READ ONLY` through the
`UnitOfWork` port (D17). `READ ONLY` alone would **not** be enough: under the default
`READ COMMITTED` every statement takes its own snapshot, so a writer committing between the two
statements would be visible to the second only. `REPEATABLE READ` fixes one snapshot at the first
statement. The **integration test is deterministic, not timing-based**: the pgvector adapter accepts
a test hook (`after_statement(n)`) and the test uses two `threading.Event` barriers — the hook
pauses after `find_nearest`, a second connection inserts a higher-scoring phrase and commits, the
hook resumes — then asserts that neither statement saw the new row and that
`most_similar == matches[0]`. A control run of the same barrier scenario at `READ COMMITTED` shows
the divergence, proving the test can fail.

**Reconciliation rule.** `find_nearest` is approximate and orders by raw `(distance, id)`, while
`find_matches` is exact and orders by `(bucket, id)`. To make the spec's *`most_similar` MUST equal
`matches[0]`* invariant hold **by construction** instead of by coincidence, `ValidatePhrase` takes
`score`, `most_similar` and `is_duplicate` from `matches[0]` whenever `matches` is non-empty (the
exact scan is authoritative for the head of the list) and uses `find_nearest` only when `matches` is
empty (the below-threshold neighbour, or `None` on an empty store). A unit test asserts the
invariant on both repository adapters, including a spy repository whose `find_nearest` returns a
worse neighbour than `matches[0]`.

**The write path never reads HNSW (Option 1).** `SavePhrase` derives its verdict (`is_duplicate`,
`score`, `most_similar`) and the metadata it records on the row from `find_nearest_exact` — an exact
scan taken inside the save transaction under the advisory lock — so an HNSW recall miss can never let
a duplicate through as `unique`. It issues `find_matches` **only** on the rejection path, to build the
409 `details` payload, inside the same transaction, before the rollback; there `matches[0]` wins over
`find_nearest_exact` by the same reconciliation rule (the two can differ in id only inside one 1e-6
bucket). The former "accepted residual" is therefore removed.

**Bit-identical re-embedding is NOT a requirement.** An earlier draft made keyset correctness depend
on the recomputed query vector being bit-identical to the one that produced the cursor. That claim
is dropped: cache eviction or another worker can legitimately recompute a vector that differs by an
ulp, and the keyset tolerates it (D16). The cache still stores the exact `Vector` object (no
serialization), and a single-process determinism smoke test (embed twice → identical) remains as a
cheap sanity check, but nothing else depends on it. Instead a **perturbed-vector test** pages a
fixture to the end with each page's query vector perturbed by one float32 ulp per component and
asserts no id is repeated or skipped (fixture distances chosen away from grid edges, so the test is
deterministic).

**Guards (all `integration`, all non-vacuous).** (1) *Recall guard, `find_nearest` (validate) only:* seed a
corpus **larger than `ef_search`** (e.g. 1 000 rows against the default 200) and, for a few hundred
query vectors, compare the HNSW top-1 — forced with `SET enable_seqscan = off` for the arm under
test — against the exact top-1 obtained with `SET enable_indexscan = off`; results must be identical.
Without the corpus size and the forced plan the planner would pick a sequential scan on both arms and
the test would compare exact against exact. (2) *`EXPLAIN` guards:* `find_nearest` (with
`enable_seqscan = off`) contains an Index Scan on `phrases_embedding_hnsw_idx` and no full-table
`Sort`; `find_matches` and `find_nearest_exact` contain **no** HNSW index scan. (2b) *Save never uses
HNSW:* a spy on the pgvector adapter shows `SavePhrase` issues `find_nearest_exact` and never
`find_nearest`, and a *recall-miss* test forces a fixture where the HNSW top-1 misses a stored
duplicate (index scan forced with `enable_seqscan = off`, tiny `hnsw.ef_search`, corpus larger than it)
while `find_nearest_exact` returns it, and asserts the save answers 409 (not 201 `unique`). (3) *Completeness:* 500 matches (more than the
former candidate window of 200) paged to the end — every id delivered exactly once, none missing.

**Oracle equivalence test:** the same fixture is scored through the pure-Python domain cosine and
through pgvector; the two must agree to **1e-5**. This is what keeps "domain owns meaning, adapter
owns computation" from drifting.

**Why 1e-5 and not 1e-6.** pgvector's `vector` type stores each component as **float32**, while the
domain cosine accumulates in Python float64. A write/read round-trip therefore costs ~1e-7 relative
error per component, and summing 384 of them plus the differing accumulation order puts the worst
case comfortably above 1e-6 — a 1e-6 gate would be a flaky test asserting something the storage
format cannot deliver. 1e-5 is **five times tighter than the half-rounding-unit** `u/2 = 5e-5`, so
a discrepancy at tolerance can only alter a reported 4-decimal score for raw values lying within
1e-5 of a rounding boundary; the calibration and boundary fixtures deliberately sit further than
that from any boundary, so the test is deterministic rather than merely usually-green. (The
semantic-validation spec states the same 1e-5 figure.)

### Cursor format

Opaque to clients (documented as such in OpenAPI; clients MUST NOT parse it — the shape may change
without a version bump of the API):

```
base64url( {"v":1, "t":"<comparison form>", "d":<raw distance>, "i":<id>, "th":<threshold>} )
```

`t` is the **comparison form** — the same string that keys the cache and feeds `embed()` — so a
cursor issued for `"Comprar leche"` is accepted for `"  comprar   LECHE "` and rejected for any
genuinely different text. `d` is the **raw** distance of the last delivered row, never a rounded
score; the keyset position is derived from it as `floor(d / 1e-6)` (D16). `i` is an integer even
though the API serializes ids as strings; the cursor is opaque, so no client ever sees it.

**Strict validation, before anything is embedded.** Decoding is strict: base64url with no
tolerated garbage, a JSON *object* (parse with `NaN`/`Infinity` literals rejected), exactly the five
keys, and per-field rules — `v` equals the supported version; `t` is a string; `d` is a finite
number in `[0, 2]`; `i` is a positive integer that fits int64 (booleans rejected); `th` is a finite
number in `[0, 1]`; the encoded length does not exceed a maximum derived from the settings
(`4 * ceil((12 * PHRASE_MAX_LENGTH + 128) / 3)` characters: worst-case casefold expansion × UTF-8
width, base64-inflated). **Any** violation — malformed, wrong type, out of range, extra or missing key,
oversized — is `400 INVALID_CURSOR`. A table-driven unit test covers one case per rule and asserts
`FakeEmbedder.call_count == 0` for each.

`th` is carried so a threshold change mid-scroll cannot corrupt a page sequence: on mismatch the API
returns `400 INVALID_CURSOR` and the UI restarts validation. **The cursor is decoded and validated
before anything is embedded**, so a malformed cursor costs zero forward passes — `ListMatches`
orders its steps decode → validate fields → compare `t` and `th` → embed → query.

The 409 payload's `next_cursor` is produced by the **same encoder from the same query vector**, so
a client continuing a conflict page through `POST /phrases/matches` is indistinguishable from one
continuing a validate page.

## Concurrency

```
-- embed() happens BEFORE this block, outside any transaction
with uow(isolation=READ_COMMITTED):        -- BEGIN; default isolation (see below)
  SET LOCAL lock_timeout = LOCK_TIMEOUT_MS;
  SELECT pg_advisory_xact_lock(hashtext('phrases:validate_and_insert'));
  find_nearest_exact(q)                 -- score + neighbour, unfiltered, LIMIT 1, EXACT scan (no HNSW)
  verdict = clamped, rounded score >= threshold
  if verdict and not confirm_duplicate:
      find_matches(q, page 1)           -- only to fill the 409 details payload
      uow.rollback()                    -- 409, nothing persisted
  else:
      INSERT INTO phrases (..., similarity_score, most_similar_phrase_id, ...);
      uow.commit()                      -- lock released automatically
```

Scope: taken by `SavePhrase` only, at the top of the save transaction, before any read; released by
commit **or** rollback. `ValidatePhrase` takes **no** lock — it is advisory by design, and its own
two reads share a `REPEATABLE READ` read-only snapshot instead.

**Two isolation levels, on purpose.** Validate is `REPEATABLE READ READ ONLY` (D17). Save stays
**`READ COMMITTED`**: a repeatable-read snapshot is fixed at the transaction's first statement, and
if that statement came before the wait on the advisory lock, the snapshot would be frozen *before*
the commit the lock was waiting for — the very commit the check must see. Under `READ COMMITTED`
each statement after the lock sees everything committed before it. Because the verdict read is an
exact scan under that lock, the whole save decision (verdict, recorded metadata) is independent of
HNSW recall and of any approximate index state. On the 409 path `find_nearest_exact`
and `find_matches` therefore run as two statements, but every in-application writer is serialized by
the same lock, so both observe the same data; only a lock-bypassing writer could interleave, which is
the documented residual race.

**Bounded lock wait.** `SET LOCAL lock_timeout` (`LOCK_TIMEOUT_MS`, default 5 000) is set before the
advisory lock so a stuck holder cannot pin every save indefinitely. SQLSTATE `55P03` maps to a
domain `LockTimeout`, answered as `500 INTERNAL_ERROR` (no dedicated code; nothing persisted, the
client may retry).

**What is recorded, always.** The insert writes `similarity_score` and `most_similar_phrase_id`
from `find_nearest_exact` **regardless of the verdict**. A `unique` row whose closest neighbour scored
0.55 stores `(0.55, P.id)`; only an empty store yields `(NULL, NULL)`. This is the behaviour the
`phrases_metadata_paired` constraint now encodes, and it is why `SavePhrase` cannot reuse the
threshold-filtered query.

Embedding happens *before* `BEGIN` so a slow model never holds the write lock; a provider failure or
timeout therefore aborts before the lock is taken and nothing is persisted.

**Two layers, honestly scoped** (ADR-006):

- *Identical text* (same `normalized_text`, status `unique`): guaranteed by the database through
  `phrases_unique_normalized_text_uidx`. Even a path that bypasses the lock — direct SQL, a future
  endpoint that forgets it, a second deployment with another lock key, an application bug — cannot
  store two `unique` rows with the same normalized text. A `duplicate_confirmed` row with that text
  is still accepted.
- *Semantic near-duplicates* (different text, high similarity): **not** covered by any index; there
  is no constraint that can express "cosine >= threshold". They remain protected only by this lock
  plus application logic. **Documented residual race**: a path that bypasses the lock (or the
  window where a reader validated earlier and a similar phrase was committed since) can still land
  two unconfirmed near-duplicates, and the database will accept them.

**Unique-violation mapping (never a 500).** The insert inside the save transaction may raise a
unique violation (SQLSTATE `23505`, constraint `phrases_unique_normalized_text_uidx`) only when the
lock was bypassed or lost a race. The pgvector adapter translates exactly that constraint into a
domain error `DuplicateTextConflict` (other integrity errors are not swallowed). `SavePhrase` then
rolls back (the transaction is aborted) and **retries the whole check-and-insert once**: the retry
runs in a fresh transaction under the lock, `find_nearest_exact` sees the now-committed identical row at
score `1.0`, and, because `confirm_duplicate` is false (a confirmed save is inserted as
`duplicate_confirmed` and cannot violate the index), the normal path answers **409
`DUPLICATE_CONFIRMATION_REQUIRED`** with the full validate-shaped payload. Justification: reusing the
normal path guarantees the 409 body is identical to any other conflict (one code path, one payload
builder) instead of hand-assembling a second one from a poisoned transaction. The retry is bounded
to one attempt; if the second attempt still raises `DuplicateTextConflict` (not expected, no delete
path exists) it is surfaced as the same 409 built from a fresh read-only snapshot, never as a 500. Both attempts
are opened through the `UnitOfWork` port by the application layer (no adapter import), and the
in-memory fake raises `DuplicateTextConflict` once (then always) so the retry path is unit-tested
without a database.

## Configuration

`pydantic-settings` `Settings` instantiated in `main.py` **before** the app is created, so invalid
config exits non-zero and is visible in `docker compose up` output.

| Var | Default | Startup validation |
| --- | --- | --- |
| `DATABASE_URL` | — | required, `postgresql+psycopg://` scheme |
| `POSTGRES_USER` / `POSTGRES_PASSWORD` / `POSTGRES_DB` | see `.env.example` | consumed by the `db` compose service and its healthcheck |
| `SIMILARITY_THRESHOLD` | `0.80` | float, `0 <= t <= 1`; **working default, finalized after the first measured slow run (slice 9)** |
| `MATCHES_PAGE_SIZE` | `50` | int, 1..200; also the max accepted `limit` |
| `PHRASE_MAX_LENGTH` | `280` | int, 1..4000; **working default pending calibration**; the raw pre-normalization cap is `4 × PHRASE_MAX_LENGTH` |
| `PHRASES_LIST_LIMIT` | `200` | int, 1..1000; hard cap on `GET /phrases` |
| `MAX_REQUEST_BYTES` | `1048576` | int >= 4096; request bodies above it are rejected with 413 before parsing |
| `EMBEDDING_PROVIDER` | `sentence_transformers` | runtime enum has ONE value; `fake` exists only in the test settings class and is rejected by the runtime `Settings` |
| `EMBEDDING_MODEL` | `sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2` | non-empty |
| `EMBEDDING_MODEL_REVISION` | Hub commit SHA (value recorded in slice 8; **unverified**) | 40 hex characters; also a Docker build arg; part of `model_id` |
| `EMBEDDING_DIMENSIONS` | `384` | must equal provider dim **and** the `vector(n)` column typmod |
| `EMBEDDING_TIMEOUT_SECONDS` | `10.0` | float > 0 |
| `EMBEDDING_MAX_CONCURRENCY` | `2` | int >= 1; executor size and semaphore of `BoundedEmbeddingProvider` |
| `EMBEDDING_CACHE_SIZE` | `512` | int >= 0; **0 disables** the decorator (≈ 1 MB at the default, estimate) |
| `HNSW_EF_SEARCH` | `200` | int, 1..1000; applies to the validate endpoint's `find_nearest` only (never to the save path) |
| `LOCK_TIMEOUT_MS` | `5000` | int >= 1; bounds the wait for the save advisory lock |
| `CORS_ORIGINS` | `http://localhost:3000` | comma-separated absolute origins, no wildcard |
| `LOG_LEVEL` | `INFO` | enum |
| `HF_HUB_OFFLINE` / `TRANSFORMERS_OFFLINE` | `1` | fixed in the image; runtime never downloads; not in `.env.example` |
| `SENTENCE_TRANSFORMERS_HOME` | `/opt/models` | bake target, fixed in the image; not in `.env.example` |
| `NEXT_PUBLIC_API_URL` | `http://localhost:8000` | browser-facing, **build arg** |
| `NEXT_PUBLIC_PHRASE_MAX_LENGTH` | `280` | **build arg**; the UI's counter limit, kept equal to `PHRASE_MAX_LENGTH` (compose passes one value to both) |
| `API_INTERNAL_URL` | `http://api:8000` | server-side fetch (Server Components) only |

`.env.example` lists every row above **except** the two image-fixed ones (this equals the list in
the api-contract spec). CORS is configured with methods `GET, POST, OPTIONS`, header `Content-Type`
and `allow_credentials=False`.

**Dimension coherence check at startup**: read the column typmod and compare against
`provider.dimensions` and `EMBEDDING_DIMENSIONS`; mismatch aborts boot. A model swap that silently
writes 768-dim vectors into a `vector(384)` column is caught at boot, not at the first insert.

**Model baked at build**: a Dockerfile stage downloads the checkpoint into `/opt/models` with
`snapshot_download(repo_id=EMBEDDING_MODEL, revision=EMBEDDING_MODEL_REVISION)`; both are build args
and the build fails if the revision is not a 40-hex commit SHA, so a rebuild can never silently pull
different weights (the SHA is also part of `model_id`, hence of the cache key). The runtime stage
copies the weights and runs fully offline. Reproducible for a reviewer with no network, and no
cold-start download.

### `GET /health` (readiness)

200 **only** when `SELECT 1` succeeds **and** the model is loaded. The handler itself runs
**no embedding** — the model is warmed once in the lifespan startup hook (one embed of a fixed
sentinel string) which flips an in-process `model_ready` flag; `/health` reads the flag and pings
the database, nothing more. The sentinel occupies exactly one cache entry and never masks a user's
cold miss: it proves the model loads, not that the cache works.

**One key mapping, everywhere** (spec, this JSON, the error registry, D15, tests): `model` is the
**readiness string** `"ready"` | `"unavailable"`; `embedding_model` is the **model-name string**.

```jsonc
// 200
{"data": {
  "status": "ok",
  "database": "ok",
  "model": "ready",
  "dimensions": 384,
  "embedding_model": "sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2",
  "embedding_cache": {"hits": 12, "misses": 3, "evictions": 0, "size": 3, "capacity": 512}
}}

// 503
{"error": {"code": "NOT_READY", "message": "service is not ready",
           "details": {"database": "ok", "model": "unavailable",
                       "dimensions": 384,
                       "embedding_model": "sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2"}}}
```

`status`, `database`, `model`, `dimensions`, `embedding_model` and `embedding_cache` are all
spec-pinned (the api-contract *Ready* scenario requires their presence and allows a superset). The
503 `details` use the same keys, with `dimensions`, `embedding_model` and `embedding_cache` included
where known, so a failing healthcheck says *which* dependency is down instead of just "not ready".
`NOT_READY` exists for `/health` only and is never raised by a business endpoint.

The compose healthcheck uses this endpoint, `web` waits on `service_healthy`, and the `api`
healthcheck carries a generous `start_period` and `retries` because a cold model load is slow
(see *Docker Compose*).

## API Contract and Error Mapping

Success envelope `{"data": ...}`, error envelope `{"error": {"code", "message", "details"?}}`.
Messages are English developer text; the UI owns all user-facing Spanish copy, keyed by `code`.

### Error registry (matches api-contract exactly)

| Condition / domain error | HTTP | `code` | `details` |
| --- | --- | --- | --- |
| `InvalidCursor` — malformed, violating a cursor field rule, oversized, or issued for a different comparison form or threshold | 400 | `INVALID_CURSOR` | — |
| unknown route | 404 | `NOT_FOUND` | — |
| wrong method on a known route | 405 | `METHOD_NOT_ALLOWED` | — |
| `DuplicateConfirmationRequired` | 409 | `DUPLICATE_CONFIRMATION_REQUIRED` | **full validate-shaped payload** (below) |
| `PayloadTooLarge` — body above `MAX_REQUEST_BYTES` | 413 | `PAYLOAD_TOO_LARGE` | — |
| `EmptyPhraseText` / `PhraseTooLong` (post-normalization **or** raw > 4 × `PHRASE_MAX_LENGTH`) / schema violation / wrong JSON type / bad `limit` / missing `cursor` / malformed JSON | 422 | `VALIDATION_ERROR` | `{"fields":[{"field","reason"}], "max_length"?}` |
| unhandled exception, **including database unreachable on any endpoint but `/health`** and `LockTimeout` on save (no dedicated codes exist for these) | 500 | `INTERNAL_ERROR` | none — never a stack trace or internal detail |
| `EmbeddingUnavailable` (provider raised / model not loaded) | 503 | `EMBEDDING_UNAVAILABLE` | — |
| `NotReady` — **`/health` only** | 503 | `NOT_READY` | `{"database": "ok"\|"unavailable", "model": "ready"\|"unavailable", "dimensions"?, "embedding_model"?, "embedding_cache"?}` |
| `EmbeddingTimeout` (> `EMBEDDING_TIMEOUT_SECONDS`, or no concurrency slot within it) | 504 | `EMBEDDING_TIMEOUT` | — |

`VALIDATION_ERROR.reason` is drawn from `empty | too_long | required | invalid_type |
out_of_range`; `too_long` additionally sets `details.max_length`. There is deliberately **no**
`EXACT_DUPLICATE` code — an exact duplicate is an ordinary duplicate that scores 1.0. A bad cursor
is **not** a `VALIDATION_ERROR`: it is `400 INVALID_CURSOR`. A *missing* `cursor` on
`/phrases/matches` is a schema violation and therefore 422.

Mapping lives in one registry dict in `platform/errors.py` with a single
`@app.exception_handler(DomainError)`. Because 404/405/413/422 and unhandled exceptions are produced
by the framework rather than by our routers, `main.py` also registers handlers for
`StarletteHTTPException` (→ `NOT_FOUND` / `METHOD_NOT_ALLOWED`), `RequestValidationError` (→
`VALIDATION_ERROR`, translating pydantic's `loc`/`type` into `fields[].field`/`reason`), a
body-size guard (→ `PAYLOAD_TOO_LARGE`, checked from `Content-Length` and by counting streamed bytes
before JSON parsing) and a catch-all (→ `INTERNAL_ERROR`), so **every** non-2xx response wears the
envelope. **The catch-all is implemented as a middleware that sits INSIDE `CORSMiddleware`**, not as
`@app.exception_handler(Exception)`: Starlette runs the latter in `ServerErrorMiddleware`, which
wraps the whole user stack *outside* CORS, so a 500 would reach the browser without
`Access-Control-Allow-Origin` and the frontend could not read the envelope. Routers raise domain
errors; they never build HTTP responses for failures. A `contract`-marked test asserts every `code`
in the registry appears in the OpenAPI document, a second walks 404/405/413/422/500 end to end, and
a third asserts that a forced 500 for an allowed `Origin` still carries `Access-Control-Allow-Origin`.

### Request shapes

| Endpoint | Body | Notes |
| --- | --- | --- |
| `POST /phrases/validate` | `{text, limit?}` | `text` bounded to `4 × PHRASE_MAX_LENGTH` code points **before** normalization (schema field bound → `too_long`); `limit` **optional**, a **strict** integer (`StrictInt`: `"10"`, `true`, `10.5` → 422 `invalid_type`), default `MATCHES_PAGE_SIZE`, range `[1, MATCHES_PAGE_SIZE]`; a `cursor` key is **ignored** (page 1 is returned) |
| `POST /phrases/matches` | `{text, cursor, limit?}` | `cursor` **required** (bounded length, strictly validated — see *Cursor format*); `limit` optional with the identical strict bounds |
| `POST /phrases` | `{text, confirm_duplicate?}` | `confirm_duplicate` is **`StrictBool`** (`"yes"`, `1`, `"true"` → 422 `invalid_type`, never coerced); unknown fields **ignored** (`extra="ignore"`); a client-sent `score`/`status`/`validated_at` never reaches the domain |
| `GET /phrases` | — | no parameters, **not paginated**, hard-capped at `PHRASES_LIST_LIMIT` newest items (default 200; older phrases are not reachable through the API in this change — documented limitation). The repository port takes only a `limit`; there is no cursor argument |

One shared `PageLimit` annotated type (strict int) owns the `[1, MATCHES_PAGE_SIZE]` rule so the two
endpoints cannot drift, and `MATCHES_PAGE_SIZE` is injected from settings rather than hardcoded — the
"`MATCHES_PAGE_SIZE=10` ⇒ page 1 has 10 items" scenario is then a settings test, not a code path.
Strictness is covered by contract tests for `"yes"`, `1` and `"true"` on `confirm_duplicate` and for
`"10"`, `true` and `10.5` on `limit`.

### The 409 body carries a complete validate response

`DUPLICATE_CONFIRMATION_REQUIRED.details` is `{threshold, score, most_similar, matches,
next_cursor, has_more}` — the *same shapes* as a 200 validate payload, with `matches` being page 1
at `MATCHES_PAGE_SIZE`. The client can therefore render the duplicate alert, including its
infinite-scroll list, **without a second round-trip**, and `details.next_cursor` is directly usable
with `POST /phrases/matches`. This is why `SavePhrase` issues `find_matches` on the rejection path:
the 409 is not an error message, it is a verdict delivery with an error status.

## Interfaces / Contracts

```python
# modules/similarity/contracts.py
class EmbeddingProvider(Protocol):
    model_id: str                               # "<model>@<revision sha>" — part of the cache key
    dimensions: int
    def embed(self, text: str) -> Vector: ...   # PRE: text is ALREADY normalized (domain rules)
                                                # POST: L2-normalized, len == dimensions, pure
    def check_ready(self) -> None: ...          # raises EmbeddingUnavailable

# modules/similarity/adapters/bounded.py
class BoundedEmbeddingProvider:                 # timeout + concurrency bound (see its section)
    def __init__(self, inner: EmbeddingProvider, timeout_seconds: float, max_concurrency: int): ...

# modules/similarity/adapters/caching.py
class CachingEmbeddingProvider:                 # implements EmbeddingProvider by delegation
    def __init__(self, inner: EmbeddingProvider, max_size: int): ...
    def embed(self, text: str) -> Vector:       # LRU on (inner.model_id, text); lock only on the
        ...                                     # dict, never around inner.embed()
    @property
    def stats(self) -> CacheStats: ...          # hits, misses, evictions, size, capacity

ROUNDING_DECIMALS = 4
ROUNDING_UNIT = 1e-4                            # domain constant, NOT configuration
KEY_EPSILON = 1e-6                              # keyset tolerance grid (D16), domain constant

@dataclass(frozen=True)
class SimilarityPolicy:
    threshold: float                            # validated in [0, 1]; compared as Decimal(str(x))
    def score(self, raw_distance: float) -> float: ...         # round(min(1, max(0, 1 - d)), 4)
    def is_duplicate(self, score: float | None) -> bool: ...   # PRE: already clamped + rounded.
                                                               # score >= threshold, inclusive, Decimal
    def includes(self, raw_distance: float) -> bool: ...       # is_duplicate(score(d))
    def max_distance(self) -> float: ...        # WIDENED SQL bound (D13): 1 - threshold + ROUNDING_UNIT,
                                                # 2.0 when threshold == 0. A superset of `includes`.

# modules/phrases/contracts.py
class Isolation(Enum):
    READ_COMMITTED = "READ COMMITTED"           # save (must see the commit the lock waited for)
    REPEATABLE_READ = "REPEATABLE READ"         # validate (one snapshot for the pair)

class UnitOfWork(Protocol):                     # one transaction; lets the application layer say
    repo: PhraseRepository                      # BEGIN/ROLLBACK/retry without importing an adapter
    def __enter__(self) -> "UnitOfWork": ...    # BEGIN [ISOLATION LEVEL ..] [READ ONLY]
    def __exit__(self, *exc) -> None: ...       # rolls back unless commit()/rollback() already ran
    def commit(self) -> None: ...
    def rollback(self) -> None: ...

class UnitOfWorkFactory(Protocol):
    def __call__(self, *, isolation: Isolation = Isolation.READ_COMMITTED,
                 read_only: bool = False) -> UnitOfWork: ...

class PhraseRepository(Protocol):               # always bound to ONE UnitOfWork's transaction
    def add(self, phrase: NewPhrase) -> Phrase: ...
    def list_recent(self, limit: int) -> list[Phrase]: ...      # newest first; no cursor argument

    def find_nearest(self, q: Vector) -> Neighbor | None: ...
        # Unfiltered top-1 over the WHOLE store, ordered (distance asc, id asc). HNSW in pgvector.
        # None only when the store is empty. NO threshold, NO cursor, NO limit argument.
        # VALIDATE endpoint only: source of `score` / `most_similar` when nothing matches.
        # MUST NOT be called by SavePhrase (approximate; see find_nearest_exact).

    def find_nearest_exact(self, q: Vector) -> Neighbor | None: ...
        # SAME contract as find_nearest (unfiltered top-1 over the WHOLE store, ordered
        # (distance asc, id asc), None only on an empty store, NO threshold/cursor/limit argument)
        # but an EXACT scan: enable_indexscan off (same planner settings as find_matches), never
        # HNSW. Used ONLY by SavePhrase, inside the save transaction under the advisory lock.
        # Source of the save verdict and of the recorded score/most_similar metadata.

    def find_matches(self, q: Vector, max_distance: float,
                     limit: int, cursor: MatchCursor | None) -> Page[Match]: ...
        # EXACT scan. Threshold-filtered (widened bound) + keyset on (bucket, id). Returns RAW
        # distances; the application clamps/rounds, applies `includes`, and applies the tail rule.

    def lock_for_write(self) -> None: ...        # SET LOCAL lock_timeout + pg_advisory_xact_lock;
                                                 # no-op in-memory

@dataclass(frozen=True)
class Neighbor:                                  # what find_nearest / find_nearest_exact return
    id: int                                      # BIGINT; serialized as a string at the API edge
    text: str                                    # display form
    distance: float                              # RAW; the use case turns it into a score
```

`FakeEmbedder` uses a lookup table keyed on the comparison form so unit tests can produce **exact**
scores at `t`, `t - u`, `t + u`, at the rounding boundaries `t - u/2 ± 1e-5`, and for a **negative raw
cosine** (clamp test). Texts that must tie map to the **same, bit-identical vector object**, so the
id tie-break is exercised with genuinely equal raw distances (the "displayed tie, distinct raw
distance" fixture uses distinct vectors). It exposes a **`call_count`** so tests can assert *how many
times* the model was actually invoked (this is how every efficiency claim in D10 is proved, rather
than asserted); a `FailingEmbedder` variant raises `EmbeddingUnavailable` / `EmbeddingTimeout` on
demand, and a controllable slow variant blocks on a `threading.Event`.
`InMemoryPhraseRepository` implements the same `(bucket, id)` keyset ordering **and the same
`find_nearest` / `find_nearest_exact` tie-break** using the domain cosine (in memory both are exact,
so a test double can additionally make `find_nearest` return a deliberately wrong neighbour to prove
the save path ignores it), and an in-memory `UnitOfWork` gives a
snapshot copy under `REPEATABLE_READ`, buffers writes until `commit()` and can raise
`DuplicateTextConflict` once to cover the retry path. Both repository implementations are driven by
a **shared contract test suite** parametrized over the two adapters — so the fast fake cannot drift
from the real one. The suite covers `find_nearest` and `find_nearest_exact` explicitly: empty store → `None`,
best-below-threshold → the neighbour is still returned, equal distances → lowest `id` wins, and,
whenever `find_matches` is non-empty, both have the same 4-decimal score as `matches[0]`
(the ids may differ only inside one 1e-6 bucket, which the reconciliation rule resolves in favour of
`matches[0]`).

## Data Flow

```
  Browser (apps/web)                       services/api                          Postgres+pgvector
  ─────────────────                        ───────────                           ─────────────────
  [PhraseForm] ──POST /phrases/validate──► router ──► ValidatePhrase
              {text, limit?}                           │  display_form → comparison_form
                                                       │  embed(cmp) ─► [LRU] ─MISS─► SentenceTransf.
                                                       │  ┌─ uow(REPEATABLE READ, read-only) ──────┐
                                                       │  │ find_nearest   → top-1 neighbour       │ HNSW
                                                       │  │ find_matches   → page 1 (widened bound)│ exact scan
                                                       │  └────────────────────────────────────────┘
                                                       │  clamp+round → policy → tail rule → has_more
                                                       │  matches[0] (if any) wins over find_nearest
                                         ◄── {is_duplicate, threshold, score, most_similar,
                                              matches[..limit], next_cursor, has_more}
  [MatchList] ──POST /phrases/matches────► router ──► ListMatches
       (scroll) {text, cursor, limit?}                 │  decode cursor + check t/th  ─► 400 INVALID_CURSOR
                                                       │       (rejected BEFORE any embed)
                                                       │  embed(cursor.t) ─► [LRU] ─HIT (0 passes)
                                                       │  find_matches ──── always live ──► exact scan (O(n))
                                         ◄── {matches[..limit], next_cursor, has_more}

  [Confirm] ────POST /phrases ───────────► router ──► SavePhrase
             {text, confirm_duplicate?}              │ embed ─► [LRU] ─HIT─►  uow(READ COMMITTED)
                                                     │           lock_timeout + advisory_xact_lock
                                                     │           find_nearest_exact ← always live, exact
                                                     │           verdict = round(score) >= t
                                                     │             ├─ dup & !confirm → find_matches
                                                     │             │                   → ROLLBACK → 409
                                                     │             └─ else → INSERT (score+neighbor
                                                     │                        recorded even if unique)
                                         ◄── 201 {data: phrase}
                                           | 409 DUPLICATE_CONFIRMATION_REQUIRED
                                             details = {threshold, score, most_similar,
                                                        matches, next_cursor, has_more}

  [LRU] = CachingEmbeddingProvider (D10). Only the query VECTOR is reused; every verdict, every
  nearest-neighbour lookup and every match page is recomputed against current data.

  First paint: [Server Component] ──GET /phrases (API_INTERNAL_URL)──► router ──► ListPhrases
```

## Frontend

```
apps/web/src/
├── app/page.tsx                       # Server Component: fetches GET /phrases for first paint
├── features/phrases/
│   ├── machine.ts                     # pure reducer — no React, no fetch, 100% unit-testable
│   ├── hooks/usePhraseValidation.ts   # binds reducer to the API client
│   ├── hooks/useInfiniteScroll.ts     # IntersectionObserver sentinel
│   └── components/{PhraseForm,ValidationProgress,DuplicateAlert,MatchList,PhraseList,StatusBadge}.tsx
├── lib/api/{client.ts,errors.ts}
├── i18n/copy.es.ts                    # THE copy table (phrase-ui) + errorCopy: Record<ErrorCode, CopyKey>
└── types/api.ts                       # generated by openapi-typescript from /openapi.json
```

**First paint and list refresh.** `app/page.tsx` is a Server Component that fetches
`GET {API_INTERNAL_URL}/phrases` and MUST opt out of static rendering: it exports
`const dynamic = 'force-dynamic'` **and** calls `fetch(url, { cache: 'no-store' })`. Without them Next
would render the list once at build time (no API exists then) and serve it stale forever. It passes
the result as `initialItems` to the client `PhraseList`, which owns the list state. After a 201 the
client refetches `GET {NEXT_PUBLIC_API_URL}/phrases` from the browser and replaces its state — no
`router.refresh()`, no reload. A failed refetch is a non-blocking list error, never a save error.

### State machine

States: `idle | validating | revalidating | duplicate | ok | saving | error`.
Events: `EDIT_TEXT | VALIDATE | VALIDATE_OK | SAVE | SAVE_OK | CONFLICT | FAIL | CONFIRM | CANCEL | LOAD_MORE | PAGE_OK`.

| From | Event | To | Progress label |
| --- | --- | --- | --- |
| `idle` | `VALIDATE` | `validating` | `progress.validating` — "Validando..." |
| `validating` | `VALIDATE_OK{unique}` | `ok` | — (`validation.ok`) |
| `validating` | `VALIDATE_OK{duplicate}` | `duplicate` | — (page 1 of matches already loaded) |
| `idle` | `SAVE` | `validating` → `revalidating` | "Validando..." → "Revalidando..." (validate says unique, then the save call runs) |
| `ok` | `SAVE` | `revalidating` | "Revalidando..." — one call, the server still re-validates |
| `duplicate` | `CONFIRM` | `saving` | "Guardando..." only — `confirm_duplicate: true` cannot be re-litigated |
| `revalidating` | `CONFLICT` (409) | `duplicate` | alert repopulated from `details` |
| `saving` | `CONFLICT` (409, defensive) | `duplicate` | the server does not 409 a `confirm_duplicate: true` save today; the UI handles it deterministically anyway |
| `revalidating` \| `saving` | `SAVE_OK` (201) | `idle` | text cleared, `saved.success` announced; **list refresh runs in the background** |
| `duplicate` | `CANCEL` | `idle` | nothing saved, text kept |
| *any* | `EDIT_TEXT` | `idle` | stale results are structurally unreachable |
| *in-flight* | `FAIL` (request failed) | `error` | code → Spanish copy |
| `error` | `VALIDATE`/`SAVE`/`EDIT_TEXT` | `idle`/retry | text preserved |

A 409 can therefore only arrive from `revalidating` (blind or `ok` path) or, defensively, from
`saving` (the in-flight confirm POST). There is **no state after the 201**: the list refresh is
tracked by the list component's own `listStatus`, so a refresh failure shows the non-blocking
`list.loadError` + Reintentar and never moves the machine to `error` (the phrase *is* saved).

**The staged-progress honesty rule (ADR-005).** The labels come from the phrase-ui copy table and
are three **separate** stages — `progress.validating`, `progress.revalidating`, `progress.saving` —
never one collapsed spinner and never a merged "Revalidando y guardando...". **Each label spans a
request that is genuinely in flight and none narrates work already done:**

```
POST /phrases/validate   →  "Validando..."      (validating)
POST /phrases            →  "Revalidando..."    (revalidating: in flight; the server embeds, locks,
                                                 re-validates and inserts atomically)
201                      →  idle                (text cleared, "Frase guardada." announced;
                                                 list refreshed in the background — no label)
POST /phrases confirm    →  "Guardando..."      (saving: the confirming call from the duplicate alert)
```

Every label boundary is a **real observable event of a real request**, never a timer: `validating`
ends when the validate response resolves and `revalidating`/`saving` end when the save response
resolves. A 409 resolves at the same boundary and routes straight to `duplicate`. From `ok` the flow
is the same minus the validate call; from `duplicate` + *Confirmar* only "Guardando..." is shown,
because with `confirm_duplicate: true` the re-validation cannot change the outcome and narrating a
decision that has already been made would be theatre. Cost of the blind path: one extra
**round-trip**, whose second leg runs a fresh exact `find_nearest_exact` and the locked insert; thanks to D10 the
embedding is computed **once**.

Infinite scroll holds a separate `pageStatus: idle | loading | done` so a fast scroll cannot fire
two page requests for the same cursor. On `400 INVALID_CURSOR` the list is discarded and validation
is re-run for the current text — the same cursor is never retried.

**Spanish copy ownership.** The API never returns display text. `i18n/copy.es.ts` is the single
copy module and holds the phrase-ui copy table verbatim (`title`, `input.*`, `button.*`,
`progress.*`, `validation.ok`, `duplicate.*`, `badge.*`, `list.*`, `saved.success`, `error.*`); a
vitest test compares its exported values against the table so a typo is a failing test, and a lint
rule bans user-visible string literals outside it. Error rendering goes through
`errorCopy: Record<ErrorCode, CopyKey>`, **exhaustive over the generated `ErrorCode` union** by TS
plus a runtime test that walks the union — a new backend code fails the frontend build until
someone maps it:

| `ErrorCode` | Copy key | Note |
| --- | --- | --- |
| `VALIDATION_ERROR` | `error.tooLong` / `error.empty` by `details.fields[0].reason`, else `error.generic` | `max_length` substituted into the message |
| `INVALID_CURSOR` | `error.invalidCursor` | **fallback only** — the UI silently restarts validation, so this string should never reach the screen; it exists so the map stays exhaustive and so a cursor failure outside the scroll path is still legible (matches the phrase-ui copy table) |
| `DUPLICATE_CONFIRMATION_REQUIRED` | *(none)* | not an error path: it renders the duplicate alert from `details` |
| `NOT_FOUND` / `METHOD_NOT_ALLOWED` / `PAYLOAD_TOO_LARGE` / `INTERNAL_ERROR` | `error.generic` | client/server bugs, nothing actionable for the user |
| `EMBEDDING_UNAVAILABLE` / `NOT_READY` | `error.embeddingUnavailable` | |
| `EMBEDDING_TIMEOUT` | `error.timeout` | |
| *(no response — fetch rejected)* | `error.network` | not a code; handled by the client wrapper |

Neutral/professional Spanish, no regional variants. `error.generic` is also the runtime fallback for
a code the map has somehow not seen, so a raw code is never rendered to a user.

**Display helpers.** The score percentage is a **floored** whole percent computed on integer basis
points — `Math.floor(Math.round(score * 10000) / 100)` — so 0.9312 → 93, 0.9950 and 0.9999 → 99, and
"100%" appears only for an exact 1.0 (rounding would show "100%" for 0.9950-0.9999). The length
counter counts **code points** of the trimmed text (`[...text.trim()].length`, so an emoji counts
once) against `NEXT_PUBLIC_PHRASE_MAX_LENGTH` (build arg, default 280, equal to the backend
`PHRASE_MAX_LENGTH`); it approximates the server rule, which stays authoritative.

## Testing Strategy

Strict TDD is the working discipline: each unit is written RED → GREEN → REFACTOR **locally**, but
RED and GREEN are **squashed per unit**, so every commit is green and the history stays bisectable.
"Failing test first" is a local working convention, not a shape the commit history has to show.

Markers in `pyproject.toml`: `unit` (no I/O, no DB, no model — the fast loop, must stay under ~2s),
`integration` (real Postgres + pgvector), `contract` (OpenAPI), `slow` (real model).

| Layer | What to test | Approach |
| --- | --- | --- |
| Unit | display form (whitespace controls → space **before** stripping remaining `Cc`, strip only U+200B/U+2060/U+FEFF, **ZWJ/ZWNJ kept inside**, NFC after stripping, trim incl. leading/trailing ZWJ/ZWNJ) **and** comparison form (casefold, **NFC again**, whitespace collapse); idempotence of both; `"Buy\tmilk"` → `"Buy milk"`; emoji ZWJ sequence and Persian ZWNJ preserved; length rule on the display form in code points; raw 4× cap | pure functions, no fixtures |
| Unit | `SimilarityPolicy` boundary at `t`, `t ± u`, cosine, `score` (clamp then round) | pure functions |
| Unit (**rounding boundary**) | raw `0.79996` → score `0.8000`, `is_duplicate` **true**, row **in** `matches`; raw `0.79994` → `0.7999`, false, **excluded** although the widened SQL bound admitted it; raw exactly `1 - max_distance` is admitted by SQL and decided by the app | table-driven over `(raw, expected_score, expected_verdict, expected_in_matches)` |
| Unit (**clamp and threshold arithmetic**) | raw cosine `-0.3` → score `0.0` (never negative), `is_duplicate` false at `t = 0.80`; raw `1.0000000002` → `1.0`; `t = 0` admits a `-0.3` row (`max_distance() == 2.0`) and it appears in `matches` with score `0.0`; `t = 0.80005` with raw `0.79996` → not a duplicate, raw `0.80006` → duplicate (Decimal comparison); a saved row with a negative raw cosine satisfies the `BETWEEN 0 AND 1` CHECK | table-driven, pure + in-memory |
| Unit (**ordering and drift**) | ties: bit-identical vectors (equal raw distance) ordered by `id`; displayed-tie fixture (raw 0.90001 vs 0.90004) ordered by raw distance, not `id`; **perturbed-vector paging** (each page's query vector perturbed by 1 float32 ulp per component) repeats and skips nothing on a fixture away from grid edges; 500-match corpus paged to the end (none missing/duplicated) | in-memory repository, `FakeEmbedder` |
| Unit (**save never uses HNSW**) | spy repository whose `find_nearest` returns a deliberately wrong neighbour (or raises): `SavePhrase` calls `find_nearest_exact` exactly once and `find_nearest` **zero** times, on 201 and on 409, and the verdict/recorded metadata come from the exact read; a fixture where `find_nearest` "misses" the stored duplicate and `find_nearest_exact` returns it → 409 (not 201 `unique`) | spy repository, both adapters |
| Unit (**reconciliation**) | spy repository whose `find_nearest` returns a worse neighbour than `matches[0]` → response `most_similar`/`score` come from `matches[0]`; empty `matches` → from `find_nearest` | spy repository |
| Unit (**UnitOfWork and retry**) | `ValidatePhrase` opens `REPEATABLE_READ` read-only; `SavePhrase` opens `READ_COMMITTED`; a repository raising `DuplicateTextConflict` once → a **fresh** unit of work, then 409 with the full payload; always raising → still 409; rollback on exception; no adapter imported by the use cases | in-memory `UnitOfWork` fake |
| Unit (**cursor rules**) | table-driven, one case per rule: bad base64url, non-object JSON, `NaN`/`Infinity` literal, wrong `v`, non-string `t`, `d` negative / >2 / NaN / string, `i` 0 / negative / >int64 / `true`, `th` <0 / >1 / non-finite, missing or extra key, oversized encoding → each `400 INVALID_CURSOR` with `FakeEmbedder.call_count == 0` | pure decoder |
| Unit (**embedding timeout**) | controllable slow fake blocked on a `threading.Event`: tiny timeout → `EmbeddingTimeout`; slot still held → next call fails fast; event released → slot freed, later call succeeds; inner call count shows nothing extra queued; timed-out result never cached | `BoundedEmbeddingProvider` + slow fake, no sleeps |
| Unit | `ValidatePhrase` / `SavePhrase`: empty store, best-below-threshold → `score`/`most_similar` non-null with `is_duplicate` false and `matches` `[]`, duplicate unconfirmed → 409 with the **full** payload, confirmed → persisted metadata, embedder failure/timeout never persists | `FakeEmbedder` + `InMemoryPhraseRepository` |
| Unit | **`most_similar == matches[0]`** whenever `matches` is non-empty, over a randomized corpus | property-style loop, both repository adapters |
| Unit | **below-threshold neighbour is recorded**: saving a phrase whose best score is 0.55 stores `status=unique`, `similarity_score=0.55`, `most_similar_phrase_id=P.id`; an empty store stores `(NULL, NULL)` | spy repository asserting the `NewPhrase` it received |
| Unit (shared) | repository contract suite parametrized over in-memory **and** pgvector adapters — incl. `find_nearest` and `find_nearest_exact`: empty → `None`, below-threshold neighbour returned, distance tie → lowest `id`, never affected by `max_distance` | one suite, two adapters — prevents fake drift |
| Unit (cache) | **call counting**: same text twice → inner `call_count == 1`; different text → 2; different `model_id`, same text → 2 (no cross-model bleed) | `FakeEmbedder.call_count` + `CachingEmbeddingProvider` |
| Unit (cache) | **cold vs warm equivalence**: vector is bit-identical after clear/re-embed; `ValidatePhrase` response payload is byte-identical with cache empty, warm and **disabled** (`size=0`) | parametrized over the three cache modes |
| Unit (cache) | **eviction**: `size=2`, insert A,B,C → A recomputed on next call, B/C hit; touching A before inserting C keeps A (true LRU, not FIFO); `evictions` counter increments |
| Unit (cache) | **failures are not cached**: a provider that raises once for T then recovers is called **twice** and the second call succeeds; `size` is unchanged after the failure | `FailingEmbedder` in one-shot mode |
| Unit (cache) | thread safety: `ThreadPoolExecutor` × N threads over M texts → no exception, `size <= capacity`, every returned vector correct | stress loop, `unit` marker |
| Unit (app) | **blind save = one embedding**: `ValidatePhrase` then `SavePhrase` on the same text sharing one provider → `call_count == 1`; **matches pages 2..n = zero extra embeddings** → `call_count` stays 1 across 3 pages | `FakeEmbedder` + `InMemoryPhraseRepository` |
| Unit (app) | **cache never skips the query**: repository counters show `find_nearest` + `find_matches` on every validate, `find_nearest_exact` (and no `find_nearest`) on every save — 2 reads on 409 (`find_nearest_exact` + `find_matches`), 1 read plus `INSERT` on 201 — `find_matches` on every match page — even when the embedding hits | spy repository |
| Unit (app) | **no embedding on a rejected cursor**: malformed / wrong-`t` / wrong-`th` cursor → `400 INVALID_CURSOR` with `call_count == 0` | `FakeEmbedder` |
| Integration | keyset paging: tie scores, page boundary, last page `has_more=false`, `+1` probe; **the tail rule** (a page truncated by the rounded filter reports `has_more=false`); advisory-lock serialization with two real connections; migration up/down incl. the new `CHECK` constraints; dimension-mismatch boot failure | compose `db`, `phrases_test` database, transaction-rollback fixture (lock test uses real commits + truncate) |
| Integration (**non-vacuous plan and recall guards, `find_nearest` (validate) only**) | corpus **larger than `ef_search`** (e.g. 1 000 rows vs 200): HNSW top-1 with `SET enable_seqscan = off` for the arm under test equals the exact top-1 with `SET enable_indexscan = off` over a few hundred query vectors; `EXPLAIN` of `find_nearest` (seq scan off) shows an Index Scan on `phrases_embedding_hnsw_idx` and no full-table `Sort`; pgvector-vs-domain-cosine **oracle equivalence** (**1e-5**, float32 storage rationale) | seeded fixture corpus |
| Integration (**save path is exact, not HNSW**) | (a) `EXPLAIN` of `find_nearest_exact` shows **no** HNSW index scan (even with `enable_seqscan = off` set on the connection first, because the method sets its own `enable_indexscan = off`); (b) a spy/statement log on the pgvector adapter shows a full `SavePhrase` (201 and 409) issues no `find_nearest` statement; (c) **recall-miss fixture**: corpus larger than `hnsw.ef_search` (tiny value, index scan forced for the HNSW arm) where the HNSW top-1 provably misses a stored near-identical phrase, while `find_nearest_exact` returns it; saving that text unconfirmed answers **409** and records nothing (a control asserting the HNSW arm alone would have returned the wrong neighbour keeps the test non-vacuous) | compose `db`, `phrases_test`, seeded corpus |
| Integration (**exact `find_matches`**) | `EXPLAIN` of `find_matches` shows **no** HNSW index scan and no `OFFSET`; **500 matches** (more than the former `ef_search` of 200) paged to the end with page size 50: 10 pages, 500 distinct ids, none missing, none repeated; `enable_indexscan` is `SET LOCAL` (a following statement on the same pooled connection sees the default); `EXPLAIN (ANALYZE)` timings on 500 and 10⁴ rows recorded as evidence | compose `db`, `phrases_test` |
| Integration (**ADR-006 DB guarantee**) | bypassing the application check with raw SQL/repository insert: a second `unique` row with the same `normalized_text` is **rejected** (`23505` on `phrases_unique_normalized_text_uidx`); a `duplicate_confirmed` row with the same `normalized_text` is **accepted**; a `unique` row with a different `normalized_text` is accepted; migration up/down creates and drops the index | compose `db`, `phrases_test`, raw `INSERT`s, no use case involved (slice 4) |
| Integration + Unit (**violation mapping**) | pgvector adapter turns only that constraint's `23505` into `DuplicateTextConflict`; `SavePhrase` retries once and returns 409 `DUPLICATE_CONFIRMATION_REQUIRED` with the full payload (not 500); repeated conflict still yields 409; a conflict on `confirm_duplicate=true` cannot occur | adapter test with a seeded row + lock-bypassing insert; use-case unit test with a repository that raises once, then always |
| Integration | **snapshot consistency (deterministic)**: two `threading.Event` barriers and the adapter's `after_statement` hook — pause after `find_nearest`, a second connection inserts a higher-scoring phrase and commits, resume — neither statement sees the new row and `most_similar == matches[0]`; a **control run at `READ COMMITTED` shows the divergence**, proving the test can fail | two real connections, barrier/hook (no sleeps or timing) |
| Integration | **cursor stability**: paging survives a cache forced to `size=1` (eviction between every page) and a perturbed query vector without gaps or repeats; bit-identical warm-vs-cold vectors are asserted only as a single-process determinism smoke test, not as a correctness dependency | compose `db`, cache forced to `size=1` |
| Contract | every error code present in OpenAPI; pagination fields documented; `limit` optional and bounded on **both** endpoints; ids typed `string` and documented opaque; `docs/openapi.json` snapshot diff | `app.openapi()` snapshot test |
| Contract | framework errors wear the envelope: `GET /nope` → 404 `NOT_FOUND`, `DELETE /phrases` → 405 `METHOD_NOT_ALLOWED`, forced exception → 500 `INTERNAL_ERROR` with no stack trace, malformed JSON → 422 `VALIDATION_ERROR` | `TestClient` end-to-end |
| Contract | `/health` 200 body has `status`/`database`/`model`(= `"ready"`)/`dimensions`/`embedding_model`(= the model name)/`embedding_cache`; 503 is `NOT_READY` with per-component `details` using the same keys (`details.model == "unavailable"` when the model is not loaded); the handler issues **zero** embeddings | patched readiness flag + patched DB ping, `FakeEmbedder.call_count == 0` |
| Contract | strict typing: `confirm_duplicate` of `"yes"`, `1`, `"true"` → 422 `invalid_type`; `limit` of `"10"`, `true`, `10.5` → 422 `invalid_type`; raw text > 4 × `PHRASE_MAX_LENGTH` → 422 `too_long` without normalization; body > `MAX_REQUEST_BYTES` → 413 `PAYLOAD_TOO_LARGE`; DB down on `POST /phrases` → 500 `INTERNAL_ERROR`; `GET /phrases` capped at `PHRASES_LIST_LIMIT` | `TestClient` |
| Contract | CORS: preflight from an allowed origin returns allow-origin, methods incl. `POST`, header `Content-Type`, **no** `Allow-Credentials`; disallowed origin → no allow-origin; a **forced 500 for an allowed origin still carries `Access-Control-Allow-Origin`** (catch-all lives inside `CORSMiddleware`) | `TestClient` |
| Contract | the 409 `details` is validate-shaped (`threshold`, `score`, `most_similar`, `matches`, `next_cursor`, `has_more`) and its `next_cursor` is accepted by `POST /phrases/matches` for the same text | 120-match fixture, conflict then continuation |
| Slow | real model loads, produces 384 dims, is deterministic (embed twice → identical); ES/EN calibration table | `-m slow`, a **manual evidence step** (`make evidence`), not part of CI |
| Frontend unit | `machine.ts` reducer: table-driven over every (state × event) pair, including `EDIT_TEXT` from every state and every invalid transition being ignored | vitest, no DOM |
| Frontend component | **progress label order**: blind save renders "Validando..." → "Revalidando..." and then, on 201, **no label** (text cleared, "Frase guardada." announced); save from `ok` renders only "Revalidando..."; confirm from `duplicate` renders **only** "Guardando..."; a 409 during `revalidating` never renders "Guardando..."; a post-201 list-refresh failure leaves the machine `idle`, keeps "Frase guardada." and shows `list.loadError` + Reintentar (never `error`); the live region is `role="status" aria-live="polite"` | vitest + @testing-library, deferred-promise fake client so each stage is asserted while in flight |
| Frontend unit | percentage helper: 0.9312 → 93, 0.9950 → 99, 0.9999 → 99, 0.29 → 29, 1.0 → 100; counter counts code points (280 emoji → 280) and reads `NEXT_PUBLIC_PHRASE_MAX_LENGTH` | vitest |
| Frontend component | form disables in flight, duplicate alert renders matches + "93%", infinite scroll appends/dedupes/stops, `400 INVALID_CURSOR` discards matches and re-runs validation, error codes render Spanish | hand-rolled typed fake client (MSW rejected: extra dep for no gain at this size) |
| Frontend unit | `errorCopy` is **exhaustive** over the generated `ErrorCode` union (incl. `INVALID_CURSOR`); `copy.es.ts` values equal the phrase-ui copy table verbatim | union walk + table snapshot |
| Frontend contract | generated `types/api.ts` regenerated in CI; build fails on diff | `openapi-typescript` drift guard |

### ES/EN calibration fixture

`services/api/tests/fixtures/calibration.yaml`, labeled pairs in three categories:

| Category | Examples | Gate |
| --- | --- | --- |
| `duplicate` (score >= the configured default threshold) | "Comprar leche" / "Ir a comprar leche"; "Comprar leche" / "comprar LECHE"; cross-lingual "Comprar leche" / "Buy milk"; accent variants | hard assert |
| `distinct` (score < the configured default threshold) | "Comprar leche" / "Comprar pan"; "Llamar al dentista" / "Comprar leche" | hard assert |
| `expected_weakness` | negation pairs ("Me gusta el café" / "No me gusta el café") | **reported, not gated** — sentence embeddings are known to score negation pairs high; we document the weakness instead of pretending it away |

The `slow` test is a **manual evidence step** (`make evidence`), not part of CI. It prints a score
table that is written to `docs/evidence/calibration.md`. **That table is the brief's "evidence of
Hugging Face integration" deliverable.** The threshold `0.80` and the max length `280` are **working
defaults**: the default is **finalized after the first measured slow run**. If the observed
separating margin is not near 0.80, change the `SIMILARITY_THRESHOLD` **default**, record the
measured margin in the ADR and update the spec — a changed default is a recorded **spec-change
trigger**, never a silent code change and never a fixture bent to fit the threshold.

## Docker Compose

| Service | Image / build | Depends on | Healthcheck |
| --- | --- | --- | --- |
| `db` | `pgvector/pgvector:pg16` *(tag unverified — see below)* | — | `pg_isready -U $POSTGRES_USER -d $POSTGRES_DB` |
| `migrate` | build `services/api` (**same image as api**; slice 4 ships a minimal `migrate`-capable Dockerfile stage without torch or model, slice 8 extends it), `alembic upgrade head`, `restart: "no"` | `db: service_healthy` | n/a (one-shot) |
| `api` | build `services/api`, ports `8000` | `migrate: service_completed_successfully` | `GET /health` (DB + model ready); `start_period: 120s`, `interval: 10s`, `timeout: 5s`, `retries: 12` so a cold torch + model load is not reported as a failure (120 s is an **estimate**, tuned after the slice 8/14 time-to-healthy measurement) |
| `web` | build `apps/web`, build-arg `NEXT_PUBLIC_API_URL`, ports `3000` | `api: service_healthy` | `GET /` |

Root `.env` (from `.env.example`) via `env_file`; named volume `pgdata`; `docker compose down -v`
restores a clean state. The API Dockerfile is multi-stage: builder installs the **CPU-only torch
wheel** from the PyTorch CPU index and downloads the model into `/opt/models` at the pinned `EMBEDDING_MODEL_REVISION` commit SHA; runtime copies
site-packages + weights and sets `HF_HUB_OFFLINE=1`.

## File Changes

Greenfield: everything is **Create**. Grouped by slice below rather than listed file by file.

## Delivery Plan (400-line review budget)

`delivery_strategy: ask-on-risk`. Feature Branch Chain: PR #1 targets the tracker branch, each later
PR targets the previous one. Every slice is independently revertible and ships its own tests.

| # | Slice (conventional commit) | Est. lines |
| --- | --- | --- |
| 0 | `chore: scaffold monorepo` — root files, `.gitignore`, `.env.example`, pyproject/package.json, import-linter + CI lint stub | ~150 |
| 1 | `feat(domain): normalization forms, clamped score and similarity policy` — display vs comparison form (whitespace-control mapping, ZWJ/ZWNJ kept, NFC twice), clamp + `score`, `Decimal` comparison, widened `max_distance`, boundary tables | ~340 |
| 2 | `feat(domain): ports, unit of work, fake embedder and in-memory repository` + shared contract suite incl. `find_nearest` and `find_nearest_exact`, `(bucket, id)` keyset, bit-identical tie fixture | ~340 |
| 2b | `perf(similarity): caching embedding provider decorator` — LRU, eviction, stats, failures-not-cached, thread-safety tests (D10 / ADR-011) | ~180 |
| 2c | `feat(domain): opaque cursor codec with strict validation` — field rules, size cap, table-driven tests | ~150 |
| 3 | `feat(app): validate, list-matches and save use cases` — the TDD core: `UnitOfWork` isolation levels, `find_nearest` + `find_matches` pair (validate) with the reconciliation rule, save via `find_nearest_exact` only (spy test: zero `find_nearest`), tail rule, below-threshold neighbour recorded, 409 payload build, `DuplicateTextConflict` fresh-transaction retry then 409 (ADR-006), call-count and cold-vs-warm assertions | ~350 |
| 4 | `feat(db): phrases schema, alembic raw-sql migrations, compose db/migrate and a minimal API Dockerfile stage` — paired-metadata `CHECK`s, `ON DELETE RESTRICT`, the ADR-006 partial unique index with its DB-level guarantee test; the `migrate` service is runnable from this slice | ~340 |
| 5a | `feat(db): exact keyset find_matches` — `(bucket, id)` keyset, widened bound, `enable_indexscan` off, perturbed-vector and 500-match paging tests, `EXPLAIN` guard | ~330 |
| 5b | `feat(db): pgvector find_nearest, find_nearest_exact, unit of work and advisory lock` — HNSW top-1 (validate), exact top-1 (save) with save-path EXPLAIN/spy and recall-miss tests, isolation levels, `lock_timeout`, `set_config` scoping, non-vacuous recall / plan / oracle guards, barrier-based snapshot test | ~350 |
| 6 | `feat(api): settings, error envelope and framework-error handlers` — 404/405/413/422/500, catch-all inside CORS, body-size guard, raw-length cap, id string serialization, shared strict `PageLimit` | ~300 |
| 6b | `feat(api): validate endpoint and /health readiness` — verdict payload, `NOT_READY` + per-component details, cache stats | ~250 |
| 7 | `feat(api): save, list and match paging endpoints` — full 409 `details`, `400 INVALID_CURSOR`, `StrictBool`, list cap, contract tests | ~380 |
| 8 | `feat(embeddings): sentence-transformers adapter, bounded provider, cache wiring and image bake` — pinned Hub SHA, timeout/concurrency bound, measured image size | ~380 |
| 9 | `test(calibration): es/en fixture and integration evidence` (manual `make evidence`) | ~150 |
| 10 | `feat(web): scaffold, api client and generated types` | ~300 |
| 11 | `feat(web): validation state machine and phrase form` — staged progress narration (no post-201 stage) | ~360 |
| 12 | `feat(web): duplicate alert with infinite-scroll matches` + `INVALID_CURSOR` restart | ~310 |
| 13 | `feat(web): saved list, status badges and the spanish copy module` — full copy table, exhaustive `errorCopy`, floored percent, `force-dynamic` first paint | ~290 |
| 14 | `feat(infra): full compose wiring and healthchecks` — `web`, `api` healthcheck with `start_period`/`retries`, build args | ~200 |
| 15 | `docs: readme and architecture` — install, run and env vars per the brief | ~300 |
| 16 | `docs: decision log` — the five `beyond-brief` ADRs in `docs/decisions/` and the technical ADRs in `docs/decisions/technical/` | ~340 |

Total ≈ 6 090 lines across **21 slices** (sum of the table above), none above the 400 budget (the
largest is ~380). Slices 1–3 need no infrastructure at all — the product's core logic is fully tested
before a database exists. Slices 4 and 5a stay separate because the migration is the rollback
boundary. Slice 4 is runnable on its own because it ships the minimal Dockerfile stage the `migrate`
service needs; slice 8 only extends that Dockerfile with torch and the model bake.

**Commit convention.** RED and GREEN are squashed per unit (see Testing Strategy), so each slice is
a sequence of green, bisectable commits.

**Why 5 and 6 split.** The exact-scan keyset work and the top-1 (HNSW and exact)/transaction primitives would
together cross the 400-line budget, as would the framework-error handlers plus the expanded `/health`
payload on the API side, so each became two slices with a clean seam — 5a is pure query work against
an existing schema, 5b adds the top-1 reads and the write-path primitives (incl. translating the
ADR-006 unique violation into `DuplicateTextConflict`; the retry-then-409 behaviour lives in slice 3
with the use case and is exposed end to end in slice 7); 6 is transport plumbing with no business
endpoint, 6b is the first endpoint that uses it. Each half is independently revertible and ships its
own tests.

**Why 2b is its own slice** rather than folded into 2 or 8: the cache is a beyond-brief optimization,
so it must be **independently revertible** — dropping that one PR (or setting
`EMBEDDING_CACHE_SIZE=0`) returns the system to the recompute-everything behaviour with every test
still green. Folding it into slice 8 would also tie a provider-agnostic decorator to the
sentence-transformers adapter and delay the call-count assertions that slice 3 depends on. **2c** is
split out because the strict cursor rules and their table-driven tests would push slice 3 past 400.

## "Beyond the Brief" Decision Log

Written as `docs/decisions/`, front-matter `type: beyond-brief | technical`. **Layout:** the top
level of `docs/decisions/` holds **exactly five** `beyond-brief` entries (ADR-001..005, the five
topics phrase-management enumerates); every `technical` ADR (ADR-006..015) lives in
`docs/decisions/technical/` so it can never be miscounted as a sixth beyond-brief entry. The README
summarizes the `beyond-brief` entries (that is the deliverable) and links the technical ones.

ADR-011 (the embedding cache) was previously typed `beyond-brief`, which would have made six and
broken the spec's "exactly five" requirement; it is `technical` and lives in `technical/`. That is
the honest classification anyway: the cache does not change what the product does, it changes how
often a pure function runs. Its "brief asked / we decided / because" framing is kept verbatim in the
entry, it is still linked from the README, and it is still the most droppable slice.

| ID | Entry |
| --- | --- |
| ADR-001 | **The brief asked for** the most similar phrase and its score. **We decided** to also return `matches` — every phrase at or above the threshold, score-ordered, cursor-paginated, with infinite scroll. **Because** a single match hides how *crowded* the neighbourhood is; a user deciding whether to confirm a duplicate deserves the full picture, and a fixed top-N would be a silent truncation disguised as an answer. `most_similar` is still returned verbatim. |
| ADR-002 | **The brief asked for** a clean layered app (UI, business, data, AI). **We decided** a monorepo of independently deployable services with modular hexagonal modules and enforced import boundaries. **Because** "layered" as a folder convention decays on contact with deadlines; import-linter contracts make the boundary a build failure. The embedding module can become a microservice by swapping one adapter — with the honest caveat that vector *search* stays with the data. |
| ADR-003 | **The brief asked for** a Hugging Face model, with evidence of the integration. **We decided** to run the Hub checkpoint (`paraphrase-multilingual-MiniLM-L12-v2`, pinned by commit SHA) locally through `sentence-transformers`, rather than through the hosted Inference API, with ONNX/fastembed documented as the migration path behind `EmbeddingProvider`. **Because** a reviewer must be able to run this offline with no token, and the threshold is calibrated against sentence-transformers' scores. This is **not** a departure from "a Hugging Face model" — the checkpoint is one; the choice is about the runtime. Migration triggers and the mandatory score-equivalence gate are written down so the choice stays revisable, not permanent. |
| ADR-004 | **The brief asked for** React or Vue. **We decided** Next.js with TypeScript. **Because** the saved-phrase list gets a real server-rendered first paint (no spinner) via a Server Component (`force-dynamic` / `no-store`, so it is never a stale build-time snapshot), while validation stays a client-side state machine — we use Next for something, not as decoration. Cost: `NEXT_PUBLIC_API_URL` and `NEXT_PUBLIC_PHRASE_MAX_LENGTH` are baked at build time. |
| ADR-005 | **The brief asked for** a validation button before saving. **We decided** a staged UX with three distinct labels — "Validando..." (the validate request), "Revalidando..." (the authoritative save request, while the server re-validates) and "Guardando..." (the confirming save from the duplicate alert) — instead of one opaque spinner or a merged "Revalidando y guardando...". Pressing Guardar without validating shows "Validando..." then "Revalidando..."; from a validated state only "Revalidando...". **Because** the server always re-validates, and the interface should tell the truth about that work. Every label spans a request that is really in flight; nothing is faked on a timer, and **no label is shown after the 201** — the machine returns to `idle`, clears the text, announces "Frase guardada." and refreshes the list in the background (a failed refresh is a non-blocking list error, never a save error). A 409 routes to the duplicate alert from `revalidating` (or, defensively, `saving`) without "Guardando..." ever narrating a save that did not happen. |
| ADR-006 | *(technical)* **ADOPTED**: partial unique index on `normalized_text` `WHERE validation_status = 'unique'`, on top of the advisory lock. Supersedes the earlier "no unique index" decision without contradicting its rationale (confirmed duplicates are outside the index and stay allowed; an unconfirmed identical text is never inserted as `unique` because the server returns 409). Integrity, not performance: it makes "no unconfirmed identical phrase is stored twice" a database guarantee. A unique violation maps to a single bounded retry, in a fresh transaction, that lands on the normal 409 `DUPLICATE_CONFIRMATION_REQUIRED` path, never a 500. Semantic (non-identical) near-duplicates are not covered; that residual race is documented. |
| ADR-007 | *(technical)* Re-embed per page for stateless match pagination; **keyset (never `OFFSET`) for stable page semantics, not for speed** — `find_matches` is an exact O(n) scan; keyset positions are `(floor(distance / 1e-6), id)` so a recomputed query vector that drifts by an ulp neither repeats nor skips rows (D16); opaque cursor with strict field validation and a size cap; `400 INVALID_CURSOR` on any violation, or a cursor issued for a different comparison form or threshold, decided **before** any embedding. Efficiency of the re-embed is ADR-011's subject, not a weakening of this one. |
| ADR-008 | *(technical)* HNSW **only for the unfiltered top-1 `find_nearest` of the validate endpoint**; the threshold-filtered, paginated `find_matches` is an **exact scan** (`enable_indexscan` off per transaction) because HNSW applies `WHERE` after a bounded candidate window and would silently truncate the match list. **The write path is exact too:** `SavePhrase` derives its verdict and recorded metadata from `find_nearest_exact` (an exact single-row scan with the same planner settings as `find_matches`, inside the save transaction under the advisory lock), never from HNSW, because an approximate recall miss on save could store a duplicate as `unique`; the cost is one O(n) scan per save, accepted at this scale (correctness of the write path over a small cost, consistent with using exact scans wherever completeness matters), and the scaling path is deferred. Non-vacuous recall/`EXPLAIN` guards (corpus larger than `ef_search`, forced plan), plus save-path `EXPLAIN`/spy and recall-miss tests. Scaling path — pgvector >= 0.8 `hnsw.iterative_scan = strict_order` with a raised `hnsw.max_scan_tuples` — is documented, **unverified** and deferred. A measured image-size baseline is recorded here. |
| ADR-009 | *(technical)* Browser→API direct calls, Server-Component first paint (`force-dynamic`, browser-side refetch after a save), no BFF proxy; CORS (methods `GET, POST, OPTIONS`, `Content-Type`, no credentials) as the accepted cost. |
| ADR-010 | *(technical)* Compose DB for integration tests instead of testcontainers. |
| ADR-011 | *(technical — see the note above; retains its beyond-brief framing)* **The brief did not ask for** any caching or performance work — it asked for a validation flow. **We decided** to add a bounded, per-process LRU **inside an `EmbeddingProvider` decorator** (`CachingEmbeddingProvider`, key `(model_id, comparison_form)`, 512 entries ≈ 1 MB (estimate), LRU eviction, lock on the dict but never around the forward pass), and to cache **nothing else**. **Because** the flow visibly recomputed the same pure function twice — once per matches page 2..n, and once more on the second leg of a blind Save — while every *other* candidate for caching (the verdict, the match page, a client-supplied score) goes stale the moment a phrase is inserted and would turn a correctness property into a race. Caching a pure deterministic function is the only optimization here that is **observably free**: cold and warm produce byte-identical responses, `EMBEDDING_CACHE_SIZE=0` reverts it, and the similarity query still runs on every single request. **Limits we accept and document**: the cache is per process, so N workers means N caches and a hit rate ≈ 1/N — correctness is unaffected (the keyset tolerates a recomputed vector), only latency. A shared cache is a possible future step if more than one replica is ever run; it is not designed here. |
| ADR-012 | *(technical)* **Two questions, distinct reads.** `find_nearest` (unfiltered top-1, HNSW, validate only) answers *what is the closest phrase* and `find_matches` (threshold-filtered keyset, exact scan) answers *which phrases are duplicates*; validate runs both in one `REPEATABLE READ` snapshot and takes `score`/`most_similar` from `matches[0]` whenever matches exist (reconciliation rule). Save asks the first question through `find_nearest_exact` (the exact twin, no HNSW) and runs `find_matches` only when it must build a 409 body. This is what makes a below-threshold `most_similar` reportable — and recordable on the saved row — instead of silently null. Rejected: one `find_matches(max_distance=1.0, limit=1)` doing double duty. |
| ADR-013 | *(technical)* **Rounding is the contract.** Scores are clamped to [0, 1] (a cosine can be negative) and then rounded to 4 decimals; that value decides the threshold (compared as `Decimal`, so thresholds with more than 4 decimals are exact), populates every response and is what gets stored. SQL filters on a bound widened by a full rounding unit (`2.0` at `t = 0`) so it is a provable **superset**, and the application applies the exact comparison, stopping at the first failing row (the tail rule). Keyset ordering stays on raw distances, so rounding never enters the cursor. Oracle equivalence against the domain cosine is gated at **1e-5**, not 1e-6, because pgvector stores float32. Rejected: rounding inside SQL, which would duplicate the rounding rule. |
| ADR-014 | *(technical)* **Ids are `BIGINT` inside and opaque strings on the wire**, because JavaScript cannot safely hold the full range and a string id keeps a future UUID/ULID switch out of the contract. |
| ADR-015 | *(technical)* **`UnitOfWork` port and two isolation levels.** The application layer opens transactions through a port (isolation level, commit, rollback), never through an adapter. Validate: `REPEATABLE READ READ ONLY` (plain `READ ONLY` under `READ COMMITTED` would give each statement its own snapshot). Save: `READ COMMITTED`, so the statement after the advisory-lock wait sees the commit the lock waited for. A bounded `lock_timeout` keeps a stuck holder from pinning every save. |

## Verification Status

Web access (`WebSearch`, `WebFetch`) was **disabled in this session**. The infrastructure and
runtime items below could not be confirmed against a source and are therefore recorded as
unverified or unmeasured, each with the exact command that settles it during the slice that depends
on it.

| Item | Status | Verify in | How |
| --- | --- | --- | --- |
| `pgvector/pgvector:pg16` tag exists; Debian-based; no official alpine variant | **UNVERIFIED (from model memory)** | slice 4 | `docker pull pgvector/pgvector:pg16 && docker images pgvector/pgvector` |
| Image size (alpine vs debian tradeoff) | **UNVERIFIED** | slice 4 | record the `docker images` size in ADR-008; if an alpine base is required, build from `postgres:16-alpine` + `make install` in a builder stage |
| pgvector extension version and HNSW availability (HNSW needs >= 0.5.0) | **UNVERIFIED** | slice 4 | `SELECT extversion FROM pg_extension WHERE extname='vector';` — migration 0001 must fail fast if HNSW is unsupported |
| `vector_cosine_ops` / `<=>` operator semantics (distance = 1 - cosine for normalized vectors) | **High confidence, still gated by a test** | slice 5b | oracle-equivalence test against the domain cosine (**1e-5**) |
| The planner serves `ORDER BY embedding <=> :q, id LIMIT 1` from the HNSW index (incremental sort on `id`) rather than a full sort | **UNVERIFIED (from model memory)** | slice 5b | `EXPLAIN (ANALYZE, BUFFERS)` assertion with `enable_seqscan = off` on a corpus larger than `ef_search` (otherwise the test is vacuous); documented fallback is a k-NN subquery re-sorted in an outer query |
| Casefolding before embedding does not materially degrade the ES/EN separating margin on a cased checkpoint | **UNMEASURED** | slice 9 | run the calibration fixture on cased pairs with and without casefolding; record both margins in ADR-003 |
| fastembed supports `paraphrase-multilingual-MiniLM-L12-v2` | **UNVERIFIED** | ADR-003 / future migration | `python -c "from fastembed import TextEmbedding; print([m['model'] for m in TextEmbedding.list_supported_models()])"` — if absent, fall back to a manual `optimum` ONNX export |
| API image size with torch CPU + model | **UNMEASURED** | slice 8 | `docker images todo-ia-api` — the measured value becomes ADR-003's migration-trigger baseline |
| Real p95 embed latency, and the measured blind-Save / page-2 saving from the cache | **UNMEASURED** | slice 8 | time a warm vs cold `POST /phrases/validate` + `POST /phrases` pair with the real model; record in ADR-011 and use it to size `EMBEDDING_CACHE_SIZE` |
| Cased-variant cosine ≈ 0.98 (display forms of "Comprar leche" vs "comprar LECHE") | **ESTIMATE, unmeasured** | slice 9 | score both forms with the real model; record in ADR-003 |
| ~50 ms CPU forward pass | **ESTIMATE, unmeasured** | slice 8 | time `embed()` p50/p95 on the target host |
| Postgres picks a sequential scan on small tables (a few thousand rows), so HNSW is often unused there | **ESTIMATE (model memory)** | slice 5b | `EXPLAIN` on 100 / 1 000 / 10 000 rows |
| ~2 KB per cache entry, ≈ 1 MB at 512 entries | **ESTIMATE, unmeasured** | slice 2b/8 | `tracemalloc` over a filled cache |
| Exact-scan `find_matches` costs milliseconds to tens of milliseconds for ~10⁴ rows | **ESTIMATE, unmeasured** | slice 5a | `EXPLAIN (ANALYZE)` on 500 and 10⁴ rows; record in ADR-008 |
| pgvector >= 0.8 `hnsw.iterative_scan = strict_order` + `hnsw.max_scan_tuples` as the scaling path | **UNVERIFIED, deferred** | future | `SHOW hnsw.iterative_scan;` on the pinned image; not adopted in this change |
| Hub commit SHA of the pinned checkpoint | **UNVERIFIED (no web access)** | slice 8 | read the SHA from the Hub repo commit list or `huggingface_hub.model_info(...).sha` and set `EMBEDDING_MODEL_REVISION` |
| `api` healthcheck `start_period: 120s` covers a cold model load | **ESTIMATE, unmeasured** | slice 14 | measure container-start → healthy and tune `start_period`/`retries` |
| Starlette runs `Exception` handlers in `ServerErrorMiddleware`, outside `CORSMiddleware` (hence the catch-all as inner middleware) | **From memory, gated by a test** | slice 6 | contract test: a forced 500 for an allowed `Origin` carries `Access-Control-Allow-Origin` |
| ONNX/quantization score drift magnitude | **UNVERIFIED by design** | future migration PR | re-run the calibration fixture and diff per-pair scores against the sentence-transformers baseline |

None of these block the design: every one is isolated behind a decision that already has a stated
fallback, and each is verified inside the slice that first depends on it.

## Migration / Rollout

No data migration (greenfield). Rollout is local only: `docker compose up`. Rollback per the
proposal — revert a slice, `alembic downgrade`, or `docker compose down -v`. Runtime tuning without
a code change: raise `SIMILARITY_THRESHOLD` toward 1.0 to make validation effectively permissive.

## Risks

| Risk | Likelihood | Mitigation |
| --- | --- | --- |
| HNSW approximation misses the true nearest neighbour in `find_nearest` (the only HNSW read, validate endpoint only). On validate the exact `matches[0]` wins (reconciliation rule); the **save** verdict and recorded metadata come from the exact `find_nearest_exact`, so a recall miss can no longer let a duplicate through as `unique` (former accepted residual **eliminated**) | Low | validate-only impact is advisory (best-below-threshold `most_similar` may be slightly off); non-vacuous recall guard; `HNSW_EF_SEARCH` tunable; save-path spy/`EXPLAIN` and recall-miss tests |
| Exact `find_matches` (per page) and `find_nearest_exact` (per save) are O(n) and slow as the store grows | Med | accepted at target scale for write-path correctness; timings recorded in slice 5a (extended to `find_nearest_exact` in 5b); scaling path (pgvector >= 0.8 iterative scan) documented, unverified, deferred |
| Threshold miscalibration ES/EN | Med | calibration fixture gates `duplicate`/`distinct`; negation weakness documented rather than hidden |
| Re-embed per page adds latency on deep scrolls | Low | D10 cache makes pages 2..n cost **0** forward passes; each page is one O(n) exact scan (not independent of `n`); page size 50 amortizes the cold pass over 50 rows |
| A recomputed query vector differs by an ulp (cache eviction, another worker) and exact float equality on `d` repeats or skips rows | Low | keyset compares on the `(floor(d / 1e-6), id)` grid (D16), so drift below the grid is absorbed; perturbed-vector test; **residual**: two non-identical rows within 1e-6 of each other and of the cursor, straddling a grid edge under drift (true ties move together and are safe) |
| Blind-save double embedding (two calls) | Low | **eliminated** by D10 when warm (one forward pass, two real calls); worst case equals the pre-cache cost |
| A future change caches a verdict or a match page and serves stale duplicates | **Med** | stated as a forbidden invariant in the D10 section; spy-repository test asserts the live query (`find_matches` / `find_nearest_exact`) runs on every request even on a cache hit |
| Cache serves a vector from the previous model after an `EMBEDDING_MODEL` swap | Low | `model_id` is part of the key; boot-time dimension/typmod coherence check; cross-model isolation test |
| Multi-worker deployment degrades hit rate to ≈ 1/N | Low | per-process by design, correctness unaffected; documented in ADR-011 (a shared cache is only a possible future step) |
| Cache memory grows unnoticed | Low | hard LRU bound (512 ≈ 1 MB), `evictions`/`size` on `GET /health`, `INFO` log on first eviction, `EMBEDDING_CACHE_SIZE=0` kill switch |
| Identical text lands twice as `unique` via a lock-bypassing path | **Eliminated at the DB** | ADR-006: partial unique index `phrases_unique_normalized_text_uidx`; violation maps to one retry then 409, never 500 |
| Semantic near-duplicate (non-identical text) lands twice via a lock-bypassing path or a stale validate | Low | **Not covered by the index**; advisory lock + application logic only; documented residual race (Concurrency) |
| The unique-violation retry loops or leaks a 500 | Low | bounded to one retry, second failure still returns 409 from a fresh snapshot; unit test with a repository that always raises `DuplicateTextConflict` |
| The partial index is mistaken for a performance feature (or dropped as unused) | Low | documented as integrity-only; performance is HNSW (top-1 only) + the embedding cache, and keyset paging gives stable page semantics rather than speed |
| torch image size / cold start | Med | CPU wheel, build-time bake, lifespan warmup, ADR-003 migration triggers |
| pgvector image tag or HNSW support differs from assumption | Med | verification table above; migration 0001 fails fast |
| **`find_nearest` and `find_matches` disagree** (`most_similar != matches[0]`) on validate because a writer commits between the two statements | Med | both run in one `BEGIN ISOLATION LEVEL REPEATABLE READ READ ONLY` snapshot (`READ ONLY` alone is not enough), and `matches[0]` wins by the reconciliation rule; invariant asserted on both adapters and, deterministically via barriers, under a concurrent writer (with a `READ COMMITTED` control run) |
| **`find_nearest`'s two-key `ORDER BY` defeats the HNSW plan**, degrading to a seq scan + full sort | Med | `EXPLAIN` assertion in the recall guard; documented k-NN-subquery fallback that keeps the index; at demo scale a seq scan is still exact, so this is a latency risk, not a correctness one (validate endpoint only; the save path does not use this query) |
| **The widened SQL bound truncates a page while `has_more` claims more** | Med | the rejected band is monotonic in distance, so the first failing row ends the page and forces `has_more=false`; boundary integration test at `0.79996`/`0.79994` |
| **Casefolding before embedding costs ES/EN separation** on a cased checkpoint | Med | calibration fixture measures both variants in slice 9; the fallback (embed the display form) is a *spec* change, so it cannot be made silently in code |
| **A UI label narrates work that already happened** (a "Guardando..." after the 201) | Low | removed: labels exist only while a request is in flight; after a 201 the machine is `idle`; ADR-005 states the rule and the label-order component test enforces it |
| A running `torch` forward pass cannot be cancelled after `EmbeddingTimeout` | Med | bounded executor + semaphore: a stuck call keeps its slot and later requests fail fast instead of piling up threads; controllable-slow-fake test; documented limit |
| The save waits indefinitely on a stuck advisory-lock holder | Low | `SET LOCAL lock_timeout` (`LOCK_TIMEOUT_MS`), mapped to 500 `INTERNAL_ERROR`, nothing persisted |
| 21 slices is a long chain to keep rebased | Med | each slice is self-contained and test-gated; retarget/rebase per the Feature Branch Chain rule; 2b is the most droppable link if the chain needs shortening (slices must still stay <= 400, so merging others is not free) |

## Open Questions

- [ ] Confirm the `pgvector` image tag and extension version in slice 4 before writing migration 0001.
- [ ] Record the measured API image size in ADR-003 (slice 8) — it is the migration-trigger baseline.
- [ ] Confirm the 0.80 default survives the ES/EN calibration run (slice 9); adjust the default and
      the ADR if the observed margin sits elsewhere.
- [ ] Size `EMBEDDING_CACHE_SIZE` against the measured p95 embed latency from slice 8; the default
      512 (≈ 1 MB) is a memory-cheap guess, not a measurement.
- [ ] Revisit whether a shared embedding cache is warranted only if a deployment ever runs more than
      one API replica — out of scope while the target is single-worker Docker Compose.
- [ ] Record the pinned Hub commit SHA (`EMBEDDING_MODEL_REVISION`) in slice 8; it is unverified.
- [ ] Measure exact-scan `find_matches` cost in slice 5a and decide whether the deferred scaling path
      (pgvector >= 0.8 iterative scan, unverified) is ever needed.
- [x] ~~Decide whether `GET /phrases` needs its own keyset pagination~~ — **resolved by api-contract**:
      it takes no parameters and is not paginated; it is hard-capped at `PHRASES_LIST_LIMIT`, and the
      repository port's unused `cursor` argument was dropped.
- [x] ~~Align `/health` with api-contract~~ — **resolved**: the spec allows a superset and pins the
      mapping (`model` = readiness string, `embedding_model` = model name); the design now matches it
      everywhere (D15, JSON, registry, tests).
- [x] ~~Align the phrase-ui transition table with its own scenarios~~ — **resolved**: the spec table
      and scenarios were rewritten together with the design's state machine and ADR-005 (`ok` →
      `revalidating`; no stage after the 201; 409 only from `revalidating` or, defensively, `saving`).
- [x] ~~Confirm the embedding input with the spec owner~~ — **resolved**: phrase-management already
      states that the comparison form is what is embedded; the design matches.
