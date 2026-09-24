# API Contract Specification

Capability: `api-contract` (new). Endpoints, JSON shapes, status codes, error envelope and error codes, pagination contract. All field names are English snake_case. Timestamps are ISO 8601 UTC strings. Scores are numbers rounded to 4 decimals. Resource ids (e.g. `id`, `most_similar_phrase_id`) are opaque strings: they are BIGINT in the database but MUST be serialized as strings in JSON, and clients MUST NOT interpret them numerically.

## ADDED Requirements

### Requirement: Response envelopes

Successful responses MUST be `{"data": <payload>}`. Error responses MUST be `{"error": {"code": <string>, "message": <string>, "details"?: <object>}}`. `code` is a stable UPPER_SNAKE_CASE identifier; `message` is a short English developer-facing string (the UI owns display copy); `details` is optional. Every non-2xx response, including framework-generated ones (unknown route 404, 405, request-body parse errors, unhandled exceptions), MUST use this envelope.

#### Scenario: Success envelope
- GIVEN any successful call
- WHEN the body is parsed
- THEN it has exactly one top-level key `data`

#### Scenario: Unknown route
- GIVEN `GET /nope`
- WHEN called
- THEN 404 with `{"error":{"code":"NOT_FOUND",...}}`

#### Scenario: Wrong method
- GIVEN `DELETE /phrases`
- WHEN called
- THEN 405 with `{"error":{"code":"METHOD_NOT_ALLOWED",...}}`

#### Scenario: Unhandled exception
- GIVEN an unexpected server exception
- WHEN a request triggers it
- THEN 500 `{"error":{"code":"INTERNAL_ERROR",...}}` and no stack trace or internal detail in the body

### Requirement: Error codes and status mapping

The API MUST use exactly these codes and statuses:

| HTTP | code | When |
| --- | --- | --- |
| 400 | `INVALID_CURSOR` | `cursor` malformed/undecodable, violating the cursor field rules (see `POST /phrases/matches`), or issued for a different normalized text or threshold |
| 404 | `NOT_FOUND` | unknown route |
| 405 | `METHOD_NOT_ALLOWED` | wrong method |
| 409 | `DUPLICATE_CONFIRMATION_REQUIRED` | save of a duplicate without `confirm_duplicate: true` |
| 413 | `PAYLOAD_TOO_LARGE` | request body larger than `MAX_REQUEST_BYTES` (default 1 MiB) |
| 422 | `VALIDATION_ERROR` | schema violation, wrong JSON type, empty text, over-length, bad `limit` |
| 500 | `INTERNAL_ERROR` | unhandled failure, including a database that is unreachable on any endpoint other than `/health` and a save that times out waiting for the write lock (no dedicated codes exist for these) |
| 503 | `EMBEDDING_UNAVAILABLE` | embedding provider raised / model not loaded |
| 504 | `EMBEDDING_TIMEOUT` | embedding exceeded `EMBEDDING_TIMEOUT_SECONDS` |

There MUST be no `EXACT_DUPLICATE` code. `VALIDATION_ERROR.details` MUST identify the offending field(s), e.g. `{"fields":[{"field":"text","reason":"empty"}]}` with reasons drawn from `empty`, `too_long`, `required`, `invalid_type`, `out_of_range`; `too_long` includes `max_length`. A bad cursor is NOT a `VALIDATION_ERROR`: it is `400 INVALID_CURSOR` (Previously: 422 `VALIDATION_ERROR` with reason `invalid_cursor`).

Input is bounded before it is processed. Text longer than 4 x `PHRASE_MAX_LENGTH` code points BEFORE normalization MUST be rejected with 422 `too_long` (`details.max_length` = `PHRASE_MAX_LENGTH`) without being normalized or embedded, which bounds the cost of normalizing hostile input. A request body larger than `MAX_REQUEST_BYTES` MUST be rejected with 413 `PAYLOAD_TOO_LARGE` before it is parsed. JSON types are strict: a value of the wrong JSON type (e.g. a numeric string where an integer is required) is `invalid_type`, never coerced.

