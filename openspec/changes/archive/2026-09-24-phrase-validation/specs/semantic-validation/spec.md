# Semantic Validation Specification

Capability: `semantic-validation` (new). Embedding, cosine similarity, threshold decision, `most_similar`, and the complete ordered match set. Behavior only; how pages reproduce the query vector is a design decision, but embedding reuse is bounded by the efficiency requirements below. Page 1 is served by `POST /phrases/validate`; pages 2..n by `POST /phrases/matches` (see api-contract).

Config: `SIMILARITY_THRESHOLD` (default 0.80), `MATCHES_PAGE_SIZE` (default 50), `EMBEDDING_TIMEOUT_SECONDS`.

## ADDED Requirements

### Requirement: Embedding via a swappable port

Similarity MUST be computed from vectors produced through an `EmbeddingProvider` port. The domain and application layers MUST NOT import the embedding runtime, FastAPI or SQLAlchemy. A fake provider MUST be usable in tests to inject exact vectors/scores.

#### Scenario: Domain isolation
- GIVEN the domain and application packages
- WHEN their imports are inspected
- THEN none import `sentence_transformers`, `torch`, `fastapi` or `sqlalchemy`

#### Scenario: Swap without domain change
- GIVEN a fake `EmbeddingProvider` returning fixed vectors
- WHEN `ValidatePhrase` runs
- THEN it produces results using only those vectors and no real model is loaded

### Requirement: Cosine similarity

Similarity MUST be cosine similarity between L2-normalized vectors. The raw cosine lies in [-1, 1], but a score MUST lie in [0, 1]: the domain clamps `score = min(1, max(0, raw))` BEFORE rounding, comparing, reporting or recording, so a negative raw cosine yields 0.0 and float overshoot (e.g. 1.0000000002) yields 1.0. Reported and compared scores MUST be rounded to 4 decimal places AFTER clamping; the threshold decision MUST use the same clamped, rounded value that is reported and recorded (so a stored `similarity_score` always satisfies its `BETWEEN 0 AND 1` check). A pure-Python domain cosine function MUST exist and agree with the repository's score within 1e-5 (tolerance rationale: pgvector stores vectors as float32, so the database score carries float32 rounding error that the pure-Python float64 cosine does not).

#### Scenario: Identical vectors
- GIVEN two identical non-zero vectors
- WHEN cosine is computed
- THEN the score is 1.0

#### Scenario: Orthogonal vectors
- GIVEN orthogonal vectors
- WHEN cosine is computed
- THEN the score is 0.0

#### Scenario: Rounding consistency
- GIVEN a raw cosine of 0.79996
- WHEN validated at threshold 0.80
- THEN the reported score is 0.8000 and the phrase IS a duplicate (decision uses the rounded value)

#### Scenario: Negative cosine is clamped
- GIVEN a raw cosine of -0.3 between the input and a stored phrase
- WHEN validated at threshold 0.80
- THEN the reported score is 0.0 (never negative), `is_duplicate` is false, and if the phrase is saved the stored `similarity_score` is 0.0

#### Scenario: Float overshoot is clamped
- GIVEN a raw cosine of 1.0000000002 (float error on identical vectors)
- WHEN validated
- THEN the reported score is 1.0

#### Scenario: Oracle agreement
- GIVEN random vector pairs
- WHEN scored by the domain cosine and by the pgvector-backed repository
- THEN the two scores differ by at most 1e-5 (float32 storage tolerance)

### Requirement: Threshold decision (inclusive)

A phrase MUST be flagged as a duplicate if and only if its best score (clamped to [0, 1] and rounded to 4 decimals, see Cosine similarity) is greater than or equal to `SIMILARITY_THRESHOLD`. The same threshold MUST decide which stored phrases appear in `matches`. The comparison MUST be exact on decimal values (a threshold with more than 4 decimals, e.g. 0.80005, is valid and is compared against the rounded score without binary-float error). Because scores are clamped, a threshold of 0 admits every stored phrase.

#### Scenario: Just below threshold (t - eps)
- GIVEN threshold 0.80 and a best score of 0.7999
- WHEN validated
- THEN `is_duplicate` is false and `matches` is empty

#### Scenario: Exactly at threshold (t)
- GIVEN threshold 0.80 and a best score of 0.8000
- WHEN validated
- THEN `is_duplicate` is true and that phrase is in `matches`

#### Scenario: Just above threshold (t + eps)
- GIVEN threshold 0.80 and a best score of 0.8001
- WHEN validated
- THEN `is_duplicate` is true and that phrase is in `matches`

#### Scenario: Threshold with more than four decimals
- GIVEN threshold 0.80005 and raw cosines 0.79996 (score 0.8000) and 0.80006 (score 0.8001)
- WHEN validated
- THEN the first is not a duplicate and the second is a duplicate

