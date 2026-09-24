# Phrase Management Specification

Capability: `phrase-management` (new). Covers text normalization, length rules, persistence of phrases and validation metadata, listing, and the decision-log documentation deliverable.

Config: `PHRASE_MAX_LENGTH` (default 280).

## ADDED Requirements

### Requirement: Text normalization

The system MUST normalize phrase text before validation, embedding, and storage: apply these steps in this order: (1) map whitespace control characters (`\t`, `\n`, `\r`, `\v`, `\f`, U+001C..U+001F, U+0085) to a single space, so they separate words instead of gluing them; (2) strip the invisible characters U+200B, U+2060 and U+FEFF and every remaining control character (Unicode category Cc); (3) apply Unicode NFC (after stripping, so composition is not blocked by a removed character); (4) trim leading and trailing whitespace and any leading or trailing U+200C/U+200D. U+200D (ZWJ) and U+200C (ZWNJ) are NOT stripped inside the text, because they are meaningful in emoji sequences and in Persian/Indic scripts. Two forms are derived: the display form (the result of steps 1-4; original casing and internal whitespace preserved, each mapped control becoming one space) is what is stored in `text` and shown; the comparison form (the display form Unicode-casefolded, then NFC again because casefolding can de-normalize, then internal whitespace collapsed to a single space) is what is embedded and is stored in `normalized_text`. Both forms MUST be idempotent. Accepted cost: embedding the casefolded form loses some casing signal; this is measured during threshold calibration. Emoji, accents and RTL text MUST be preserved and MUST NOT cause errors.

#### Scenario: Trim and NFC
- GIVEN the input `"  Café "` (decomposed accent)
- WHEN it is normalized
- THEN the result is `"Café"` (precomposed, no surrounding spaces)

#### Scenario: Zero-width and control characters stripped
- GIVEN the input `"Buy​ milk\u0007"`
- WHEN it is normalized
- THEN the result is `"Buy milk"`

#### Scenario: Whitespace controls separate words
- GIVEN the input `"Buy\tmilk\nnow"`
- WHEN it is normalized
- THEN the display form is `"Buy milk now"` (each control became a space; nothing was glued to `"Buymilknow"`)

#### Scenario: ZWJ and ZWNJ are preserved inside text
- GIVEN the input `"👨‍👩‍👧"` (family emoji sequence) and a Persian word containing U+200C
- WHEN each is normalized
- THEN the joiners are preserved and the strings are otherwise unchanged; a text made only of U+200C/U+200D is empty after normalization

#### Scenario: Comparison form re-normalizes after casefold
- GIVEN a string whose casefold output is not NFC
- WHEN the comparison form is derived
- THEN the result is NFC and re-deriving it yields the same string

#### Scenario: Emoji and RTL preserved
- GIVEN the inputs `"Comprar leche 🥛"` and `"شراء الحليب"`
- WHEN each is normalized, validated and saved
- THEN neither raises an error and both are stored unchanged apart from trim/NFC/stripping

#### Scenario: Normalization is idempotent
- GIVEN any normalized string s
- WHEN it is normalized again
- THEN the result equals s

### Requirement: Empty text rejection

Text that is empty, or empty after normalization (whitespace-only, or only zero-width/control characters), MUST be rejected with `422 VALIDATION_ERROR` and MUST NOT be embedded or persisted.

#### Scenario: Empty string
- GIVEN the text `""`
- WHEN it is submitted to validate or save
- THEN the response is 422 `VALIDATION_ERROR` with `details` naming field `text`, and the embedding provider is never called

#### Scenario: Whitespace and invisible-only
- GIVEN the text `"   \t\n​"`
- WHEN it is submitted
- THEN the outcome is the same as the empty string case

#### Scenario: Missing or non-string field
- GIVEN a body without `text`, or with `text: 42`
- WHEN it is submitted
- THEN the response is 422 `VALIDATION_ERROR`

### Requirement: Maximum length