#### Scenario: Empty text
- GIVEN `POST /phrases/validate {"text":"  "}`
- WHEN called
- THEN 422 `VALIDATION_ERROR` with `details.fields[0] == {"field":"text","reason":"empty"}`

#### Scenario: Too long
- GIVEN 281 characters and default config
- WHEN validate is called
- THEN 422 with `details.fields[0].reason == "too_long"` and `details.max_length == 280`

#### Scenario: Provider failure
- GIVEN a failing embedding provider
- WHEN validate or save is called
- THEN 503 `EMBEDDING_UNAVAILABLE`

#### Scenario: Provider timeout
- GIVEN a slow embedding provider
- WHEN validate or save is called
- THEN 504 `EMBEDDING_TIMEOUT`

#### Scenario: Malformed JSON
- GIVEN a body that is not valid JSON
- WHEN posted
- THEN 422 `VALIDATION_ERROR` in the envelope

#### Scenario: Raw length cap
- GIVEN `PHRASE_MAX_LENGTH=280` and a text of 1121 code points (mostly padding) before normalization
- WHEN validate or save is called
- THEN 422 `too_long` with `details.max_length == 280` and no embedding call occurs

#### Scenario: Oversized body
- GIVEN a request body larger than `MAX_REQUEST_BYTES`
- WHEN posted
- THEN 413 `PAYLOAD_TOO_LARGE` in the envelope and nothing is parsed or embedded

#### Scenario: Database unreachable outside health
- GIVEN the database is unreachable
- WHEN `POST /phrases` is called
- THEN 500 `INTERNAL_ERROR` (documented behavior; only `/health` reports `NOT_READY`) and nothing is persisted

### Requirement: POST /phrases/validate

Request: `{"text": string, "limit"?: integer}`. `limit` is the page-1 size; it MUST be a strict JSON integer (numeric strings, booleans and floats are rejected), defaults to `MATCHES_PAGE_SIZE` and MUST be within [1, `MATCHES_PAGE_SIZE`] (`MATCHES_PAGE_SIZE` itself is 1..200). The endpoint takes no `cursor`, is stateless and MUST persist nothing. (Previously: also accepted `cursor`, `limit` up to 200.)

Response 200:

```json
{
  "data": {
    "is_duplicate": true,
    "threshold": 0.8,
    "score": 0.9312,
    "most_similar": {"id": "<id>", "text": "Comprar leche", "score": 0.9312},
    "matches": [
      {"id": "<id>", "text": "Comprar leche", "score": 0.9312}
    ],
    "next_cursor": null,
    "has_more": false,
    "total": 1
  }
}
```

