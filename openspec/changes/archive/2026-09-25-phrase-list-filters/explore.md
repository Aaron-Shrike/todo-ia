# Exploration: phrase-list-filters

Add filtering to `GET /phrases` (the saved-phrase list): by validation status
(`unique` / `duplicate_confirmed`), by text (substring), and by similarity
score (minimum threshold). Requested live, in a support conversation, after
two other bugs were diagnosed against the same feature area.

## Current State

`GET /phrases` today: `services/api/src/app/modules/phrases/api/router.py`'s
`list_phrases` reads `limit`/`cursor` query params only, calls
`container.list_phrases(limit, cursor)` →
`services/api/src/app/modules/phrases/application/list_phrases.py`'s
`ListPhrases` (decodes the opaque `(created_at, id)` cursor, calls
`uow.repo.list_page(limit, list_cursor)` inside a read-only `UnitOfWork`) →
`PhraseRepository.list_page` (Protocol in `contracts.py`), implemented in
`adapters/pgvector_repository.py` (`list_page`/`build_list_page_query`/
`_LIST_BASE_SELECT`/`_LIST_CURSOR_PREDICATE`/`_LIST_ORDER_LIMIT`, ordering
`(created_at, id) DESC`, served by `phrases_created_at_id_idx (created_at
DESC, id DESC)` from `services/api/migrations/versions/0001_create_phrases.py`)
and mirrored in `adapters/in_memory_repository.py` (the pure-Python test
double). No filters exist anywhere in this path today.

`similarity_score` (DOUBLE PRECISION, nullable, `CHECK BETWEEN 0 AND 1`) is
NULL exactly when `most_similar_phrase_id` is NULL — enforced by migration
0001's `phrases_metadata_paired` CHECK constraint, i.e. only when the phrase
had literally no other phrase to compare against at save time (per
`phrase-management` spec's own "Below-threshold neighbor is recorded"
scenario, a `unique` row still gets a recorded low score if ANY other phrase
existed at save time — NULL is rarer than "unique status" alone).

Frontend: `apps/web/src/features/phrases/components/PhraseList.tsx` already
renders `badgeLabel`/`badgeClassName`/`scoreLabel` per item, paginates via
`client.listPhrases()` (`apps/web/src/lib/api/client.ts`'s
`ListPhrasesParams { limit?, cursor? }`) and an `IntersectionObserver`
sentinel; it already implements a `refresh()` that always restarts from page
1 (used after save and on Reintentar) — the natural place to hook "filters
changed → restart pagination." No filter UI exists today.

**Important spec finding**: `openspec/specs/phrase-management/spec.md`'s
"List phrases" requirement literally states: *"Search, filtering and
alternative sorting are out of scope."* This means the propose/spec phase
must issue a `## MODIFIED Requirements` delta against this exact requirement,
not just add new ones elsewhere — and should confirm whether this change also
needs a `docs/decisions/` "beyond-brief" entry per that same spec's
decision-log requirement (the filter ask came from a live support
conversation, outside the original brief).

## Affected Areas

- `services/api/src/app/modules/phrases/api/router.py` — `list_phrases` route
  needs new optional query params (`status`, `q`, `min_score`).
- `services/api/src/app/modules/phrases/api/schemas.py` — needs a new
  bounded-query-param helper (pattern: `query_limit`) for `min_score`, and
  validation for `status` against `ValidationStatus`'s two values.
- `services/api/src/app/modules/phrases/application/list_phrases.py` —
  `ListPhrases.__call__` needs new optional filter params threaded through to
  `list_page`.
- `services/api/src/app/modules/phrases/contracts.py` —
  `PhraseRepository.list_page` Protocol signature changes; `PhraseListPage`/
  filter dataclasses may need new fields.
- `services/api/src/app/modules/phrases/adapters/pgvector_repository.py` —
  `list_page`, `build_list_page_query`, and `count_all()` (must become
  filter-aware — see Risks) need new conditional WHERE fragments, following
  the existing `build_list_page_query(*, has_cursor)` /
  `build_find_matches_query(*, has_cursor)` idiom already in this file.