The normalized text length (in Unicode code points) MUST NOT exceed `PHRASE_MAX_LENGTH` (default 280). Longer text MUST be rejected with `422 VALIDATION_ERROR` before embedding, with `details.max_length` stating the limit. The limit is measured AFTER normalization. Independently, raw input longer than 4 x `PHRASE_MAX_LENGTH` code points is rejected BEFORE normalization with the same `too_long` error (see api-contract), so normalization cost is bounded. `PHRASE_MAX_LENGTH` MUST be a positive integer; an invalid value MUST fail fast at startup.

#### Scenario: Exactly at limit
- GIVEN normalized text of exactly 280 code points
- WHEN validated or saved
- THEN it is accepted

#### Scenario: One over limit
- GIVEN normalized text of 281 code points
- WHEN validated or saved
- THEN the response is 422 `VALIDATION_ERROR` with `details.max_length == 280` and no embedding call occurs

#### Scenario: Padding does not count
- GIVEN 280 characters of content plus 20 trailing spaces
- WHEN validated
- THEN it is accepted (length measured after trim)

#### Scenario: Raw input cap before normalization
- GIVEN `PHRASE_MAX_LENGTH=280` and 1121 raw code points (mostly padding or invisible characters)
- WHEN validated or saved
- THEN 422 `too_long` with `details.max_length == 280`, and neither normalization nor embedding ran

#### Scenario: Configurable limit
- GIVEN `PHRASE_MAX_LENGTH=50`
- WHEN a 51-code-point phrase is submitted
- THEN it is rejected with `details.max_length == 50`

#### Scenario: Invalid limit config
- GIVEN `PHRASE_MAX_LENGTH=0` or `abc`
- WHEN the backend starts
- THEN startup fails with a clear configuration error

### Requirement: Phrase persistence with validation metadata

Every persisted phrase MUST carry: `id`, `text` (display form), `normalized_text` (case-folded, whitespace-collapsed comparison form), `embedding`, `created_at`, and validation metadata: `similarity_score` (nullable, 4 decimals, always within [0, 1] because scores are clamped), `most_similar_phrase_id` (nullable FK to phrases), `validation_status` (`unique` | `duplicate_confirmed`), `validated_at` (timestamp of the server-side validation performed during save). The database MUST enforce a PARTIAL unique index on `normalized_text` restricted to rows with `validation_status = 'unique'` (see requirement "Database-level uniqueness of unconfirmed phrases"). The database MUST NOT have a plain (non-partial) unique constraint or index on `normalized_text`.

#### Scenario: Unique phrase metadata
- GIVEN an empty store
- WHEN "Comprar leche" is saved
- THEN the row has `validation_status = unique`, `similarity_score = NULL`, `most_similar_phrase_id = NULL`, and a non-null `validated_at`

#### Scenario: Below-threshold neighbor is recorded
- GIVEN a stored phrase P and a new phrase whose best score against P is 0.55 (threshold 0.80)
- WHEN the new phrase is saved
- THEN status is `unique`, `similarity_score = 0.55`, `most_similar_phrase_id = P.id`

#### Scenario: Confirmed duplicate metadata
- GIVEN a stored phrase P and a new phrase with best score 0.92 against P
- WHEN it is saved with `confirm_duplicate: true`
- THEN status is `duplicate_confirmed`, `similarity_score = 0.92`, `most_similar_phrase_id = P.id`

#### Scenario: Metadata is immutable history
- GIVEN a stored phrase recorded at threshold 0.80
- WHEN the threshold is later changed to 0.95 and the service restarts
- THEN the stored row's score, status and most-similar id are unchanged

#### Scenario: No plain unique index
- GIVEN the applied migrations
- WHEN the schema is inspected
- THEN the only unique index involving `normalized_text` is partial with predicate `validation_status = 'unique'`, and no unconditional unique constraint or index exists on it

#### Scenario: Embedding dimension mismatch fails fast
- GIVEN the configured model produces vectors whose dimension differs from the `embedding` column dimension
- WHEN the backend starts
- THEN startup fails with a clear error and no request is served

### Requirement: Database-level uniqueness of unconfirmed phrases

The database MUST guarantee that no two rows with `validation_status = 'unique'` share the same `normalized_text`, via a partial unique index (`CREATE UNIQUE INDEX ... ON phrases (normalized_text) WHERE validation_status = 'unique'`) created by the schema migration and removed by its downgrade. Rows with `validation_status = 'duplicate_confirmed'` MUST be outside the index, so confirmed duplicates with identical text remain allowed. The index exists for integrity, not performance. It MUST NOT be presented as protection against semantic (non-identical) near-duplicates, which remain protected only by the advisory lock and application logic (see duplicate-confirmation, Concurrency control).

