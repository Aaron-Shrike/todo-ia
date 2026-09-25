# Proposal: Saved-Phrase List Filters

## Intent

**Business problem.** Once the list holds thousands of phrases (20,004 today), the curator cannot answer basic questions such as "which phrases did someone save despite the duplicate warning?", "do we already have something about 'leche'?", or "what was saved close to the threshold?" The only option is scrolling newest-first. The request came up during a live support conversation.

**Success.** On the saved-phrase list, the user can narrow results by status, by text, and by minimum score, in any combination. The counter (`{loaded}/{total}`) stays accurate, and infinite scroll still reaches the last matching phrase.

**Scope change, stated explicitly.** `phrase-management` "List phrases" currently says *"Search, filtering and alternative sorting are out of scope."* This change deliberately reverses that for filtering. Search ranking and alternative sorting stay out of scope.

## Scope

### In Scope

- `GET /phrases` gets three optional, combinable query params (AND semantics). This extends the existing endpoint; no new endpoint is added:
  - `status`: single value, `unique` or `duplicate_confirmed`. Any other value returns 422.
  - `q`: case-insensitive substring match against `normalized_text`. The server converts `q` to the same comparison form as `normalized_text` and escapes the LIKE wildcards `%`, `_` and `\`. Length is capped by `PHRASE_MAX_LENGTH`. A blank `q` counts as absent.
  - `min_score`: float in [0,1], matching `similarity_score >= min_score`. Rows with a NULL score are excluded, per standard SQL semantics, and this is documented.
- Invalid values use the existing `422 VALIDATION_ERROR` (same as `limit` today). No new error codes.
- **`total` counts the filtered set**: the count applies the same WHERE fragments as the page query and ignores pagination, following the `count_matches` precedent.
- **Cursor unchanged.** It still encodes only `(created_at, id)` and does not depend on filters. The client re-sends the filters with every page request. Changing any filter restarts the list from page 1 through the existing `refresh()` in `PhraseList.tsx`.
- `PhraseRepository.list_page` / count updated in both adapters in lockstep. `ListPageContractSuite` gets filter cases.
- **Migration `0002`**: a partial index `ON phrases (created_at DESC, id DESC) WHERE validation_status = 'duplicate_confirmed'`, with a working downgrade.
- Filter controls in the UI (status select, text input, minimum-score input), plus an empty state for "no results for these filters". Copy is in neutral Spanish.
- A new `beyond-brief` entry, `docs/decisions/ADR-016-list-filters.md`.

### Out of Scope

- **Accent-insensitive search** (`unaccent` or an accent-folded column). This is a known limitation, not a bug: `cafe` does NOT match `café`.
- **`pg_trgm` / GIN trigram index** for `q`. Deferred; see Approach.
- Max score or score ranges; selecting more than one status; sorting other than newest-first; relevance ranking.
- Tying the active filters to the cursor (the way `matches` does); saving filters in the URL.
- Changes to `POST /phrases/validate`, `/matches` or the save flow.

## Capabilities

### New Capabilities

None.

### Modified Capabilities

- `phrase-management`: **MODIFIED** "List phrases" (filters, filter-aware `total`, filter-independent cursor, removal of the out-of-scope sentence). **MODIFIED** "Beyond the brief decision log": exactly five entries become exactly six. **ADDED** a requirement for the filter index migration.
- `api-contract`: `GET /phrases` query params, validation rules, 422 mapping.
- `phrase-ui`: filter controls, reset to page 1 when filters change, filtered counter, filtered empty state.

## Approach

- Extend the existing `build_list_page_query(*, has_cursor)` pattern with conditional WHERE fragments (`has_status`, `has_q`, `has_min_score`), so each variant stays a real query that EXPLAIN can inspect. Always-present `(:p IS NULL OR ...)` predicates are rejected because they break the file's EXPLAIN-guard convention.
- `q` uses `LIKE` on the comparison form, not `ILIKE`. Both sides are already casefolded, so Postgres and the in-memory adapter's Python `in` behave identically. `ILIKE`'s `lower()` differs from `casefold()`, for example on `ß`.
- **Status index: partial, not plain btree.** With 20,001 `unique` rows and 3 `duplicate_confirmed`, the useful filter is the rare value. A partial index keyed on `(created_at DESC, id DESC)` is tiny. It serves the rare filter's order, its cursor and an index-only count in one structure. A plain btree on `validation_status` has almost no selectivity for `unique`, and for `duplicate_confirmed` it still needs a separate sort. `status=unique` keeps using `phrases_created_at_id_idx` with an early-terminating Filter, which is cheap because nearly every row passes.
- **`pg_trgm`: deferred.** Measured cost is 32 ms at 20k rows, which users won't notice. Adding it needs a new extension, a GIN index that slows every save, and it does not help queries under 3 characters. Revisit this if the list grows past ~100k rows or filtered p95 exceeds 100 ms. Record the trigger in the ADR.

## Affected Areas

| Area | Impact | Description |
|---|---|---|
| `services/api/src/app/modules/phrases/api/{router,schemas}.py` | Modified | Query params, `min_score`/`status` validators |
| `services/api/src/app/modules/phrases/application/list_phrases.py` | Modified | Thread filters |
| `services/api/src/app/modules/phrases/contracts.py` | Modified | Filter value object, `list_page` signature |
| `services/api/src/app/modules/phrases/adapters/{pgvector,in_memory}_repository.py` | Modified | Filtered page and count |
| `services/api/migrations/versions/0002_*.py` | New | Partial status index |
| `services/api/tests/contract_suite/repository_contract.py`, `tests/unit/test_decision_log.py` | Modified | Filter cases; 5 becomes 6 |
| `apps/web/src/lib/api/client.ts`, `features/phrases/components/PhraseList.tsx`, `i18n/copy.es.ts` | Modified | Params, filter UI, copy |
| `docs/decisions/ADR-016-list-filters.md`, `README.md` | New/Modified | Beyond-brief entry and summary link |

## Risks

| Risk | Likelihood | Mitigation |
|---|---|---|
| Diff exceeds the 400-line budget (backend, migration, UI, specs, tests) | High | `sdd-tasks` forecasts it; `ask-on-risk` decides the split |
| Adapters drift on `q` semantics | Med | Shared contract-suite cases, including wildcard characters and casefold edge cases |
| Users expect accent-insensitive search | Med | Documented limitation; can be added later without breaking anything |
| The skew reverses (duplicates become common) | Low | Partial index is cheap to drop or replace; noted in ADR |
| Uncommitted `phrase-ui`/`PhraseForm`/`copy.es` changes on `develop` | Med | Commit or stash them before apply to avoid spec and copy conflicts |

## Rollback Plan

Revert the change's PR(s). Migration `0002` downgrade drops the partial index; no data changes. The new params are optional, so older clients keep working throughout.

## Dependencies

None. No new extension and no new library.

## Success Criteria

- [ ] Each filter, and every combination, returns only matching rows, newest first, reachable to the end via the cursor.
- [ ] `total` equals the filtered row count on every page.
- [ ] Invalid `status` / `min_score` / over-length `q` return 422 `VALIDATION_ERROR`.
- [ ] `q` containing `%` or `_` is matched literally.
- [ ] `EXPLAIN` for `status=duplicate_confirmed` uses the partial index (no Seq Scan).
- [ ] Both adapters pass the same filter contract cases.
- [ ] UI changes restart pagination and show the filtered counter and empty state.
- [ ] Six `beyond-brief` ADRs; the decision-log test is updated.

## Proposal question round

The orchestrator settled the endpoint and query-param decisions. These questions still need the user's review:

1. **Who and when**: is this mainly the curator auditing confirmed duplicates, or authors checking "do we already have this?" before typing? This decides whether `q` or `status` is the prominent control.
2. **Text input behavior**: should the list filter while typing (debounced) or only when the user explicitly applies it?
3. **Empty result**: when filters match nothing, should the UI offer a one-click "clear filters"?
4. **Decision log**: do you agree this counts as a `beyond-brief` deviation (the precedent is ADR-005, an additive UX), which raises the "exactly five" rule to six?

Assumptions until answered: `status` first, `q` debounced, a clear-filters link, and ADR-016 as beyond-brief.
