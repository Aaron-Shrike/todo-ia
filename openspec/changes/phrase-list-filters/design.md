# Design: Saved-Phrase List Filters

Implements `proposal.md`'s 10 settled decisions and the user's later UX
decision: live filters, with `q` debounced. Evidence is in
`explore-db-findings.md` (20,001 `unique` / 3 `duplicate_confirmed`; a filtered
first page today costs Seq Scan + Sort, 5007 buffers, 10-32 ms).

## Technical Approach

`GET /phrases` gets three optional query params: `status`, `q` and
`min_score`. They are validated at the schema layer, normalized in
`ListPhrases`, and passed to the repository as one frozen value object,
`ListFilters`. The pgvector adapter extends its conditional-fragment builder
(`build_list_page_query`) and adds a sibling `build_count_list_query` that
shares the same WHERE fragments. This is the same pairing as
`find_matches`/`count_matches`. The in-memory adapter applies the same
semantics in Python, and the shared contract suite proves they agree.
Migration `0002` adds one partial index. The cursor codec does not change.

## Architecture Decisions

| # | Decision | Rejected alternative | Rationale |
|---|---|---|---|
| D1 | `ListFilters` dataclass in `contracts.py`, passed as keyword-only `filters: ListFilters = NO_FILTERS` | Three loose kwargs on `list_page` | One type crosses application → repo; the default keeps every existing call site and test valid. A module constant, not `ListFilters()`, avoids ruff B008 |
| D2 | `q` is normalized in the **application** layer: `comparison_form(display_form(q))`, and blank becomes `None` | Normalizing in the router | `phrases.api` must not import `domain` (import-linter). `comparison_form` takes a display form, so `display_form` goes first, exactly as `normalize_and_check_length` does |
| D3 | LIKE escaping lives in the **pgvector adapter** (`_contains_pattern`) | Escaping in the application layer | Escaping is SQL syntax. The in-memory adapter uses Python `in` on the raw term and must never see `\%` |
| D4 | The status value is **inlined as a SQL literal** from the closed `ValidationStatus` enum (`status.value`), not bound as `:status` | `validation_status = :status` | psycopg3 auto-prepares after 5 executions, and Postgres may then pick a **generic plan**. A generic plan cannot prove `$1 = 'duplicate_confirmed'`, so it would silently stop using the partial index. The value comes only from enum members, so it is injection-safe by construction |
| D5 | New `count_filtered(filters)` on the Protocol. `count_all()` stays, implemented as `count_filtered(NO_FILTERS)` | Replacing `count_all` | This mirrors `count_matches` and keeps the existing contract and integration tests unchanged |
| D6 | Builder signature `build_list_page_query(*, has_cursor, status=None, has_text=False, has_min_score=False)` | `(:p IS NULL OR …)` predicates | Proposal ADR. Each variant is a real query that EXPLAIN can inspect |
| D7 | Plain `CREATE INDEX` (not `CONCURRENTLY`) in `0002` | `CONCURRENTLY` with `autocommit_block()` | Alembic runs each migration in a transaction. The build is a single ~20k-row scan (ms), and the index holds 3 rows |
| D8 | No `pg_trgm` | GIN trigram index | Deferred per the proposal's ADR (32 ms at 20k rows; revisit past ~100k rows or filtered p95 > 100 ms). Recorded in ADR-016 |

## SQL (pgvector_repository.py)

