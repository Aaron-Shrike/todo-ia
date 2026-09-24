# Duplicate Confirmation Specification

Capability: `duplicate-confirmation` (new). Server-side re-validation on save, the `confirm_duplicate` flag, the 409 flow, and concurrency behavior.

## ADDED Requirements

### Requirement: Server-side re-validation on every save

`POST /phrases` MUST recompute similarity server-side against the current store on EVERY call, regardless of whether the client validated first. The server MUST NOT accept or trust any client-supplied score, most-similar id, status or `validated_at`; such fields, if sent, MUST be ignored. Re-validation MUST always re-run the similarity query against current stored data; a cached verdict MUST NEVER be trusted. Only the embedding vector MAY be reused from the cache (see semantic-validation). The save verdict (`is_duplicate`, `score`, `most_similar`) and the metadata recorded on the stored row MUST NOT depend on an approximate index read: on save they MUST be derived from an EXACT nearest-neighbour scan (no HNSW index scan) taken inside the save transaction under the advisory lock. The approximate top-1 read is reserved for `POST /phrases/validate`.

#### Scenario: Similarity re-run despite warm cache
- GIVEN validate of T returned unique (embedding cached), then another phrase similar to T is saved
- WHEN `POST /phrases` is called for T without confirmation
- THEN the embedder is not called again, the similarity query runs against current data, and the response is 409 `DUPLICATE_CONFIRMATION_REQUIRED`

#### Scenario: Query count on save
- GIVEN a repository that counts similarity queries, a unique text T and a warm cache
- WHEN `POST /phrases` is called for T (201) and then again for T without confirmation (now an exact duplicate, 409)
- THEN the call that returns 201 ran exactly 1 similarity query (the EXACT nearest-neighbour lookup) plus the `INSERT`, and the call that returns 409 ran exactly 3 similarity queries (the EXACT nearest-neighbour lookup, the first match page, and the exact-scan count backing the 409 `details.total` counter, all exact scans) and no `INSERT`; neither call ran an approximate (HNSW) nearest-neighbour query (0 such queries); at most one embedding was computed across both calls

#### Scenario: Save does not use the approximate read
- GIVEN a repository spy whose approximate nearest-neighbour method returns a wrong (or no) neighbour, and a stored phrase that is a duplicate of T
- WHEN `POST /phrases` is called for T without confirmation
- THEN the approximate method is called 0 times, the verdict comes from the exact lookup, and the response is 409 `DUPLICATE_CONFIRMATION_REQUIRED` (not a 201 `unique`)

#### Scenario: Save catches a duplicate the approximate index would miss
- GIVEN an integration corpus larger than `hnsw.ef_search` where the HNSW top-1 for T misses a stored duplicate that an exact scan finds
- WHEN `POST /phrases` is called for T without confirmation
- THEN the response is 409 `DUPLICATE_CONFIRMATION_REQUIRED`, nothing is stored, and the plan of the save's nearest-neighbour query (EXPLAIN) contains no HNSW index scan

#### Scenario: Save without validating (unique)
- GIVEN no similar phrase exists
- WHEN `POST /phrases {"text":"Regar las plantas"}` is called without a prior validate
- THEN the response is 201 and the phrase is stored with status `unique`

#### Scenario: Save without validating (duplicate)
- GIVEN a similar phrase exists (score >= threshold)
- WHEN `POST /phrases {"text": ...}` is called without validate and without `confirm_duplicate`
- THEN the response is 409 `DUPLICATE_CONFIRMATION_REQUIRED` and nothing is stored

#### Scenario: Forged client score
- GIVEN a similar phrase exists
- WHEN the body is `{"text": ..., "score": 0.1, "is_duplicate": false, "validation_status": "unique"}`
- THEN the extra fields are ignored and the response is 409 `DUPLICATE_CONFIRMATION_REQUIRED`

#### Scenario: Stale validation
- GIVEN the client validated text T when it was unique, then another user saved a near-identical phrase
- WHEN the client saves T without `confirm_duplicate`
- THEN the server re-validates and responds 409 `DUPLICATE_CONFIRMATION_REQUIRED`

### Requirement: Explicit confirmation flag

`confirm_duplicate` MUST be an optional strict JSON boolean defaulting to false (no coercion). When the server-side score is >= threshold and `confirm_duplicate` is not exactly `true`, the save MUST be rejected with `409 DUPLICATE_CONFIRMATION_REQUIRED` and nothing persisted. When `true` and the phrase is a duplicate, the save MUST succeed with status `duplicate_confirmed`.

#### Scenario: Duplicate confirmed
- GIVEN a stored phrase P and a new phrase with score 0.92
- WHEN saved with `confirm_duplicate: true`
- THEN 201, status `duplicate_confirmed`, score 0.92, `most_similar_phrase_id = P.id`

#### Scenario: Flag on a non-duplicate
- GIVEN a phrase that is not a duplicate
- WHEN saved with `confirm_duplicate: true`
- THEN 201 and status is `unique` (the flag never falsifies status)

#### Scenario: Non-boolean flag
- GIVEN `confirm_duplicate` of `"yes"`, `1` or `"true"`
- WHEN saved
- THEN 422 `VALIDATION_ERROR` for each and nothing is stored

#### Scenario: Cancel saves nothing
- GIVEN a 409 response was received
- WHEN the client does not re-submit
- THEN no phrase was stored and the store is unchanged

#### Scenario: Exact duplicate confirmable
- GIVEN stored "Comprar leche"
- WHEN "comprar leche" is saved with `confirm_duplicate: true`
- THEN 201 with status `duplicate_confirmed`, score 1.0

### Requirement: 409 payload