`score` and `most_similar` are null when the store is empty; `matches` is `[]` when nothing meets the threshold. `matches` holds page 1 only, in the ordering defined in semantic-validation (raw distance asc, `id` asc; displayed scores are non-increasing). `next_cursor` is an opaque string when `has_more` is true, otherwise null. `total` is the full count of phrases meeting the threshold, independent of pagination (the UI's "10/46 coincidencias" counter) — `0` when the store is empty or nothing meets the threshold. Pages 2..n are fetched via `POST /phrases/matches`; verdict fields exist only in this response.

#### Scenario: Duplicate found
- GIVEN stored "Comprar leche" scoring 0.9312 against the input
- WHEN `POST /phrases/validate {"text":"Buy milk"}` is called
- THEN 200 with the body above: `is_duplicate` true, `threshold` 0.8, one match, `has_more` false, `next_cursor` null, `total` 1

#### Scenario: Empty store
- GIVEN an empty store
- WHEN validate is called
- THEN 200 `{"data":{"is_duplicate":false,"threshold":0.8,"score":null,"most_similar":null,"matches":[],"next_cursor":null,"has_more":false,"total":0}}`

#### Scenario: Page 1 carries the verdict
- GIVEN 120 matches
- WHEN validate is called with `limit: 50`
- THEN 50 matches, `has_more` true, non-null `next_cursor`, `total` 120, plus `is_duplicate`, `threshold`, `score`, `most_similar`

#### Scenario: Limit bounds
- GIVEN `limit` of 0, -1, `"ten"`, or greater than `MATCHES_PAGE_SIZE`
- WHEN validate is called
- THEN 422 `VALIDATION_ERROR` with `details.fields[0].field == "limit"`

#### Scenario: Strict integer limit
- GIVEN `limit` of `"10"`, `true` or `10.5`
- WHEN validate is called
- THEN 422 `VALIDATION_ERROR` with `details.fields[0].field == "limit"` and reason `invalid_type`

#### Scenario: Default limit
- GIVEN 60 matches and `MATCHES_PAGE_SIZE=50`
- WHEN called without `limit`
- THEN 50 matches, `has_more` true

#### Scenario: Cursor not accepted
- GIVEN a body containing `cursor`
- WHEN validate is called
- THEN the field is ignored and page 1 is returned

#### Scenario: Nothing persisted
- GIVEN any validate call
- WHEN followed by `GET /phrases`
- THEN the list is unchanged

### Requirement: POST /phrases/matches

Request: `{"text": string, "cursor": string, "limit"?: integer}`; `cursor` is REQUIRED and `limit` follows the validate bounds. Response 200: `{"data": {"matches": [...], "next_cursor": string|null, "has_more": boolean, "total": integer}}`. `total` is the same full-count value validate's page 1 reported for this text (independent of pagination), so a client resuming from a stored cursor without ever having seen page 1 can still render the counter. It MUST NOT include `is_duplicate`, `threshold`, `score` or `most_similar`. The endpoint is stateless and persists nothing. The cursor is opaque (base64url; clients MUST NOT parse it) and bound to the normalized text and the threshold in force when issued. A malformed cursor, or one issued for a different normalized text or threshold, MUST return `400 INVALID_CURSOR`, and no embedding is computed for a malformed cursor. The cursor MUST be validated strictly BEFORE anything is embedded or queried: it MUST NOT exceed a maximum length derived from `PHRASE_MAX_LENGTH`; it MUST be strict base64url decoding to a JSON object (no NaN/Infinity literals) whose version `v` is the supported version, whose text `t` is a string, whose raw distance `d` is a finite number in [0, 2], whose id `i` is a positive integer that fits in int64 (booleans rejected), and whose threshold `th` is a finite number in [0, 1]; any violation, unknown or missing field is `400 INVALID_CURSOR`. Ordering and completeness semantics are defined in semantic-validation.

#### Scenario: Pagination walk
- GIVEN 120 matches and page 1 from validate with `limit: 50`
- WHEN `POST /phrases/matches {"text": same, "cursor": <next_cursor>, "limit": 50}` is called repeatedly
- THEN pages have 50, 20 items after page 1; the last has `has_more` false and `next_cursor` null

#### Scenario: No verdict fields
- GIVEN a valid cursor
- WHEN matches is called
- THEN `data` has exactly `matches`, `next_cursor`, `has_more`, `total`

#### Scenario: Cursor with different text
- GIVEN a cursor issued for text A
- WHEN used with text B
- THEN 400 `INVALID_CURSOR`

#### Scenario: Cursor with different threshold
- GIVEN a cursor issued at threshold 0.80 and the service restarted at 0.90
- WHEN it is submitted
- THEN 400 `INVALID_CURSOR`

#### Scenario: Malformed cursor
- GIVEN `cursor="not-a-cursor"` or valid base64url that is not a cursor
- WHEN matches is called
- THEN 400 `INVALID_CURSOR`

#### Scenario: Cursor field violations
- GIVEN cursors that decode to a JSON object but violate one field rule each: wrong `v`; `t` not a string; `d` negative, above 2, NaN or a string; `i` zero, negative, above int64 or `true`; `th` below 0, above 1 or non-finite; a missing or extra field; or an encoded length above the maximum
- WHEN matches is called
- THEN each returns 400 `INVALID_CURSOR` and nothing is embedded (table-driven)

#### Scenario: Missing cursor
- GIVEN a body without `cursor`
- WHEN posted
- THEN 422 `VALIDATION_ERROR` with `details.fields[0].field == "cursor"`

#### Scenario: Limit bounds
- GIVEN `limit` of 0 or above `MATCHES_PAGE_SIZE`
- WHEN called
- THEN 422 `VALIDATION_ERROR` on field `limit`

### Requirement: POST /phrases

Request: `{"text": string, "confirm_duplicate"?: boolean}`. `confirm_duplicate` MUST be a strict JSON boolean (`"yes"`, `1`, `"true"` are rejected with 422, never coerced). Unknown fields MUST be ignored. The server always re-validates (see duplicate-confirmation).

Response 201:

```json
{
  "data": {
    "id": "<id>",
    "text": "Buy milk",
    "created_at": "2026-09-21T12:00:00Z",
    "validation": {
      "status": "duplicate_confirmed",
      "score": 0.9312,
      "most_similar_phrase_id": "<id>",
      "validated_at": "2026-09-21T12:00:00Z"
    }
  }
}
```

Response 409 (`DUPLICATE_CONFIRMATION_REQUIRED`): the error envelope with `details` = `{threshold, score, most_similar, matches, next_cursor, has_more, total}` (same shapes as the validate response). Other statuses per the error table.

#### Scenario: Created unique
- GIVEN an empty store
- WHEN `POST /phrases {"text":"Regar plantas"}` is called
- THEN 201, `data.validation` is `{"status":"unique","score":null,"most_similar_phrase_id":null,"validated_at":<timestamp>}`

#### Scenario: Conflict shape
- GIVEN a duplicate exists
- WHEN saved without confirmation
- THEN 409 `{"error":{"code":"DUPLICATE_CONFIRMATION_REQUIRED","message":<string>,"details":{"threshold":0.8,"score":0.9312,"most_similar":{...},"matches":[...],"next_cursor":null,"has_more":false,"total":1}}}`

#### Scenario: Created confirmed
- GIVEN a duplicate exists
- WHEN saved with `confirm_duplicate: true`
- THEN 201 with `validation.status == "duplicate_confirmed"`

#### Scenario: Strict boolean flag
- GIVEN `confirm_duplicate` of `"yes"`, `1` or `"true"`
- WHEN `POST /phrases` is called
- THEN 422 `VALIDATION_ERROR` with `details.fields[0].field == "confirm_duplicate"` and reason `invalid_type`, and nothing is persisted

#### Scenario: Text is stored normalized
- GIVEN `{"text":"  Hola​  "}`
- WHEN saved
- THEN `data.text == "Hola"`

### Requirement: GET /phrases

Returns 200 `{"data":{"items":[<phrase>...], "total": integer, "next_cursor": string|null, "has_more": boolean}}` where `<phrase>` has the same shape as the 201 payload, ordered newest first (`created_at desc, id desc`). Keyset-paginated: `limit` (optional query param, defaults to `PHRASES_PAGE_SIZE`, bounded `[1, PHRASES_LIST_LIMIT]`) and `cursor` (optional, opaque, from a previous page's `next_cursor`) let a client page through the FULL store — this supersedes the previous "not paginated, hard-capped, older phrases unreachable" limitation. `total` is the full row count regardless of pagination. The cursor is opaque (base64url; clients MUST NOT parse it), carries only a `(created_at, id)` keyset position — no text/threshold binding, unlike `POST /phrases/matches`'s cursor — and a cursor from one endpoint MUST NOT be accepted by the other. A malformed cursor MUST return `400 INVALID_CURSOR`, decided strictly before any query runs.

#### Scenario: List shape
- GIVEN two stored phrases
- WHEN `GET /phrases` is called
- THEN 200, `data.items` has 2 entries each with `id`, `text`, `created_at`, `validation.{status,score,most_similar_phrase_id,validated_at}`, newest first, and `data.total == 2`

#### Scenario: Empty
- GIVEN no phrases
- WHEN called
- THEN 200 `{"data":{"items":[],"total":0,"next_cursor":null,"has_more":false}}`

#### Scenario: Default page size
- GIVEN `PHRASES_PAGE_SIZE=10` and 15 stored phrases
- WHEN `GET /phrases` is called without `limit`
- THEN 10 items are returned, `has_more` true, `total` 15

#### Scenario: Pagination walk
- GIVEN 25 stored phrases and `limit=10`
- WHEN `GET /phrases` is followed through `next_cursor` until `has_more` is false
- THEN 25 distinct ids are returned in total across 3 pages (10, 10, 5), newest first, none repeated or skipped

#### Scenario: Limit bounds
- GIVEN `limit` of 0 or greater than `PHRASES_LIST_LIMIT`
- WHEN `GET /phrases` is called
- THEN 422 `VALIDATION_ERROR`

#### Scenario: Malformed or cross-endpoint cursor
- GIVEN `cursor="not-a-cursor"`, or a valid `POST /phrases/matches` cursor
- WHEN `GET /phrases` is called with it
- THEN 400 `INVALID_CURSOR`

### Requirement: GET /health

`GET /health` is a readiness probe. It MUST return 200 `{"data":{"status":"ok","database":"ok","model":"ready","dimensions":<integer>,"embedding_model":"<model name>","embedding_cache":{"hits":<int>,"misses":<int>,"evictions":<int>,"size":<int>,"capacity":<int>}}}` only when the database is reachable AND the embedding model is loaded. Otherwise it MUST return 503 with the error envelope, code `NOT_READY`, and per-component `details` (`{"database":"ok"|"unavailable","model":"ready"|"unavailable", ...}` plus the same `dimensions`, `embedding_model` and `embedding_cache` fields where known). `model` is the readiness string (`"ready"` | `"unavailable"`) and `embedding_model` is the model name string; the 503 `details` use the same keys. `embedding_cache` is the only place cache statistics are exposed (operational, not part of any phrase endpoint). It MUST NOT itself run a heavy embedding.

#### Scenario: Ready
- GIVEN db reachable and model loaded
- WHEN `GET /health` is called
- THEN 200 and the body MUST include `status`, `database`, `model`, `dimensions`, `embedding_model` and `embedding_cache` (a superset of these fields is allowed; the body is not required to equal the shape above exactly)

#### Scenario: Model not loaded
- GIVEN the model has not finished loading
- WHEN called
- THEN 503 `NOT_READY` with `details.model == "unavailable"`

#### Scenario: Database down
- GIVEN the database is unreachable
- WHEN called
- THEN 503 `NOT_READY` with `details.database == "unavailable"`

Note: `NOT_READY` (503) is added to the code table for `/health` only.

### Requirement: OpenAPI documentation

The generated OpenAPI document MUST describe every endpoint, request/response schema, the pagination parameters and fields, the `400`/`409`/`422`/`503`/`504` responses, and every error code above. A contract test MUST assert this.

#### Scenario: Endpoints documented
- GIVEN `/openapi.json`
- WHEN inspected
- THEN paths `/phrases/validate` (POST), `/phrases/matches` (POST), `/phrases` (GET, POST) and `/health` (GET) exist

#### Scenario: Error responses documented
- GIVEN the POST `/phrases` operation
- WHEN inspected
- THEN responses 201, 409, 422, 503 and 504 are declared with the error envelope schema

#### Scenario: Pagination documented
- GIVEN the POST `/phrases/validate` and `/phrases/matches` operations
- WHEN inspected
- THEN validate declares `limit` and responds with `next_cursor` and `has_more`; matches declares `text`, `cursor` and `limit`, responds with `next_cursor` and `has_more`, and declares 400 `INVALID_CURSOR`; the cursor is documented as opaque

#### Scenario: Every code documented
- GIVEN the error registry
- WHEN compared with the OpenAPI document
- THEN every `code` in the registry appears in it

### Requirement: Caching is invisible to the contract

No response body or status of any phrase endpoint MAY depend on cache state (see semantic-validation, Embedding cache). The API MUST expose no cache-related field or header, except the operational `embedding_cache` counters in `GET /health`.

#### Scenario: Cold and warm responses identical
- GIVEN the same request sent with a cold and then a warm embedding cache
- WHEN the two responses are compared
- THEN status and body are byte-identical

### Requirement: CORS and configuration

The backend MUST accept cross-origin requests only from origins listed in `CORS_ORIGINS` (no wildcard). Allowed methods are `GET, POST, OPTIONS`; the allowed request header is `Content-Type`; credentials are NOT allowed (`allow_credentials=False`, no cookies). CORS headers MUST also be present on error responses, including 500. Every user-settable environment variable MUST be listed in `.env.example` with a default: `DATABASE_URL`, `POSTGRES_USER`, `POSTGRES_PASSWORD`, `POSTGRES_DB`, `SIMILARITY_THRESHOLD`, `MATCHES_PAGE_SIZE`, `PHRASE_MAX_LENGTH`, `PHRASES_LIST_LIMIT`, `PHRASES_PAGE_SIZE`, `MAX_REQUEST_BYTES`, `EMBEDDING_PROVIDER`, `EMBEDDING_MODEL`, `EMBEDDING_MODEL_REVISION`, `EMBEDDING_DIMENSIONS`, `EMBEDDING_TIMEOUT_SECONDS`, `EMBEDDING_MAX_CONCURRENCY`, `EMBEDDING_CACHE_SIZE`, `HNSW_EF_SEARCH`, `LOCK_TIMEOUT_MS`, `CORS_ORIGINS`, `LOG_LEVEL`, `NEXT_PUBLIC_API_URL`, `NEXT_PUBLIC_PHRASE_MAX_LENGTH`, `API_INTERNAL_URL`. Variables fixed inside the image (`HF_HUB_OFFLINE`, `TRANSFORMERS_OFFLINE`, `SENTENCE_TRANSFORMERS_HOME`) are not user-settable and are not listed. `EMBEDDING_PROVIDER=fake` is accepted only by the test settings, never by the runtime settings.

#### Scenario: Allowed origin
- GIVEN `CORS_ORIGINS=http://localhost:3000`
- WHEN a request arrives with that Origin
- THEN the response carries the matching `Access-Control-Allow-Origin`

#### Scenario: Disallowed origin
- GIVEN an Origin not in `CORS_ORIGINS`
- WHEN a request arrives
- THEN no `Access-Control-Allow-Origin` header is returned

#### Scenario: Preflight from an allowed origin
- GIVEN `CORS_ORIGINS=http://localhost:3000`
- WHEN `OPTIONS /phrases/validate` arrives with that Origin, `Access-Control-Request-Method: POST` and `Access-Control-Request-Headers: content-type`
- THEN the response carries the matching `Access-Control-Allow-Origin`, allowed methods including `POST`, allowed headers including `Content-Type`, and no `Access-Control-Allow-Credentials`

#### Scenario: Preflight from a disallowed origin
- GIVEN an Origin not in `CORS_ORIGINS`
- WHEN a preflight arrives
- THEN no `Access-Control-Allow-Origin` header is returned

#### Scenario: Errors carry CORS headers
- GIVEN an allowed Origin and a request that triggers an unhandled exception
- WHEN the 500 `INTERNAL_ERROR` response is produced
- THEN it still carries `Access-Control-Allow-Origin`, so the browser can read the envelope

#### Scenario: Env documented
- GIVEN `.env.example`
- WHEN read
- THEN every variable above is present