```python
_LIST_CURSOR_PREDICATE = "(created_at, id) < (:cursor_created_at, :cursor_id)"   # WHERE moved out
_LIST_TEXT_PREDICATE = r"normalized_text LIKE :text_pattern ESCAPE '\'"
_LIST_MIN_SCORE_PREDICATE = "similarity_score >= :min_score"

def _status_predicate(status: ValidationStatus) -> str:
    return f"validation_status = '{status.value}'"  # D4: enum-only literal

def _list_where(*, has_cursor: bool, status: ValidationStatus | None,
                has_text: bool, has_min_score: bool) -> str:
    parts = [
        *([_status_predicate(status)] if status is not None else []),
        *([_LIST_TEXT_PREDICATE] if has_text else []),
        *([_LIST_MIN_SCORE_PREDICATE] if has_min_score else []),
        *([_LIST_CURSOR_PREDICATE] if has_cursor else []),
    ]
    return ("WHERE " + "\n  AND ".join(parts) + "\n") if parts else ""

def build_list_page_query(*, has_cursor: bool, status: ValidationStatus | None = None,
                          has_text: bool = False, has_min_score: bool = False) -> str:
    """Exposed so a plan/EXPLAIN test runs the real query, not a copy."""
    return _LIST_BASE_SELECT + _list_where(has_cursor=has_cursor, status=status,
        has_text=has_text, has_min_score=has_min_score) + _LIST_ORDER_LIMIT

def build_count_list_query(*, status=None, has_text=False, has_min_score=False) -> str:
    """Same WHERE fragments as `build_list_page_query`, minus cursor/order/limit."""
    return "SELECT count(*) FROM phrases\n" + _list_where(has_cursor=False, ...)

def _contains_pattern(term: str) -> str:
    escaped = term.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")
    return f"%{escaped}%"
```

Here is the rendered query for all filters plus a cursor:

```sql
SELECT id, text, normalized_text, embedding::text AS embedding, similarity_score,
       most_similar_phrase_id, validation_status, validated_at, created_at
FROM phrases
WHERE validation_status = 'duplicate_confirmed'
  AND normalized_text LIKE :text_pattern ESCAPE '\'
  AND similarity_score >= :min_score
  AND (created_at, id) < (:cursor_created_at, :cursor_id)
ORDER BY created_at DESC, id DESC
LIMIT :limit + 1
```

With no filters and no cursor, the output is byte-identical to today's query,
so there is no plan regression on the default path. `list_page` sets
`text_pattern` and `min_score` only when they are present. It then runs
`count_filtered(filters)` in place of `count_all()`. The count and the page
run as two statements in the same READ COMMITTED read-only UoW, which is
unchanged from today.

**Semantics parity (the in-memory `_passes(row, f)`):**
- status: `row.validation_status is f.status`
- text: `f.text in row.normalized_text`. Both sides are NFC and casefolded, and
  Postgres `LIKE` under a deterministic collation compares code point by code
  point, so the result equals Python substring matching. This is why `LIKE`
  is used and not `ILIKE`: `ILIKE` uses `lower()`, which does not fold `ß` to
  `ss`.
- min_score: `row.similarity_score is not None and row.similarity_score >= f.min_score`.
  This matches SQL three-valued logic exactly (`NULL >= x` is UNKNOWN, so the
  row is excluded). Both sides are IEEE doubles.

**Plans:** `status=duplicate_confirmed` uses the partial index for ordering,
the cursor and an index-only count. `status=unique` early-terminates on
`phrases_created_at_id_idx`. Its count is about the same cost as today's
`count(*)`. `q` and `min_score` on their own are Filters on the existing index,
and are accepted per D8.

## Migration `0002_list_filter_status_index.py`

```python
revision = "0002"; down_revision = "0001"
def upgrade() -> None:
    op.execute("CREATE INDEX phrases_duplicate_confirmed_created_at_id_idx "
               "ON phrases (created_at DESC, id DESC) "
               "WHERE validation_status = 'duplicate_confirmed';")
def downgrade() -> None:
    op.execute("DROP INDEX IF EXISTS phrases_duplicate_confirmed_created_at_id_idx;")
```

## Interfaces / Contracts