#### Scenario: Second unique row with the same text is rejected by the database
- GIVEN a stored row with `validation_status = unique` and `normalized_text = "comprar leche"`
- WHEN a second row with `validation_status = unique` and the same `normalized_text` is inserted directly, bypassing the application check
- THEN the database rejects the insert with a unique violation

#### Scenario: Confirmed duplicate with the same text is accepted by the database
- GIVEN a stored row with `validation_status = unique` and `normalized_text = "comprar leche"`
- WHEN a row with `validation_status = duplicate_confirmed`, the same `normalized_text` and valid metadata is inserted directly
- THEN the insert succeeds and both rows coexist

#### Scenario: Different text is unaffected
- GIVEN a stored `unique` row with `normalized_text = "comprar leche"`
- WHEN a `unique` row with `normalized_text = "comprar pan"` is inserted
- THEN the insert succeeds

#### Scenario: Migration lifecycle
- GIVEN the schema migration
- WHEN it is applied and then downgraded
- THEN the partial unique index exists after upgrade and no longer exists after downgrade

### Requirement: List phrases

The system MUST list saved phrases newest first (`created_at desc, id desc`) with their validation metadata (see api-contract), keyset-paginated by `limit`/`cursor` (default page size `PHRASES_PAGE_SIZE`, bounded by `PHRASES_LIST_LIMIT`) so the full store is reachable through repeated pages, not just the newest `PHRASES_LIST_LIMIT` items. Search, filtering and alternative sorting are out of scope.

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

### Requirement: Migrations

Schema MUST be created by Alembic migrations written as raw SQL. The first migration MUST enable the `vector` extension. Every migration MUST provide a working `downgrade`.

#### Scenario: Upgrade from empty database
- GIVEN an empty Postgres with pgvector available
- WHEN `alembic upgrade head` runs
- THEN the `phrases` table and `vector` extension exist

#### Scenario: Downgrade to base
- GIVEN a migrated database
- WHEN `alembic downgrade base` runs
- THEN the `phrases` table is dropped and then the `vector` extension is dropped without error

### Requirement: "Beyond the brief" decision log

The repository MUST contain `docs/decisions/` with ADR-style entries, each phrased as "The brief asked for X; we decided Y because Z". At delivery the top level of `docs/decisions/` MUST contain exactly five entries of type `beyond-brief`: (1) full match list with infinite scroll instead of a single most-similar phrase (`most_similar` still returned); (2) monorepo with independently deployable services and modular hexagonal architecture instead of a simple layered app; (3) sentence-transformers now with a documented ONNX/fastembed migration path and its triggers (image size, cold start, RAM); (4) Next.js instead of plain React/Vue; (5) staged validate/re-validate progress UX. Technical ADRs (type `technical`) live in a separate `docs/decisions/technical/` directory and do NOT count toward the five. The README MUST include a summary section linking to each `beyond-brief` entry (and MAY link the technical ones). Every future deliberate deviation from the brief MUST add a `beyond-brief` entry.

#### Scenario: Five entries present
- GIVEN the delivered repository
- WHEN the top level of `docs/decisions/` is listed (files only, excluding the `technical/` subdirectory)
- THEN it contains exactly five entry files of type `beyond-brief` covering topics (1)-(5), each with "brief asked", "decision" and "rationale" sections

#### Scenario: Technical ADRs are separate
- GIVEN the delivered repository
- WHEN `docs/decisions/technical/` is listed
- THEN it holds the technical ADRs, each with front-matter `type: technical`, and none of them has type `beyond-brief`

#### Scenario: README summary
- GIVEN the README
- WHEN its decision-log section is read
- THEN it lists all five entries with one-line summaries and relative links to the files

#### Scenario: ONNX path documented
- GIVEN the entry for decision (3)
- WHEN read
- THEN it names the `EmbeddingProvider` port as the swap boundary and lists image size, cold start and RAM as migration triggers