#### Scenario: Threshold zero admits everything
- GIVEN `SIMILARITY_THRESHOLD=0` and a stored phrase whose raw cosine with the input is -0.3 (score 0.0)
- WHEN validated
- THEN `is_duplicate` is true and that phrase is in `matches` with score 0.0

#### Scenario: Threshold changed via env
- GIVEN `SIMILARITY_THRESHOLD=0.95` and a best score of 0.90
- WHEN validated
- THEN `is_duplicate` is false and the response `threshold` is 0.95

### Requirement: Threshold configuration validation

`SIMILARITY_THRESHOLD` MUST be a number in the closed interval [0, 1]. Any other value (out of range, non-numeric, NaN, empty) MUST make the backend fail fast at startup with a clear message. The value 0 and 1 are valid.

#### Scenario: Out of range
- GIVEN `SIMILARITY_THRESHOLD=1.5` or `-0.1`
- WHEN the backend starts
- THEN startup fails with a configuration error naming the variable

#### Scenario: Non-numeric
- GIVEN `SIMILARITY_THRESHOLD=high`
- WHEN the backend starts
- THEN startup fails

#### Scenario: Boundary values accepted
- GIVEN `SIMILARITY_THRESHOLD=0` or `1`
- WHEN the backend starts
- THEN startup succeeds

### Requirement: Validation result shape