```python
# contracts.py
@dataclass(frozen=True)
class ListFilters:
    status: ValidationStatus | None = None
    text: str | None = None        # comparison form, non-empty; adapters must not re-normalize
    min_score: float | None = None # [0, 1], >=, NULL scores excluded
NO_FILTERS = ListFilters()

class PhraseRepository(Protocol):
    def list_page(self, limit: int, cursor: ListCursor | None, *,
                  filters: ListFilters = NO_FILTERS) -> PhraseListPage: ...
    def count_filtered(self, filters: ListFilters) -> int: ...
    def count_all(self) -> int: ...   # == count_filtered(NO_FILTERS)

# application/list_phrases.py
def __call__(self, *, limit: int, cursor: str | None,
             status: ValidationStatus | None = None, q: str | None = None,
             min_score: float | None = None) -> PhraseListView: ...

# api/schemas.py
def query_score() -> Any:   # min_score
    return Annotated[float, Field(ge=0, le=1, allow_inf_nan=False)]
def query_text(max_length: int) -> Any:   # q; raw cap = PHRASE_MAX_LENGTH
    ...  # AfterValidator raising PydanticCustomError("string_too_long", ..., {"max_length": max_length})

# api/router.py list_phrases: new params
status: ValidationStatus | None = None,          # enum error -> 422 reason invalid_type
q: query_text(phrase_max_length) | None = None,  # -> 422 too_long + details.max_length
min_score: query_score() | None = None,          # -> 422 out_of_range
```

The existing `_validation_error_handler` in `main.py` already maps all three
error types. No change is needed there.

## Frontend

- **`client.ts`**: `ListPhrasesParams` gains
  `status?: "unique" | "duplicate_confirmed"`, `q?: string` and
  `minScore?: number`, serialized as `status`, `q` and `min_score`. Only
  defined values are serialized.
- **`hooks/useDebouncedValue.ts`** (new): `useState` plus `useEffect` running
  `setTimeout`, returning `clearTimeout`. The delay is
  `LIST_FILTER_DEBOUNCE_MS = 300`, added to `constants.ts`.
- **`PhraseListFilters.tsx`** (new, presentational): a status `<select>`
  (Todas / `copy.badge.*`), a text input (`maxLength` = the phrase max), and a
  `<input type="number" min=0 max=100 step=1>` for minimum similarity as a
  percent. It sends `percent / 100`, which agrees with `floorPercent`
  display: an item showing "85%" passes a minimum of 85.
- **`PhraseList.tsx`** (container) owns the filter state:

```tsx
const debouncedQ = useDebouncedValue(qDraft, LIST_FILTER_DEBOUNCE_MS);
// Clearing q applies at once; only non-blank typing waits.
const applied = toListParams(statusFilter, qDraft.trim() === "" ? "" : debouncedQ, minScorePct);
const appliedKey = JSON.stringify(applied);
const filtersRef = useRef(applied); filtersRef.current = applied;
const fetchedKey = useRef(appliedKey);   // initial = unfiltered == SSR initialPage
const generation = useRef(0);

useEffect(() => {                        // StrictMode-safe: key compare, not a first-run flag
  if (fetchedKey.current === appliedKey) return;
  fetchedKey.current = appliedKey;
  void refresh();
}, [appliedKey]);
```

`refresh()` keeps its public signature. It now means "page 1 with the current
filters": it reads `filtersRef.current`, bumps `generation`, clears
`inFlightMore`, and drops any response whose generation is stale. So the
existing callers (`PhraseWorkspace.onSaved` and Reintentar) respect the active
filters without changes. `loadMore` sends `{...filtersRef.current, cursor}`
and uses the same generation guard. It resets `inFlightMore` only for a
current-generation response. `status` and `minScore` changes go through the
same effect with no debounce. When filters are active and the list is idle
with zero items, the list shows `copy.list.emptyFiltered` and a
"Limpiar filtros" button that resets all three filters. The filter controls
render outside the items/error branches.

## File Changes

