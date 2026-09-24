# Delta for api-contract

## MODIFIED Requirements

### Requirement: GET /phrases

Returns 200 `{"data":{"items":[<phrase>...], "total": integer, "next_cursor": string|null, "has_more": boolean}}` where `<phrase>` has the same shape as the 201 payload, ordered newest first (`created_at desc, id desc`). Keyset-paginated: `limit` (optional query param, defaults to `PHRASES_PAGE_SIZE`, bounded `[1, PHRASES_LIST_LIMIT]`) and `cursor` (optional, opaque, from a previous page's `next_cursor`) let a client page through the FULL store — this supersedes the previous "not paginated, hard-capped, older phrases unreachable" limitation. Three additional optional query params filter the list, combined with AND semantics when more than one is present: `status` (one of `unique` or `duplicate_confirmed`; any other value is invalid), `q` (case-insensitive substring match against `normalized_text`, compared using the same casefolding used to derive `normalized_text`; blank or omitted counts as absent; length is capped at `PHRASE_MAX_LENGTH`; accent-insensitivity is out of scope — a query for an unaccented form does NOT match an accented stored value; literal `%`, `_` and `\` in `q` are matched literally, never as wildcards), and `min_score` (float in `[0, 1]`; matches `similarity_score >= min_score`; rows with a NULL `similarity_score` are excluded, per standard SQL semantics). An invalid `status`, an out-of-range `min_score`, or a `q` longer than `PHRASE_MAX_LENGTH` MUST return 422 `VALIDATION_ERROR` (same convention as `limit` bound violations). `total` is the row count of the ACTIVE filter set — the full store when no filter is present. The cursor is opaque (base64url; clients MUST NOT parse it), carries only a `(created_at, id)` keyset position — no filter or threshold binding, unlike `POST /phrases/matches`'s cursor — and a cursor from one endpoint MUST NOT be accepted by the other. Filter params are NOT encoded in the cursor: a client MUST resend the same filter query params on every page request to keep pagination consistent across pages. A malformed cursor MUST return `400 INVALID_CURSOR`, decided strictly before any query runs.
(Previously: no `status`/`q`/`min_score` params; `total` was always the full row count regardless of pagination.)

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

#### Scenario: Filter by status
- GIVEN phrases with mixed `validation_status`
- WHEN `GET /phrases?status=duplicate_confirmed` is called
- THEN only matching items are returned and `data.total` equals their count

#### Scenario: Invalid status value
- GIVEN `status=bogus`
- WHEN `GET /phrases` is called
- THEN 422 `VALIDATION_ERROR`

#### Scenario: Filter by text, case-insensitive
- GIVEN a stored phrase whose `normalized_text` contains "leche"
- WHEN `GET /phrases?q=LECHE` is called
- THEN the phrase is included in `data.items`

#### Scenario: Text filter matches wildcard characters literally
- GIVEN a stored phrase containing a literal `%` or `_`
- WHEN `GET /phrases` is called with `q` containing that literal character
- THEN it is matched as a literal character, not as a SQL wildcard

#### Scenario: Text filter is not accent-insensitive
- GIVEN a stored phrase "café" and no unaccented variant stored
- WHEN `GET /phrases?q=cafe` is called
- THEN "café" is NOT returned (documented limitation)

#### Scenario: Blank q is treated as absent
- GIVEN `q=` (empty string) or `q` omitted
- WHEN `GET /phrases` is called
- THEN no text filter is applied

#### Scenario: q over the length cap
- GIVEN a `q` value longer than `PHRASE_MAX_LENGTH`
- WHEN `GET /phrases` is called
- THEN 422 `VALIDATION_ERROR`

#### Scenario: Minimum score excludes NULL
- GIVEN one phrase with `similarity_score=0.85` and one with a NULL score
- WHEN `GET /phrases?min_score=0.5` is called
- THEN only the non-null, at-or-above-threshold phrase is returned

#### Scenario: min_score out of range
- GIVEN `min_score=-0.1` or `min_score=1.5`
- WHEN `GET /phrases` is called
- THEN 422 `VALIDATION_ERROR`

#### Scenario: Filters combine with AND
- GIVEN `status`, `q`, and `min_score` all provided
- WHEN `GET /phrases` is called
- THEN only rows matching all three are returned

#### Scenario: total is filter-aware
- GIVEN a filter matching 20 of 20004 rows
- WHEN any page is requested with that filter
- THEN `data.total` is 20

#### Scenario: Cursor requires resending filters
- GIVEN a first page requested with `q=leche`
- WHEN the client requests the next page using `next_cursor` and the same `q=leche`
- THEN pagination continues correctly over the filtered set