Validation MUST return: `is_duplicate` (bool), `threshold` (number), `score` (best score over ALL stored phrases, or null if the store is empty), `most_similar` (`{id, text, score}` of the best-scoring stored phrase, or null if the store is empty), and page 1 of `matches` with `next_cursor`, `has_more` and `total` (the full count of phrases meeting the threshold, independent of pagination — the UI's "10/46 coincidencias" counter; `0` when the store is empty or nothing meets the threshold). `score` and `most_similar` MUST report the best stored phrase even when it is below the threshold (so `is_duplicate` false with a non-null score is valid). When matches exist, `most_similar` MUST equal the first element of `matches`. These verdict fields are returned ONLY by validate; `POST /phrases/matches` returns `matches`, `next_cursor`, `has_more` and `total` only.

#### Scenario: Empty store
- GIVEN no stored phrases
- WHEN a valid phrase is validated
- THEN `is_duplicate` false, `score` null, `most_similar` null, `matches` `[]`, `has_more` false, `next_cursor` null, `total` 0

#### Scenario: Best below threshold
- GIVEN stored phrases scoring 0.55 and 0.40 against the input (threshold 0.80)
- WHEN validated
- THEN `is_duplicate` false, `score` 0.55, `most_similar` is the 0.55 phrase, `matches` `[]`

#### Scenario: most_similar equals first match
- GIVEN stored phrases scoring 0.95 and 0.85
- WHEN validated
- THEN `most_similar` is the 0.95 phrase and `matches[0]` is the same phrase with the same score

#### Scenario: Statelessness
- GIVEN any validation call
- WHEN it completes (success or failure)
- THEN no row is inserted or modified

### Requirement: Complete ordered match set

`matches` MUST contain EVERY stored phrase with score >= threshold — never a fixed top-N — delivered page by page (page 1 from validate, pages 2..n from `POST /phrases/matches`). Concatenating all pages MUST yield the complete set exactly once, in order. `has_more` MUST be true if and only if further matches exist beyond the current page.

Ordering: the observable ordering key is `(raw distance asc, id asc)` — equivalently unrounded score descending, with `id` ascending as the tie-break for equal raw distance (distances are compared on a 1e-6 tolerance grid so that paging survives sub-ulp drift of the recomputed query vector; see design). The reported 4-decimal scores are non-increasing along the list, but two items that DISPLAY the same score are NOT necessarily in `id` order, because their raw distances may differ. `matches` is produced by an exact scan (never an approximate index), so it is complete regardless of how many phrases match.

#### Scenario: All matches reachable
- GIVEN 120 stored phrases scoring above threshold and page size 50
- WHEN validate is called and then `/phrases/matches` is followed through `next_cursor` until `has_more` is false
- THEN 3 pages are returned (50, 50, 20), 120 distinct ids in total, in the ordering defined above

#### Scenario: Exact page boundary
- GIVEN exactly 50 matches and page size 50
- WHEN the first page is requested
- THEN 50 items are returned, `has_more` is false and `next_cursor` is null

#### Scenario: One over page boundary
- GIVEN 51 matches and page size 50
- WHEN pages are followed
- THEN page 1 has 50 items with `has_more` true, page 2 has 1 item with `has_more` false

#### Scenario: Tie scores across a page boundary
- GIVEN 5 matches with bit-identical embedding vectors (therefore equal raw distance, all scoring 0.9000) with ids 1..5 and `limit=2`
- WHEN pages are followed
- THEN the pages contain ids [1,2], [3,4], [5]: none repeated, none skipped

#### Scenario: Displayed ties are ordered by raw distance
- GIVEN id 1 with raw score 0.90001 and id 2 with raw score 0.90004, both displayed as 0.9000
- WHEN validated
- THEN id 2 precedes id 1 (higher raw score first) even though both show 0.9000

#### Scenario: Paging beyond the former approximate-index window
- GIVEN 500 stored phrases above threshold (more than the default `hnsw.ef_search` of 200) and page size 50
- WHEN validate is called and `/phrases/matches` is followed through `next_cursor` until `has_more` is false
- THEN 10 pages are returned, 500 distinct ids in total, none missing and none repeated

#### Scenario: Threshold zero
- GIVEN `SIMILARITY_THRESHOLD=0.0` (which admits every stored phrase, since scores are clamped to [0, 1]) and 500 stored phrases
- WHEN validated
- THEN only the first page (default 50) is returned with `has_more` true and the payload never contains all 500

#### Scenario: Custom page size
- GIVEN `MATCHES_PAGE_SIZE=10` and 25 matches
- WHEN validated without `limit`
- THEN the first page has 10 items

### Requirement: Page consistency and staleness

Pages requested for the same text MUST be ordered consistently: each subsequent page continues strictly after the cursor position in the ordering defined above. A phrase saved between two page requests MAY appear or not (paging is advisory), but MUST NOT cause an item already delivered to be delivered again or the ordering to be violated, and `has_more` MUST remain truthful for the state observed by that request.

#### Scenario: Phrase saved between pages
- GIVEN page 1 was delivered, then a new phrase with a score higher than every delivered item is saved
- WHEN page 2 is requested with page 1's cursor
- THEN page 2 contains no id already delivered on page 1 and remains ordered after the cursor position

#### Scenario: Cursor bound to the query text
- GIVEN a cursor produced for text A
- WHEN it is submitted to `/phrases/matches` with text B
- THEN the request is rejected with `400 INVALID_CURSOR`

#### Scenario: Cursor bound to the threshold
- GIVEN a cursor produced at threshold 0.80
- WHEN it is submitted while the threshold is 0.90
- THEN the request is rejected with `400 INVALID_CURSOR`

#### Scenario: Vector drift does not repeat or skip
- GIVEN page 1 was delivered for a text and page 2 is requested with a recomputed query vector perturbed by one float32 ulp per component (as after a cache eviction or on another worker)
- WHEN the whole sequence is followed to the end on a fixture whose distances do not lie on a tolerance-grid edge
- THEN no id is delivered twice and none is skipped

#### Scenario: Malformed cursor
- GIVEN `cursor="not-a-cursor"`
- WHEN `/phrases/matches` is called
- THEN the response is `400 INVALID_CURSOR` and nothing is embedded

### Requirement: Exact duplicates are ordinary duplicates

A phrase equal to a stored phrase ignoring case and whitespace differences MUST score 1.0 (after rounding; both are embedded from the same comparison form, so the vectors are identical), be flagged as a duplicate, and be confirmable. No separate exact-duplicate error or code exists.

#### Scenario: Case and spacing variants
- GIVEN stored "Comprar leche"
- WHEN "  comprar   LECHE " is validated
- THEN `is_duplicate` true, `score` 1.0, `most_similar.text` is "Comprar leche"

#### Scenario: Confirmable
- GIVEN the same input
- WHEN saved with `confirm_duplicate: true`
- THEN it is stored with status `duplicate_confirmed`

### Requirement: Model failure and timeout

If the embedding provider raises or exceeds `EMBEDDING_TIMEOUT_SECONDS`, validation MUST fail explicitly (503 `EMBEDDING_UNAVAILABLE` or 504 timeout, see api-contract). Validation MUST NOT be silently skipped, MUST NOT return a fabricated "not duplicate" result, and MUST NOT persist anything.

#### Scenario: Provider raises
- GIVEN a provider that raises on embed
- WHEN validate is called
- THEN the outcome is `EMBEDDING_UNAVAILABLE`, no `is_duplicate` value is returned, and no row exists

#### Scenario: Provider times out
- GIVEN a provider slower than `EMBEDDING_TIMEOUT_SECONDS`
- WHEN validate is called
- THEN the outcome is a timeout error and no row exists

#### Scenario: Recovery
- GIVEN a provider that failed once and then recovers
- WHEN the same request is retried
- THEN it succeeds normally

### Requirement: Embedding reuse within a bounded window

For a given comparison form (the text that is embedded), the system MUST NOT recompute the embedding while a cached vector for it exists. This applies across validate, `/phrases/matches` (any page) and `POST /phrases`. Tests MUST observe this through an embedder call counter on the fake provider.

#### Scenario: Validate then pages
- GIVEN a cold cache and a counting fake embedder
- WHEN validate is called and then `/phrases/matches` for pages 2 and 3 with the same text
- THEN the embedder was called exactly once

#### Scenario: Validate then save
- GIVEN validate was called for text T
- WHEN `POST /phrases` is called for T within the cache window
- THEN the embedder call count is still 1

#### Scenario: Normalization variants share an entry
- GIVEN validate of "Comprar leche" then of "  comprar   leche " (same comparison form, which is the embedding input and cache key)
- WHEN both complete
- THEN the embedder was called once

#### Scenario: Blind save
- GIVEN a cold cache entry for T and no prior validate by the user
- WHEN a blind Save runs `POST /phrases/validate` then `POST /phrases` for T
- THEN the embedder is called exactly once across the sequence (validate warms the cache, save reuses it); if T was already cached, zero times

#### Scenario: Evicted entry
- GIVEN the cache is full and T was evicted by newer entries
- WHEN T is requested again
- THEN the embedder is called again and the response is unchanged

### Requirement: Embedding cache is a pure optimization

The cache key MUST be the normalized text plus the embedding model identifier. The cache MUST be bounded in size (entries are evicted when full). It MUST NOT change any response: identical inputs yield identical status and body with a cold or warm cache. A failed embedding (provider error or timeout) MUST NOT be cached.

#### Scenario: Cold equals warm
- GIVEN the same validate request run against a cold and a warm cache
- WHEN the responses are compared
- THEN they are identical

#### Scenario: Model identifier in key
- GIVEN a cached vector for text T under model M1
- WHEN T is requested under model M2
- THEN the embedder is called and M1's vector is not used

#### Scenario: Bounded size
- GIVEN capacity N and N+1 distinct texts embedded
- WHEN the cache is inspected
- THEN it holds at most N entries

#### Scenario: Failures not cached
- GIVEN a provider that fails once for T then recovers
- WHEN T is requested twice
- THEN the second request calls the embedder again and succeeds

### Requirement: Keyset match pagination

Match pages MUST use keyset pagination from the cursor position and MUST NOT use OFFSET, so that a page is defined by the position it continues from rather than by a row count that shifts when phrases are saved. The `matches` query MUST be an exact scan (it MUST NOT depend on an approximate index): each page costs work proportional to the number of stored phrases (O(n)), which is accepted at the target scale. The cost of page N is NOT claimed to be independent of N. The keyset comparison MUST tolerate sub-ulp drift of the recomputed query vector (1e-6 tolerance grid with `id` tie-break).

#### Scenario: No OFFSET
- GIVEN the match query issued for page 5
- WHEN the SQL is captured in an integration test
- THEN it contains no `OFFSET` and it filters strictly after the cursor's `(distance bucket, id)` position

#### Scenario: Exact scan
- GIVEN a corpus larger than `hnsw.ef_search`
- WHEN the match query plan is captured (EXPLAIN) in an integration test
- THEN the plan contains no HNSW index scan

#### Scenario: Exact scan on the save path
- GIVEN a corpus larger than `hnsw.ef_search`
- WHEN the nearest-neighbour query used by `POST /phrases` is captured (EXPLAIN) in an integration test
- THEN the plan contains no HNSW index scan (the approximate top-1 is used by `POST /phrases/validate` only)

### Requirement: Cross-language calibration

A calibration fixture of ES/EN phrase pairs MUST exist. A `slow`-marked test using the real model MUST assert that known paraphrase pairs (including mixed ES/EN, e.g. "Comprar leche" / "Buy milk") score >= the configured default threshold and known unrelated pairs score below it. The default threshold (initially 0.80, a working value) is FINALIZED after the first measured run of this test; if the measured margin requires a different default, changing it is a recorded spec-change trigger (spec, design ADR and this requirement are updated together), never a silent code change and never a fixture bent to fit. The slow test is a MANUAL evidence step (`make evidence`, not part of CI) and doubles as embedding-integration evidence.

#### Scenario: Paraphrase pairs flagged
- GIVEN the real model and the fixture's paraphrase pairs
- WHEN each pair is scored
- THEN every pair scores >= the configured default threshold

#### Scenario: Unrelated pairs pass
- GIVEN the fixture's unrelated pairs
- WHEN each is scored
- THEN every pair scores < the configured default threshold

#### Scenario: Default changes are recorded
- GIVEN the first measured slow run shows a separating margin not near 0.80
- WHEN the default threshold is changed
- THEN the spec, the design ADR and the measured margin are updated in the same change