| File | Action | Change |
|---|---|---|
| `services/api/src/app/modules/phrases/contracts.py` | Modify | `ListFilters`, `NO_FILTERS`, `list_page` kwarg, `count_filtered`, `__all__` |
| `.../adapters/pgvector_repository.py` | Modify | Fragments, `_list_where`, both builders, `_contains_pattern`, `count_filtered` |
| `.../adapters/in_memory_repository.py` | Modify | `_passes`, filtered `list_page`/`total`, `count_filtered` |
| `.../application/list_phrases.py` | Modify | Normalize `q` (D2), build `ListFilters` |
| `.../api/schemas.py` | Modify | `query_score`, `query_text` |
| `.../api/router.py` | Modify | Three query params passed to `container.list_phrases` |
| `services/api/migrations/versions/0002_list_filter_status_index.py` | Create | Partial index plus downgrade |
| `services/api/tests/contract_suite/repository_contract.py` | Modify | Filter cases in `ListPageContractSuite`, `_new_phrase(status, score, neighbour)` helper |
| `services/api/tests/integration/test_list_filters_pgvector.py` | Create | EXPLAIN guards |
| `services/api/tests/contract/test_phrases_endpoints.py` | Modify | 422s and param passthrough |
| `services/api/tests/unit/phrases/` (list_phrases test) | Modify | `q` normalization and blank handling |
| `docs/openapi.json`, `apps/web/src/types/api.ts` | Regenerate | Snapshot test plus the CI drift guard (`make types`) |
| `docs/decisions/ADR-016-list-filters.md`, `README.md` | Create/Modify | Beyond-brief entry, `pg_trgm` revisit trigger, summary link |
| `services/api/tests/unit/test_decision_log.py` | Modify | **Flag for sdd-tasks:** `test_exactly_five_beyond_brief_adrs_at_top_level` becomes six. Check that its glob and message ("ADR-001..005") admit ADR-016 at top level |
| `apps/web/src/lib/api/client.ts` (+ `client.test.ts`) | Modify | New params |
| `apps/web/src/features/phrases/hooks/useDebouncedValue.ts` | Create | Debounce hook |
| `apps/web/src/features/phrases/components/PhraseListFilters.tsx` | Create | Controls |
| `apps/web/src/features/phrases/components/PhraseList.tsx` (+ test) | Modify | Filter state, generation guard, filtered empty state |
| `apps/web/src/features/phrases/constants.ts`, `phrases.module.css` | Modify | Debounce constant, filter bar styles |
| `apps/web/src/i18n/copy.es.ts` (+ test) | Modify | Filter labels, `emptyFiltered`, `clearFilters` (neutral Spanish) |

## Testing Strategy

| Layer | What | How |
|---|---|---|
| Contract suite (both adapters) | Each filter and the AND combination; `total == count_filtered ==` the filtered size on every page; a full cursor walk under a filter; literal `%` `_` `\`; `q="ß"` matches a stored `"strasse"`; `min_score` equality boundary; NULL score excluded | `ListPageContractSuite` |
| Integration (pgvector) | EXPLAIN for `status=duplicate_confirmed` (with and without cursor, plus the count) uses `phrases_duplicate_confirmed_created_at_id_idx` and no Seq Scan, **including under `SET plan_cache_mode = force_generic_plan`**, which guards D4; the unfiltered builder output equals today's SQL | New file, seeded with a skewed table, then `ANALYZE` |
| API contract | Invalid `status`, `min_score=1.1`/`nan`, and an over-length `q` each return 422 `VALIDATION_ERROR` with the right reason | TestClient |
| Frontend | The debounce fires once after 300 ms; status and min-score changes refetch immediately; a stale response is dropped; `refresh()` after save keeps the filters; the filtered empty state and clear button work; the query string is correct | Vitest with fake timers and the injected client |

## Migration / Rollout

Migration `0002` is additive, and its downgrade drops the index. The new
params are optional, so older clients are unaffected.

## Open Questions

None blocking. The proposal's own assumptions still stand: `status` is the
most prominent control, and the UI includes a clear-filters button.