The 409 response MUST use the error envelope with `code: DUPLICATE_CONFIRMATION_REQUIRED` and `details` containing the same fields as a validate response (`threshold`, `score`, `most_similar`, `matches` first page, `next_cursor`, `has_more`, `total`), so the client can render the alert without a second call.

#### Scenario: Payload completeness
- GIVEN 3 matches above threshold
- WHEN a save is rejected with 409
- THEN `details.most_similar` is the best phrase, `details.matches` has 3 items ordered by score desc, `details.has_more` is false, `details.total` is 3

#### Scenario: Large match set on 409
- GIVEN 120 matches and page size 50
- WHEN a save is rejected with 409
- THEN `details.matches` has 50 items, `details.has_more` true and `details.next_cursor` is usable with `POST /phrases/matches`

### Requirement: Failures never save

If the embedding provider fails or times out during save, the response MUST be 503 `EMBEDDING_UNAVAILABLE` or the timeout error, and NOTHING MUST be persisted. `confirm_duplicate: true` MUST NOT bypass validation: a provider failure still prevents saving.

#### Scenario: Model down on save
- GIVEN a failing provider
- WHEN `POST /phrases` is called
- THEN 503 `EMBEDDING_UNAVAILABLE` and the store is unchanged

#### Scenario: Model down with confirmation
- GIVEN a failing provider
- WHEN `POST /phrases {"text": ..., "confirm_duplicate": true}` is called
- THEN 503 and nothing is stored

#### Scenario: Timeout on save
- GIVEN a provider slower than `EMBEDDING_TIMEOUT_SECONDS`
- WHEN a save is attempted
- THEN the timeout error is returned and nothing is stored

#### Scenario: Database failure rolls back
- GIVEN the insert fails after validation
- WHEN a save is attempted
- THEN the response is 500 `INTERNAL_ERROR` and no partial row exists

### Requirement: Concurrency control

Check-and-insert MUST be serialized with a Postgres transaction-scoped advisory lock (`pg_advisory_xact_lock`) so that two concurrent saves see each other's committed result. The lock is complemented by a database backstop: a partial unique index on `normalized_text` restricted to `validation_status = 'unique'` (see phrase-management, "Database-level uniqueness of unconfirmed phrases"), which makes identical unconfirmed text a database guarantee. The wait for the lock MUST be bounded (`LOCK_TIMEOUT_MS`): a save that cannot obtain the lock in time fails with 500 `INTERNAL_ERROR` (no dedicated code) and persists nothing. A unique violation on insert MUST NOT surface as a 500: the save MUST be retried once, in a fresh transaction, through the normal check-and-insert path, which yields 409 `DUPLICATE_CONFIRMATION_REQUIRED`. The residual limitation MUST be documented in the design and README and stated honestly: the index does NOT cover semantic (non-identical) near-duplicates, which stay protected only by the lock and application logic (the lock is held only around check-and-insert; embedding runs outside it, and a reader who validated earlier can be stale).

#### Scenario: Concurrent similar saves
- GIVEN two concurrent `POST /phrases` requests with near-identical text and no confirmation, store initially empty
- WHEN both execute against real Postgres
- THEN exactly one returns 201 and the other returns 409 `DUPLICATE_CONFIRMATION_REQUIRED`

#### Scenario: Concurrent confirmed saves
- GIVEN two concurrent saves with `confirm_duplicate: true` of near-identical text
- WHEN both execute
- THEN both may succeed (201) and the store contains both rows

#### Scenario: Concurrent identical saves without confirmation
- GIVEN two concurrent `POST /phrases` requests with identical text (case and whitespace variants included), no confirmation, store initially empty
- WHEN both execute against real Postgres
- THEN exactly one returns 201 with status `unique`, the other returns 409 `DUPLICATE_CONFIRMATION_REQUIRED`, and the store holds exactly one such row

#### Scenario: Unique violation maps to 409, never 500
- GIVEN a `unique` row with normalized text T is committed after a save's check but before its insert (lock bypassed or lost)
- WHEN that save's insert raises a unique violation on the partial unique index
- THEN the save is retried once through the normal path and the response is 409 `DUPLICATE_CONFIRMATION_REQUIRED` with the full validate-shaped `details` (score 1.0), not 500 `INTERNAL_ERROR`, and nothing extra is stored

#### Scenario: Persistent violation still yields 409
- GIVEN the retry after a unique violation raises the violation again
- WHEN the save completes
- THEN the response is still 409 `DUPLICATE_CONFIRMATION_REQUIRED`, never 500

#### Scenario: Confirmed save cannot violate the index
- GIVEN a stored `unique` row with normalized text T
- WHEN T is saved with `confirm_duplicate: true` while a concurrent save of T also confirms
- THEN both succeed as `duplicate_confirmed` (the index only covers `unique` rows)

#### Scenario: Semantic near-duplicates are not covered by the index
- GIVEN two non-identical near-duplicate texts saved with the lock bypassed
- WHEN both inserts run as `unique`
- THEN the database accepts both (documented residual race; protected only by the lock and application logic)

#### Scenario: Lock wait is bounded
- GIVEN another transaction holds the advisory lock for longer than `LOCK_TIMEOUT_MS`
- WHEN a save is attempted
- THEN it fails with 500 `INTERNAL_ERROR` after roughly `LOCK_TIMEOUT_MS`, nothing is stored, and a later save succeeds once the lock is free

#### Scenario: Lock released on failure
- GIVEN a save that fails mid-transaction
- WHEN a subsequent save is issued
- THEN it is not blocked (lock released with the transaction)

#### Scenario: Limitation documented
- GIVEN the delivered design and README
- WHEN read
- THEN both state the advisory-lock scope and the documented residual race
