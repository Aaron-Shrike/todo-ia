# Delta for phrase-management

## MODIFIED Requirements

### Requirement: List phrases

The system MUST list saved phrases newest first (`created_at desc, id desc`) with their validation metadata (see api-contract), keyset-paginated by `limit`/`cursor` (default page size `PHRASES_PAGE_SIZE`, bounded by `PHRASES_LIST_LIMIT`) so the full store is reachable through repeated pages, not just the newest `PHRASES_LIST_LIMIT` items. The list MAY be narrowed by `status`, `q`, and `min_score`, combined with AND semantics when more than one is present (see api-contract for query-param shape and validation). `total` reflects the ACTIVE filter set, not the whole table. The pagination cursor carries no filter state; a client MUST resend the same filter params on every page request to keep results consistent across pages. Alternative sorting remains out of scope.
(Previously: "Search, filtering and alternative sorting are out of scope.")

#### Scenario: Newest first
- GIVEN phrases saved in order A, B, C
- WHEN the list is requested
- THEN the order is C, B, A

#### Scenario: Empty list
- GIVEN no phrases
- WHEN the list is requested
- THEN `items` is `[]`, `total` is `0`, with status 200

#### Scenario: Metadata exposed
- GIVEN a `duplicate_confirmed` phrase
- WHEN the list is requested
- THEN its item includes `validation.status`, `validation.score`, `validation.most_similar_phrase_id`, `validation.validated_at`

#### Scenario: Full store reachable via pagination
- GIVEN more phrases stored than `PHRASES_LIST_LIMIT`
- WHEN the client follows `next_cursor` across repeated requests until `has_more` is false
- THEN every stored phrase is eventually returned exactly once, newest first

#### Scenario: Filter by status narrows to matching rows
- GIVEN phrases with both `unique` and `duplicate_confirmed` status
- WHEN the list is requested with `status=duplicate_confirmed`
- THEN only `duplicate_confirmed` rows are returned, newest first

#### Scenario: Filter by text matches case-insensitively
- GIVEN a stored phrase with `normalized_text` containing "leche"
- WHEN the list is requested with `q=LECHE`
- THEN the phrase is included

#### Scenario: Text filter is not accent-insensitive
- GIVEN a stored phrase "café" and no phrase containing an unaccented "cafe"
- WHEN the list is requested with `q=cafe`
- THEN "café" is NOT returned (documented limitation, not a bug)

#### Scenario: Minimum score excludes NULL scores
- GIVEN one phrase with `similarity_score = 0.85` and one with a NULL score
- WHEN the list is requested with `min_score=0.5`
- THEN only the phrase with the non-null score at or above 0.5 is returned

#### Scenario: Filters combine with AND
- GIVEN phrases of mixed status, text and score
- WHEN the list is requested with `status`, `q`, and `min_score` together
- THEN only rows satisfying all three are returned

#### Scenario: Total reflects the active filter set
- GIVEN 20 rows matching a filter out of 20004 total rows
- WHEN the list is requested with that filter, at any page
- THEN `total` is 20, not 20004

#### Scenario: Cursor stays filter-agnostic across pages
- GIVEN a first page requested with `status=duplicate_confirmed`
- WHEN the client requests the next page with `next_cursor` and the same `status=duplicate_confirmed`
- THEN pagination continues correctly over the filtered set

### Requirement: "Beyond the brief" decision log

The repository MUST contain `docs/decisions/` with ADR-style entries, each phrased as "The brief asked for X; we decided Y because Z". At delivery the top level of `docs/decisions/` MUST contain exactly six entries of type `beyond-brief`: (1) full match list with infinite scroll instead of a single most-similar phrase (`most_similar` still returned); (2) monorepo with independently deployable services and modular hexagonal architecture instead of a simple layered app; (3) sentence-transformers now with a documented ONNX/fastembed migration path and its triggers (image size, cold start, RAM); (4) Next.js instead of plain React/Vue; (5) staged validate/re-validate progress UX; (6) saved-phrase list filters (status, text, minimum score) added to `GET /phrases`, reversing the original "filtering is out of scope" brief, documented in `docs/decisions/ADR-016-list-filters.md`. Technical ADRs (type `technical`) live in a separate `docs/decisions/technical/` directory and do NOT count toward the six. The README MUST include a summary section linking to each `beyond-brief` entry (and MAY link the technical ones). Every future deliberate deviation from the brief MUST add a `beyond-brief` entry.
(Previously: exactly five entries covering topics (1)-(5); ADR-016 did not exist.)

#### Scenario: Six entries present
- GIVEN the delivered repository
- WHEN the top level of `docs/decisions/` is listed (files only, excluding the `technical/` subdirectory)
- THEN it contains exactly six entry files of type `beyond-brief` covering topics (1)-(6), each with "brief asked", "decision" and "rationale" sections

#### Scenario: Technical ADRs are separate
- GIVEN the delivered repository
- WHEN `docs/decisions/technical/` is listed
- THEN it holds the technical ADRs, each with front-matter `type: technical`, and none of them has type `beyond-brief`

#### Scenario: README summary
- GIVEN the README
- WHEN its decision-log section is read
- THEN it lists all six entries with one-line summaries and relative links to the files

#### Scenario: ONNX path documented
- GIVEN the entry for decision (3)
- WHEN read
- THEN it names the `EmbeddingProvider` port as the swap boundary and lists image size, cold start and RAM as migration triggers

#### Scenario: ADR-016 documents the reversal and the deferred index
- GIVEN `docs/decisions/ADR-016-list-filters.md`
- WHEN read
- THEN it states that the original spec called filtering out of scope, the decision to add `status`/`q`/`min_score` filters, and the rationale, including the deferred `pg_trgm` trigger conditions

## ADDED Requirements

### Requirement: Filter status index

Migration `0002` MUST create a partial index `ON phrases (created_at DESC, id DESC) WHERE validation_status = 'duplicate_confirmed'`, with a working `downgrade`. This index serves the `status=duplicate_confirmed` filter's ordering, its cursor position, and an index-only count in one structure, given the observed skew where `duplicate_confirmed` is a small minority of rows. The `status=unique` case (the common value) continues to use the existing `phrases_created_at_id_idx` with a row filter, which stays cheap because nearly every row passes. A `pg_trgm` trigram index for the `q` filter is explicitly deferred (see ADR-016); the unfiltered and status-filtered paths are unaffected by that deferral.

#### Scenario: Partial index used for the rare status
- GIVEN the migration is applied
- WHEN `EXPLAIN` runs for `GET /phrases?status=duplicate_confirmed`
- THEN the plan uses the new partial index, not a sequential scan

#### Scenario: Migration lifecycle
- GIVEN migration `0002`
- WHEN it is applied and then downgraded
- THEN the partial index exists after upgrade and no longer exists after downgrade

#### Scenario: Unfiltered and status=unique paths unaffected
- GIVEN the migration is applied
- WHEN `GET /phrases` is called without a status filter, or with `status=unique`
- THEN the existing `phrases_created_at_id_idx` continues to serve the query