- `services/api/src/app/modules/phrases/adapters/in_memory_repository.py` —
  `InMemoryPhraseRepository.list_page` must mirror the same filter semantics
  in Python (cross-checked by `tests/contract_suite/repository_contract.py`
  — read before touching `list_page`'s signature).
- `services/api/src/app/modules/phrases/container.py` /
  `services/api/src/app/platform/settings.py` — if a new setting is needed
  (e.g. reusing `phrase_max_length` for the `q` param's cap rather than
  inventing one).
- `services/api/migrations/versions/` — a possible new migration for
  `pg_trgm`/`unaccent` extension and/or a composite/partial index (pending
  live EXPLAIN — see Findings below, now filled in).
- `openspec/specs/phrase-management/spec.md` — "List phrases" requirement
  needs a `MODIFIED` delta (currently says filtering is out of scope).
- `openspec/specs/api-contract/spec.md` — "GET /phrases" requirement needs
  new query params documented.
- `openspec/specs/phrase-ui/spec.md` — needs new filter-UI requirements (no
  filter UI exists today).
- `apps/web/src/features/phrases/components/PhraseList.tsx` and
  `apps/web/src/lib/api/client.ts` — `ListPhrasesParams` needs `status`/`q`/
  `min_score`, and a filter-changed path needs to restart pagination (reuse
  existing `refresh()`).

## Constraints / Real Findings

1. **Index & keyset interaction**: the only index serving `list_page`'s
   ordering is `phrases_created_at_id_idx (created_at DESC, id DESC)`. Adding
   WHERE predicates alongside the existing
   `(created_at, id) < (:cursor_created_at, :cursor_id)` cursor predicate is
   correctness-safe — Postgres can still Index Scan on
   `phrases_created_at_id_idx` and Filter the extra predicates row-by-row
   while honoring `ORDER BY ... LIMIT :limit+1` with early termination.
   Efficiency depends on selectivity.

   **Live-verified against the real ~20k-row table** (orchestrator ran this
   after the exploration sub-agent reported it had no Bash tool available):
   see `explore-db-findings.md` in this same directory for the full
   `EXPLAIN (ANALYZE, BUFFERS)` output. Summary: status-only filtering
   Index-Scans `phrases_created_at_id_idx` fine at this scale (Filter
   condition, no separate index needed yet); an unindexed `normalized_text
   ILIKE '%...%'` filter combined with a narrow first page forces a much
   larger scan than the unfiltered query for a rare substring — confirms the
   sub-agent's structural concern was real, not theoretical. Decision on
   `pg_trgm` deferred to design, informed by these numbers.

2. **NULL score semantics**: confirmed — `similarity_score >= :min_score`
   naturally excludes NULL-score rows under standard SQL 3-valued logic
   (`NULL >= x` is UNKNOWN). This matches the intuitive "only show phrases
   with a recorded score at or above the threshold" UX; needs documenting in
   the spec, not special-casing in code.

3. **Cursor + filter interaction**: `GET /phrases`'s cursor carries only
   `(created_at, id)` — no text/threshold binding, unlike
   `POST /phrases/matches`'s cursor (confirmed in `contracts.py`'s
   `ListCursor` and the api-contract spec). Two real options: (a) keep the
   cursor filter-agnostic — client resends filter query params on every page
   request, server does not bind/validate them into the cursor; (b) bind the
   active filter set into the cursor like `matches` does with
   text/threshold, rejecting a mismatched replay with `400 INVALID_CURSOR`.
   (a) is far simpler and matches this endpoint's existing "cursor is just a
   position pointer" design; (b) adds meaningful complexity that seems
   disproportionate to a "simple three-criteria filter" ask. **Recommend
   (a)**, with the UI rule "changing any filter always restarts pagination
   from page 1" — reusing the `refresh()` pattern already implemented in
   `PhraseList.tsx` for post-save refresh and Reintentar.

4. **Status single- vs multi-select**: only 2 possible values exist
   (`unique`, `duplicate_confirmed`). Multi-select is barely meaningful with
   2 values (selecting both ≈ no filter). **Recommend single-select**
   (`?status=unique|duplicate_confirmed`, optional/nullable = no filter).

5. **Text search column & case/accent-insensitivity**: `normalized_text`
   (casefolded, NFC, whitespace-collapsed — `domain/normalization.py`'s
   `comparison_form`) gives case-insensitivity for free by reusing the
   existing column, but is **NOT accent-stripped** (casefold preserves
   diacritics) — a query for "cafe" would NOT match stored "café" via
   `normalized_text`. True accent-insensitivity needs either Postgres's
   `unaccent` extension (not installed — migration 0001 only enables
   `vector`) applied inside the filter predicate, or a new stored
   accent-folded column. The product owner's phrasing didn't specify
   accent-insensitivity explicitly. **Open question for propose** —
   recommend defaulting to case-insensitive-only against `normalized_text`
   (zero schema change) unless the product owner confirms accents matter.

6. **Score filter shape**: the product owner's own phrasing ("at or above
   some threshold") is explicitly min-only. **Recommend `min_score` only**
   (`>=`), no max/range — can be added later, additively, if ever requested.

7. **Existing conventions to follow**:
   - `services/api/src/app/modules/phrases/api/schemas.py`'s
     `query_limit(max_value)` is the established pattern for lenient
     (non-strict) query-param bounds — a new `min_score` should get an
     analogous `Annotated[float, Field(ge=0, le=1)]` helper; `status` should
     validate against `ValidationStatus`'s literal values (422 on anything
     else, not silent ignore).
   - Settings-driven bounds are injected via constructor/builder kwargs
     (`build_phrases_router(*, ..., phrases_list_limit, phrases_page_size)`),
     never read ad hoc inside a route body.
   - `PhraseRepository` is a Protocol implemented twice and cross-checked by
     `tests/contract_suite/repository_contract.py`; any `list_page` signature
     change must be mirrored in both `pgvector_repository.py` and
     `in_memory_repository.py`.
   - Invalid filter values should map to the existing `422 VALIDATION_ERROR`
     convention (same as `limit` bound violations today), not a new error
     code.

## Approaches

1. **Extend `GET /phrases` with new optional query params** (`status`, `q`,
   `min_score`) — additive, same shape as how `limit` was added.
   - Pros: single endpoint, no client routing change, reuses existing keyset
     cursor machinery unchanged; smallest surface change; filter-agnostic
     cursor design (finding 3) needs zero cursor-codec change.
   - Cons: `list_page`'s Protocol signature grows across 2 adapters;
     `count_all()` must become filter-aware (see below) or the UI's
     `{loaded}/{total}` counter (already implemented via `counterLabel`) will
     show the wrong denominator.
   - Effort: Medium.

2. **New dedicated endpoint** (e.g. `POST /phrases/search`) leaving
   `GET /phrases` untouched.
   - Pros: existing endpoint's contract stays frozen; a POST body could
     sidestep query-string encoding for `q`.
   - Cons: duplicates ordering/pagination/`total` logic that IS
     `GET /phrases`'s own job, just filtered; the product owner explicitly
     framed this as "add filtering to **the saved-phrase list**" (this list,
     not a new one); two client call sites to keep in sync in `apps/web`;
     `matches`/`validate`'s two-endpoint split exists for a different reason
     (stateless verdict vs. continuation) that doesn't apply here.
   - Effort: Medium-High (all of #1's work plus a new contract section and
     duplicated pagination/total logic to maintain forever).

3. **SQL WHERE composition strategy** (sub-decision under #1):
   conditional-fragment building (extend the existing
   `build_list_page_query(*, has_cursor: bool)` idiom — already the pattern
   used one file up by `build_find_matches_query(*, has_cursor)`) vs.
   always-present `(:param IS NULL OR col = :param)`-style optional
   predicates.
   - Conditional-fragment building matches this codebase's established idiom
     exactly and keeps each generated query's plan clean/explainable (the
     file's own docstring convention: "Exposed so a plan/EXPLAIN test runs
     the real query, not a copy"). **Recommended.**
   - Always-present optional predicates are fewer branches but historically
     riskier for planner behavior and breaks the file's stated EXPLAIN-guard
     -test convention.

### `total`/`count_all()` filter-awareness

`list_page` currently always calls `self.count_all()` unconditionally
(`SELECT count(*) FROM phrases`). Once filters exist, `total` MUST reflect
the filtered count — mirroring `count_matches`'s existing precedent (it
applies the SAME predicate as `find_matches`, independent of pagination) —
otherwise the UI's `{loaded}/{total}` counter would show the full unfiltered
store size while `items` shows filtered rows. This needs a filter-aware
`count_all` variant or a query sharing `list_page`'s WHERE fragments.

## Recommendation

Approach 1 (extend `GET /phrases`) with the conditional-fragment SQL builder
and a filter-aware total. Query params: `status` (single, optional), `q`
(optional, case-insensitive substring against `normalized_text`,
accent-insensitivity deferred pending product confirmation), `min_score`
(optional float [0,1], `>=`). Filters compose with AND semantics unless
propose decides otherwise. Cursor stays filter-agnostic; client restarts
pagination on any filter change (reusing the existing `refresh()` pattern).

## Risks

- `phrase-management` spec's "List phrases" requirement currently says
  filtering is explicitly out of scope — the spec phase needs a `MODIFIED`,
  not `ADDED`, delta, and should confirm whether a `docs/decisions/`
  beyond-brief entry is also needed.
- `count_all()`/total must become filter-aware or the UI counter will
  silently show the wrong denominator when a filter is active.
- Both `PhraseRepository` adapters must be extended in lockstep, exercised by
  `tests/contract_suite/repository_contract.py`.
- Text substring filtering has no supporting index today — live-verified
  (see `explore-db-findings.md`): a rare substring near an old page scans a
  much larger fraction of the table than the unfiltered query. `pg_trgm` vs.
  "accept the cost at current scale" is a real design decision, not
  theoretical.

## Open Questions for Propose

1. Accent-insensitive text search: required now, or deferred (case-insensitive only)?
2. Status filter: confirm single-select suffices (only 2 values today).
3. Score filter: confirm min-only (`>=`) suffices; no max/range needed.
4. Cursor/filter interaction: confirm "cursor is filter-agnostic, client resets pagination on filter change" is acceptable vs. binding filters into the cursor like `matches`.
5. Does this change need a `docs/decisions/` "beyond-brief" entry?
6. `pg_trgm` now vs. deferred — see live EXPLAIN numbers in `explore-db-findings.md`.

## Ready for Proposal

Yes — the endpoint-shape decision (extend `GET /phrases`, approach 1) is
clear, and the live EXPLAIN/index check (originally blocked by the
exploration sub-agent's lack of Bash access) has since been run directly
against the real database by the orchestrator. Open questions 1-5 above
should be resolved in `sdd-propose`.
