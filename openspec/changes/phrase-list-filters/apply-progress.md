# Apply Progress: Saved-Phrase List Filters

Source of truth: `tasks.md` (Units 1-4), `design.md`. This file tracks
apply-phase execution batch by batch.

> **Merge/reconciliation note (orchestrator)**: this file hit an add/add
> git conflict at every branch merge point in the feature-branch-chain
> (PR #48 merging Unit 4 into Unit 3's branch, then PR #46 merging the
> combined Unit 1+2 branch into the tracker) — expected fallout of each
> unit's apply session writing its own independent copy of this path.
> Resolved each time by combining the real content from both sides into
> this single running document, in unit order (1 → 2 → 3 → 4). No content
> from any unit's session was dropped; where one side had a fuller/more
> authoritative account of a unit than another (e.g. Unit 1/2's original
> sections vs. an earlier reconstruction), the fuller original was kept.

## Unit 1: Filter contracts and repository adapters — DONE

Branch: `feat/plf-01-backend-filters` (child of tracker `feat/phrase-list-filters`, which is off `develop`).

### Files changed

| File | Action | What was done |
|---|---|---|
| `services/api/src/app/modules/phrases/contracts.py` | Modified | Added `ListFilters` frozen dataclass (`status`, `text`, `min_score`), module constant `NO_FILTERS = ListFilters()`; `PhraseRepository.list_page` gained keyword-only `filters: ListFilters = NO_FILTERS`; added `count_filtered(filters) -> int` to the Protocol; `count_all()` re-documented as `count_filtered(NO_FILTERS)`; `__all__` updated. |
| `services/api/src/app/modules/phrases/adapters/in_memory_repository.py` | Modified | Added `_passes(row, filters)` row predicate (status equality, `text in normalized_text`, `min_score` with SQL-matching NULL semantics); `list_page` filters before sorting/paging and computes `total` via `count_filtered`; added `count_filtered`; `count_all` now delegates to `count_filtered(NO_FILTERS)`. |
| `services/api/src/app/modules/phrases/adapters/pgvector_repository.py` | Modified | Added `_status_predicate` (D4: enum value inlined as a SQL literal, never bound), `_list_where` (shared conditional-fragment builder), `build_list_page_query`/`build_count_list_query` (now accept `status`/`has_text`/`has_min_score`), `_contains_pattern` (LIKE-escapes `\`, `%`, `_`, backslash escaped first); `list_page`/added `count_filtered` build params conditionally and pass filters through; `count_all` now delegates to `count_filtered(NO_FILTERS)`; removed the now-dead `COUNT_ALL_QUERY` constant. |
| `services/api/migrations/versions/0002_list_filter_status_index.py` | Created | Partial index `phrases_duplicate_confirmed_created_at_id_idx ON phrases (created_at DESC, id DESC) WHERE validation_status = 'duplicate_confirmed'`, plain `CREATE INDEX` per D7, working `downgrade`. |
| `services/api/tests/contract_suite/repository_contract.py` | Modified | `_new_phrase` gained optional `status`/`score`/`neighbour`/`normalized_text` kwargs (backward compatible, 2-arg call sites untouched). Added 7 filter scenarios to `ListPageContractSuite` (registered for BOTH adapters via existing composition): status-only, text-only, a case-folding regression case (`ß`→`ss`, proving neither adapter re-folds), literal-wildcard escaping (`%`, `_`, `\`), min-score-only (NULL excluded, `>=` boundary), AND-combination, and a full cursor walk under a filter with `total`/`count_filtered` pinned to the filtered size on every page. |
| `services/api/tests/integration/test_pgvector_repository.py` | Modified | Added pure-logic (no-DB) tests for `_status_predicate`, `_contains_pattern`, `build_list_page_query` (including the "byte-identical to the pre-Unit-1 query when unfiltered" proof design.md requires), `build_count_list_query`. Updated the module docstring: this venv now has `sqlalchemy` installed (see below), so this file's tests execute for real. |
| `services/api/tests/integration/test_schema.py` | Modified | Added `_index_exists` helper and `TestListFilterStatusIndexMigration`, asserting the partial index exists after `upgrade head` and is gone after `downgrade base`. |

### TDD Cycle Evidence

| Task | RED | GREEN | REFACTOR | Notes |
|---|---|---|---|---|
| 1.1 `ListFilters`/`NO_FILTERS`/Protocol | N/A (pure type addition; see below) | Implemented alongside 1.2/1.4 | — | Protocol changes are structural (no runtime enforcement); driven RED by 1.4's contract-suite tests importing `ListFilters` and calling the new `list_page(filters=...)`/`count_filtered` signatures, same pattern this codebase used for `ListCursor`/`Page` (no dedicated `test_contracts.py`). |
| 1.2 in-memory adapter | Confirmed: 7 new contract-suite tests failed with `TypeError: ... got an unexpected keyword argument 'filters'` before the adapter change | Confirmed: `pytest tests/contract_suite -m "not integration and not slow"` → 20 passed | Ran full unit suite (310 passed) after | Real pytest RED→GREEN, executed in-session. |
| 1.3 pgvector adapter (pure SQL-shape) | Confirmed: `ImportError: cannot import name '_contains_pattern'` before the adapter change | Confirmed: 9/9 passed in `tests/integration/test_pgvector_repository.py` (marked `integration`, runs without a DB — pure string-builder logic) | ruff/mypy clean after | Real pytest RED→GREEN, executed in-session. |
| 1.3 pgvector adapter (DB-backed `list_page`/`count_filtered`, and 1.4's pgvector registration in `test_list_page_pgvector.py`) | Not executed as pytest RED | Not executed as pytest GREEN | — | Could not run in that session's sandbox — see Environment note. Verified instead by hand-executing the exact rendered SQL (via `docker compose exec db psql`) against seeded data in `phrases_test`; see "Manual DB verification" below. |
| 1.5 migration `0002` + lifecycle test | Not executed as pytest RED | Not executed as pytest GREEN | — | Could not run via pytest/alembic in that session's sandbox — see Environment note. Verified by hand-applying the migration's literal SQL (`CREATE INDEX` / `DROP INDEX`) against `phrases_test` via `docker compose exec db psql`: index present after upgrade, absent after downgrade, index definition matches the migration exactly. |

**Post-apply re-verification (orchestrator, later session)**: the DB-backed
tests above (`test_schema.py`, `test_list_page_pgvector.py`, plus Unit 2's
`test_list_filters_pgvector.py`) were re-run for real via pytest against
the live Postgres container, after resolving a local port conflict (this
machine's native PostgreSQL 16 install was shadowing Docker's default 5432
— see Engram `discovery/native-postgres-port-conflict`; fixed via
`DB_HOST_PORT` in `.env`, no code change). Result: **28/28 passed**. The
"could not run this session" caveats below are historical and no longer
block anything.

### Environment note — DB-backed tests could not run via pytest in the apply session

That apply session's sandboxed `Bash` tool could not make a real TCP
connection from the host to the `db` container's published port: every
`psycopg`/`sqlalchemy` connection attempt failed with `FATAL: password
authentication failed`, but no corresponding entry ever appeared in
`docker compose logs db` for any of these attempts — meaning the
connection never actually reached the real Postgres backend; the sandbox's
network layer intercepted it. `docker compose exec db psql ...`
(executing INSIDE the already-running `db` container) was not blocked and
was used instead for hand-verification.

**Manual DB verification performed instead** (via `docker compose exec db
psql -U todo_ia -d phrases_test`, not through pytest/SQLAlchemy):
1. Recreated the `phrases` table (migration 0001's literal SQL) in
   `phrases_test`, then ran migration 0002's literal upgrade SQL — index
   created successfully; `pg_indexes` confirmed its definition matches the
   migration byte-for-byte. Ran the downgrade SQL — index gone. Recreated
   it again for the next step.
2. Seeded 5 rows (3 `unique`, 2 `duplicate_confirmed` with scores 0.4 and
   0.9) plus a `unique` row containing a literal `%` in its text.
3. Printed the EXACT SQL `build_list_page_query`/`build_count_list_query`
   render for the AND-combination case (`status=duplicate_confirmed`, text
   `LIKE '%leche%' ESCAPE '\'`, `min_score >= 0.5`) and ran it through
   psql: returned exactly 1 row (id 5, score 0.9) — id 4 (score 0.4)
   correctly excluded by `min_score`.
4. Ran the literal-wildcard-escape pattern (`text="0%"` →
   `LIKE '%0\%%' ESCAPE '\'`): matched only the row whose text genuinely
   contains `%`, proving `%` is not treated as a wildcard.
5. Confirmed NULL-score exclusion: `similarity_score >= 0.0` returned only
   the 2 `duplicate_confirmed` rows, never the 3 NULL-score `unique` rows.
6. Dropped the manually-created table afterward.

### Venv note

`services/api/.venv` was missing `alembic`/`sqlalchemy`/`psycopg` at the
start of the Unit 1 apply session — `.venv/bin/pip install -e ".[dev]"`
synced it, which is why `test_pgvector_repository.py`'s pure-logic tests
now execute.

### Test results (Unit 1 apply session)

```
cd services/api && .venv/bin/python -m pytest -m "not integration and not slow" -q
→ 310 passed, 70 deselected (was 303 passed before Unit 1; +7 new filter scenarios via the in-memory adapter)

cd services/api && .venv/bin/python -m pytest -m integration tests/integration/test_pgvector_repository.py -q
→ 9 passed (pure SQL-shape tests, no DB needed)

cd services/api && .venv/bin/ruff check src tests
→ All checks passed!

cd services/api && .venv/bin/mypy src
→ Success: no issues found in 44 source files

cd services/api && .venv/bin/lint-imports
→ Contracts: 5 kept, 0 broken.
```

DB-backed integration tests: NOT executed via pytest in that session (see
Environment note above); hand-verified via direct SQL instead — since then
re-run for real, see "Post-apply re-verification" above.

### Deviations from design.md

- `_new_phrase`'s helper signature grew an additional `normalized_text`
  keyword (not listed in tasks.md 1.4's shorthand) so the case-folding
  regression test could seed a `normalized_text` that differs from the
  display `text` — needed to simulate what `SavePhrase` would have already
  written (folding "Straße" to "strasse" before Unit 1's adapters ever see
  it). Backward compatible; every pre-existing 2-arg call site is
  unaffected.
- The exact tasks.md 1.4 phrasing `q="ß" matching stored "strasse"` was
  ambiguous taken literally (a bare "ß" is never a substring of the ASCII
  "strasse"). Implemented as two assertions instead, documented inline in
  `repository_contract.py`: an already-folded query ("strasse") matches an
  already-folded stored value, and a raw un-folded query ("straße") does
  NOT match it — proving neither adapter performs its own casefolding,
  consistent with design.md's stated rationale for choosing `LIKE` over
  `ILIKE`.

### What Unit 2 needs (exact shapes to import/call)

Unit 2 (`services/api/src/app/modules/phrases/api/schemas.py`,
`api/router.py`, `application/list_phrases.py`) needs:

```python
from app.modules.phrases.contracts import ListFilters, NO_FILTERS, ValidationStatus

# ListFilters — frozen dataclass, all fields optional, default NO_FILTERS:
ListFilters(
    status: ValidationStatus | None = None,
    text: str | None = None,       # MUST already be in comparison form
                                     # (comparison_form(display_form(q))) —
                                     # adapters do NOT normalize; blank/None
                                     # both mean "no text filter", Unit 2
                                     # must turn blank into None itself
    min_score: float | None = None, # [0, 1]; NULL similarity_score rows
                                     # are always excluded when set
)

# PhraseRepository (Protocol, unchanged method names, new signature/method):
def list_page(
    self, limit: int, cursor: ListCursor | None, *, filters: ListFilters = NO_FILTERS
) -> PhraseListPage: ...          # existing positional call sites remain
                                    # valid unchanged — `filters` only
                                    # needs passing when Unit 2 wants to
                                    # actually filter

def count_filtered(self, filters: ListFilters) -> int: ...  # NEW method;
                                    # `list_page`'s own `total` already
                                    # calls this internally — Unit 2 does
                                    # NOT need to call it separately unless
                                    # it wants a count without a page
```

## Unit 2: API wiring, EXPLAIN guard, OpenAPI/types regen — DONE

Branch: `feat/plf-02-api-wiring` (child of `feat/plf-01-backend-filters`, per
`feature-branch-chain`).

**Environment note — this session had to switch to an isolated `git
worktree` mid-unit.** The shared main working directory was found to be
LIVE across at least three concurrent apply sub-agent sessions (this one,
Unit 3, and Unit 4) with no isolation: HEAD and uncommitted files changed
out from under this session more than once. Recovery: `git stash push -u`,
then `git worktree add ../todo-ia-plf-02 -b feat/plf-02-api-wiring
feat/plf-01-backend-filters` for a fully isolated checkout, then `git
stash pop` inside it — zero work lost. All Unit 2 work was done inside
`/Users/macos/Code/Projects/todo-ia-plf-02`, reusing the main worktree's
already-provisioned `.venv` by absolute path.

### Files changed

| File | Action | What was done |
|---|---|---|
| `services/api/src/app/modules/phrases/api/schemas.py` | Modified | Added `query_score()` (`Annotated[float, Field(ge=0, le=1, allow_inf_nan=False)]`, always `[0,1]`) and `query_text(max_length)` (`AfterValidator` raising the same `string_too_long`-typed `PydanticCustomError` as `raw_phrase_text`, but capped at the SEMANTIC `max_length` directly — no `4x` raw multiplier, since `q` is only ever compared, never stored/embedded). |
| `services/api/src/app/modules/phrases/api/router.py` | Modified | `list_phrases` route gained `status: ValidationStatus \| None`, `q: query_text(phrase_max_length) \| None`, `min_score: query_score() \| None`, all threaded through to `container.list_phrases(...)`. |
| `services/api/src/app/modules/phrases/application/list_phrases.py` | Modified | `ListPhrases.__call__` gained `status`/`q`/`min_score` keyword params; `q` normalized via `comparison_form(display_form(q))` (D2), blank/whitespace-only collapses to `None`; builds one `ListFilters(status=status, text=text_filter, min_score=min_score)` and passes it to `uow.repo.list_page(limit, list_cursor, filters=filters)` — `total` comes back already filter-aware via Unit 1's `count_filtered` internally, so this use case does NOT call `count_filtered` a second time (confirmed correct, not a deviation). |
| `services/api/tests/unit/phrases/test_schemas.py` | Modified | Added `query_score`/`query_text` boundary, out-of-range, `nan`-rejection, and `details.max_length` tests. |
| `services/api/tests/unit/phrases/test_list_phrases.py` | Modified | 7 new tests: status filter passthrough, `status=None` no-op, `q` casefold normalization, blank/whitespace/`None` `q` all treated as absent, `min_score` NULL-exclusion, `min_score=None` no-op, AND-combination proof. |
| `services/api/tests/contract/test_phrases_endpoints.py` | Modified | 12 new end-to-end tests: invalid `status` → 422, `min_score` out of range (incl. `nan`) → 422, over-length `q` → 422, filter-by-status, case-insensitive text filter, literal `%`/`_` wildcard matching, `min_score` NULL-exclusion, AND-combination, filter-aware `total`, cursor-resend-filters pagination walk. |
| `services/api/tests/integration/test_list_filters_pgvector.py` | Created | EXPLAIN guards — module-scoped fixture bulk-seeds a 20000-`unique`/3-`duplicate_confirmed` table (matching `explore-db-findings.md`'s real shape), `ANALYZE`s. 5 tests: unfiltered path still uses `phrases_created_at_id_idx`; `status=duplicate_confirmed` uses the new partial index with no cursor / with a cursor / for the count; and the D4-specific guard — the same query still uses the partial index under `SET plan_cache_mode = force_generic_plan`, proving the status value survives as a literal even when Postgres is forced off a custom plan. |
| `docs/openapi.json` | Regenerated | Via `app.openapi()`. `GET /phrases`'s `parameters` now lists `limit, cursor, status, q, min_score`; `ValidationStatus` added as a reusable `components.schemas` enum. |
| `apps/web/src/types/api.ts` | Regenerated | Via `make types`. `components.schemas.ValidationStatus` added; `operations["list_phrases_phrases_get"].parameters.query` gained `status?`, `q?`, `min_score?`. |

### TDD Cycle Evidence

| Task | RED | GREEN | TRIANGULATE |
|------|-----|-------|-------------|
| 2.1 `query_score`/`query_text` (schemas) | Confirmed `ImportError` before adding the functions | 22/22 passed after | 9 new cases: boundary values, out-of-range, `nan`, semantic-vs-raw-cap distinction |
| 2.1 router wiring | 12/19 new list_phrases tests confirmed failing (FastAPI silently ignored the unrecognized params) before the router change | 19/19 passed after | 12 new scenarios across all three params plus AND-combination and cursor-resend |
| 2.2 `ListPhrases` filter/normalize | Confirmed `TypeError: unexpected keyword argument 'status'` before the change | 14/14 passed after | 9 new cases: status filter/no-op, casefold, blank/whitespace/None `q`, `min_score` filter/no-op, AND-combination |
| 2.4 EXPLAIN guard | Not executed as pytest RED — see "DB-backed verification" below | Not executed as pytest GREEN — see below | N/A |
| 2.5 OpenAPI/`api.ts` regen | `test_snapshot_matches_docs_openapi_json` failed (stale snapshot) immediately after 2.1-2.3 landed | Regenerated both files; all 6 `test_openapi.py` tests pass | N/A |

### DB-backed verification (EXPLAIN guard, `test_list_filters_pgvector.py`)

Same sandboxed-TCP limitation Unit 1 hit — not executed via pytest in that
session. Hand-verified via `docker compose exec db psql -U todo_ia -d
phrases_test` using the EXACT same table shape and EXACT same rendered
SQL the test file builds:

1. Applied migrations 0001+0002's literal SQL to the scratch `phrases_test` database.
2. Bulk-seeded 20000 `unique` + 3 `duplicate_confirmed` rows, `ANALYZE`d.
3. Unfiltered `list_page` query: `Index Scan using phrases_created_at_id_idx`, 5 buffer hits — no plan regression on the default path.
4. `status=duplicate_confirmed`, no cursor / with a cursor / count-only: all three used `Index Scan`/`Index Only Scan` on `phrases_duplicate_confirmed_created_at_id_idx`, 2 buffer hits each, zero `Seq Scan` — a ~2500x reduction in buffer hits vs. the pre-migration baseline (5007 buffers + `Seq Scan`) in `explore-db-findings.md`.
5. **D4 guard**: `SET plan_cache_mode = force_generic_plan;` then `PREPARE`/`EXECUTE` ×5 (mirroring psycopg3's real auto-prepare threshold): still `Index Scan using phrases_duplicate_confirmed_created_at_id_idx`, still zero `Seq Scan` — proves the literal-not-bound status value (D4) survives a forced generic plan, which a bound `:status` parameter would NOT have.
6. Dropped the scratch table afterward.

**Post-apply re-verification (orchestrator, later session)**: this test
file was later re-run for real via pytest against the live Postgres
container (same port-conflict fix as Unit 1) — **5/5 passed**, matching
every hand-verified assertion above.

### Test results (Unit 2 apply session)

```
cd services/api && .venv/bin/python -m pytest -m "not integration and not slow" -q
→ 340 passed, 76 deselected (was 303 before Unit 2; net new: 31)

cd services/api && .venv/bin/python -m pytest tests/contract/test_openapi.py -q
→ 6 passed (including test_snapshot_matches_docs_openapi_json)

cd services/api && .venv/bin/ruff check src tests
→ All checks passed!

cd services/api && .venv/bin/mypy src
→ Success: no issues found in 44 source files

cd services/api && .venv/bin/lint-imports
→ Contracts: 5 kept, 0 broken.
```

### Deviations from design.md

- None functionally. `test_list_filters_pgvector.py` uses a module-scoped
  fixture (one seeded table shared by all 5 tests) instead of the
  function-scoped pattern other pgvector integration files use — noted in
  the file's own docstring: rebuilding 20003 rows per test would be slow
  for read-only EXPLAIN checks that never mutate the table.

### What Unit 3 (frontend) needs to know

- `GET /phrases?status=<unique|duplicate_confirmed>&q=<string>&min_score=<0..1 float>`, all three optional, AND-combined.
- Invalid `status`, `min_score` outside `[0, 1]` (incl. `nan`), or `q` longer than `PHRASE_MAX_LENGTH` → `422 VALIDATION_ERROR`, same envelope as every other validation error in this API.
- Response shape unchanged: `total` now reflects the ACTIVE filter set.
- The cursor stays filter-agnostic — the client MUST resend the same filter query params on every page request.
- `min_score` on the wire is `percent / 100` (a UI control showing "85%" sends `0.85`).
- Text filter matching is via `LIKE` under the same casefolding the backend already applies to `normalized_text` — NOT accent-insensitive (a query for "cafe" will not match a stored "café").

### Issues found

None in the implementation itself. The environmental git-worktree race
(see Environment note above) was recovered from cleanly with zero work
lost.

## Unit 3: Frontend filter controls — DONE

Branch: `feat/plf-03-frontend-filters` (child of tracker
`feat/phrase-list-filters` DIRECTLY, per design.md: "Unit 3 is independent
of Units 1-2" — not stacked on Unit 1 or Unit 2's branches).

Independent of Units 1-2 per design.md/tasks.md's own notes:
`ListPhrasesParams` in `client.ts` is hand-written (not derived from the
generated `api.ts` OpenAPI schemas Unit 2 regenerates), and every frontend
test injects a fake `fetchImpl`/`listPhrases`.

### Files changed

| File | Action | What was done |
|---|---|---|
| `apps/web/src/lib/api/client.ts` | Modified | `ListPhrasesParams` gained `status?: "unique" \| "duplicate_confirmed"`, `q?: string`, `minScore?: number`; `listPhrases()` serializes them as `status`/`q`/`min_score` query params, only when defined. |
| `apps/web/src/lib/api/client.test.ts` | Modified | Two new cases: all three filter params encoded together; no filter params sent when `{}` is passed. |
| `apps/web/src/features/phrases/hooks/useDebouncedValue.ts` | Created | Generic `useState`/`useEffect`+`setTimeout`/`clearTimeout` debounce hook. Debounces, not throttles — the value-clearing special case ("clearing applies immediately") is NOT inside this hook; it lives in `PhraseList.tsx`'s own `qDraft.trim() === "" ? "" : debouncedQ` composition. |
| `apps/web/src/features/phrases/hooks/useDebouncedValue.test.ts` | Created | 5 tests: initial value, no update before delay, updates at delay, debounce-not-throttle, timer cleared on unmount. |
| `apps/web/src/features/phrases/constants.ts` | Modified | Added `LIST_FILTER_DEBOUNCE_MS = 300`. |
| `apps/web/src/features/phrases/components/PhraseListFilters.tsx` | Created | Presentational filter bar: status `<select>` (`Todas`/`Única`/`Duplicado confirmado`, status FIRST — most prominent control), text `<input>` (`maxLength` = phrase max), min-score `<input type="number" min=0 max=100 step=1>` whose `onChange` sends `percent / 100` (a `[0,1]` fraction) up, or `null` when cleared. |
| `apps/web/src/features/phrases/components/PhraseListFilters.test.tsx` | Created | 9 tests: status-select-first DOM order, option labels/default, wiring, `maxLength` cap, placeholder, percent→fraction conversion, clearing sends `null`, number-input bounds. |
| `apps/web/src/i18n/copy.es.ts` | Modified | New `filters` namespace; `list.emptyFiltered`; `button.clearFilters`. Status select reuses the EXISTING `badge.*` keys. |
| `apps/web/src/i18n/copy.es.test.ts` | Modified | Extended the verbatim-comparison table. |
| `apps/web/src/features/phrases/components/PhraseList.tsx` | Modified | Filter state owned here; `debouncedQ = useDebouncedValue(qDraft, LIST_FILTER_DEBOUNCE_MS)`; `appliedQ = qDraft.trim() === "" ? "" : debouncedQ`; `filtersRef` kept current every render; a `generation` ref-counter guards `refresh()`/`loadMore()` against stale responses. `refresh()` keeps its exact public signature — existing call sites (`PhraseWorkspace.onSaved`, Reintentar) transparently respect active filters. Filtered empty state shows `copy.list.emptyFiltered` + "Limpiar filtros". |
| `apps/web/src/features/phrases/components/PhraseList.test.tsx` | Modified | New `describe("filters")` block, 9 tests. All 15 pre-existing tests still pass unmodified. |
| `apps/web/src/features/phrases/components/phrases.module.css` | Modified | Added `.filterBar`, `.filterField`, `.filterSelect`/`.filterInput`, `.emptyStateFiltered`. |
| `openspec/specs/phrase-ui/spec.md` | Modified | Mirrored the three ADDED requirements verbatim; extended the copy table. |
| `openspec/changes/phrase-list-filters/tasks.md` | Modified | Marked 3.1-3.5 `[x]`. |

### TDD Cycle Evidence

| Task | RED | GREEN | REFACTOR |
|---|---|---|---|
| 3.1 `client.ts` params | Confirmed: URL missing filter params before the change | 14/14 passed | None needed |
| 3.2 `useDebouncedValue` | Confirmed: module did not exist | 5/5 passed | None needed |
| 3.3 `copy.es.ts`/`PhraseListFilters.tsx` | Confirmed: missing keys/module | 1/1 and 9/9 passed | None needed |
| 3.4/3.5 `PhraseList.tsx` wiring | Confirmed: 9 new filter-scenario tests failed (filter bar not rendered); 15 pre-existing tests still passed | 24/24 passed after wiring | Fixed 4 tests' `waitFor`-under-fake-timers hang (switched to explicit `act` microtask flushes); fixed 2 `tsc` errors on `client.listPhrases.mockClear()` typing. |

### Test results (Unit 3 apply session)

```
cd apps/web && npx vitest run
→ Test Files  13 passed (13)
→ Tests  202 passed (202)

cd apps/web && npx tsc --noEmit
→ (no output — clean)
```

### Deviations from design.md

- `PhraseListFilters`'s `onMinScoreChange` prop delivers the ALREADY-CONVERTED `[0,1]` fraction, not the raw percent — design.md's own prose followed literally.
- `useDebouncedValue.ts` has NO special case for "clearing applies immediately" — that logic lives entirely in `PhraseList.tsx`.
- `PhraseListFilters`'s text-input `maxLength` default duplicates `PhraseForm.tsx`'s `ENV_MAX_LENGTH` pattern locally, since that constant isn't exported and Unit 3's scope doesn't include modifying `PhraseForm.tsx`.

### Issues found

None blocking.

## Unit 4: Decision log — ADR-016 — DONE

Branch: `feat/plf-04-decision-log` (child of tracker `feat/phrase-list-filters`, which is off `develop`), branched directly off the tracker (Unit 4 is independent of Units 1-3).
Commit: `a60d73f` — `docs(decisions): add ADR-016 list filters, decision log now six entries`.

### Files changed

| File | Action | What was done |
|---|---|---|
| `docs/decisions/ADR-016-list-filters.md` | Created | `type: beyond-brief` front matter; states the brief (and the pre-existing `phrase-management` "List phrases" requirement) called filtering out of scope, the decision to add `status`/`q`/`min_score` to `GET /phrases`, the rationale (support-conversation-driven need, ADR-005 cited as the established beyond-brief-additive-UX precedent), and the deferred `pg_trgm` trigger conditions (~100k rows or filtered p95 > 100ms) per `proposal.md`. |
| `services/api/tests/unit/test_decision_log.py` | Modified | Renamed `test_exactly_five_beyond_brief_adrs_at_top_level` to `test_exactly_six_beyond_brief_adrs_at_top_level`; expected count 5 -> 6; assertion message now names `ADR-001..005, ADR-016`. |
| `README.md` | Modified | "Decisions beyond the brief" section: "Five decisions" -> "Six decisions"; added an `ADR-016` row to the table; "not counted among the five above" -> "not counted among the six above". |
| `docs/decisions/technical/` count line | Not modified | Task 4.3's scope note only touched the top-level five/six count line the technical count line references; the technical-ADR count itself (ten) is unchanged by this unit. |
| `docs/architecture.md` | Modified | Monorepo-layout code comment: `# exactly five beyond-brief ADRs (ADR-001..005)` -> `# exactly six beyond-brief ADRs (ADR-001..005, ADR-016)`. Found via this task's required sweep for stale ADR-count mentions across top-level docs. |
| `openspec/changes/phrase-list-filters/tasks.md` | Modified | Marked 4.1-4.3 `[x]`. |

### Deliberately NOT modified (out of Unit 4's scope, confirmed by sweep)

- `openspec/specs/phrase-management/spec.md` — still says "exactly five" / lists topics (1)-(5). This is the pre-change deployed spec; the delta at `openspec/changes/phrase-list-filters/specs/phrase-management/spec.md` already carries the six-entry MODIFIED requirement, and the top-level `specs/` copy is expected to be updated by `sdd-archive` when this change is archived, not by `sdd-apply`. Left untouched.
- `docs/decisions/technical/ADR-011-embedding-cache.md` — its classification note references "the exactly five requirement" as *historical* rationale for why the embedding cache was filed as `technical` rather than `beyond-brief` at the time it was written. That number is now stale prose (five -> six happened for an unrelated later reason), but it is inside another unit's already-shipped ADR content, not a live doc/count in the sense task 4.3 asked to sweep. Flagged here rather than edited.

### TDD Cycle Evidence

| Task | RED | GREEN | REFACTOR | Notes |
|---|---|---|---|---|
| 4.1 `ADR-016-list-filters.md` | N/A (doc creation; RED is expressed through 4.2's test) | N/A | — | Doc content authored per `proposal.md`'s Approach/ADR-016 guidance and the delta spec's "ADR-016 documents the reversal and the deferred index" scenario. |
| 4.2 decision-log test rename/count | Confirmed: ran `pytest tests/unit/test_decision_log.py -q` BEFORE creating ADR-016 -> 4 passed (baseline, 5 ADRs). After creating `ADR-016-list-filters.md` (task 4.1) but BEFORE touching the test -> reran -> `test_exactly_five_beyond_brief_adrs_at_top_level` FAILED (`assert 6 == 5`) and `test_readme_links_every_adr` FAILED (README didn't mention `ADR-016-list-filters.md` yet); 2 failed, 2 passed. | Renamed the test to `test_exactly_six_beyond_brief_adrs_at_top_level`, updated count/message, updated README (task 4.3) -> reran -> 4 passed. | ruff/mypy not re-run (docs+test-assertion-only change, no source under `services/api/src/app/` touched) | Real pytest RED->GREEN, executed in-session, exactly as tasks.md's "Strict TDD" preamble requires. |
| 4.3 README + architecture.md sweep | Implicit RED: `test_readme_links_every_adr` (see above) failed until README was updated | Confirmed GREEN in the same rerun as 4.2 above | — | `docs/architecture.md` has no dedicated test coverage; verified by `rg` sweep for "five"/ADR-count mentions across top-level docs. |

### Full verification run

- `cd services/api && .venv/bin/python -m pytest tests/unit/test_decision_log.py -q` -> `4 passed`.
- `cd services/api && .venv/bin/python -m pytest -m "not integration and not slow" -q` -> `303 passed, 56 deselected` (this branch alone, before Units 1-3 were merged in).
- Doc sweep for stale ADR-count mentions: `rg -ni "five.{0,20}(beyond|adr)|beyond.{0,20}five|exactly five"` across `*.md`/`*.py`, excluding `openspec/changes/**`. Hits: `docs/architecture.md` (fixed, this unit), `docs/decisions/technical/ADR-011-embedding-cache.md` (historical, left as-is), `openspec/specs/phrase-management/spec.md` (pre-change deployed spec, left for `sdd-archive`). `openspec/project.md` had no hits.

### Environment note — shared working directory across concurrent Unit agents

This repo had one working directory, not per-unit git worktrees, while
Units 1/3/4 ran concurrently. Mid-session, another agent's `git checkout`
(observed switching HEAD to `feat/plf-03-frontend-filters`, and at another
point uncommitted edits to `services/api/src/app/modules/phrases/api/schemas.py`
and `tests/unit/phrases/test_schemas.py` appeared — Unit 2's live WIP)
silently changed this branch's checked-out working-tree contents out from
under this session. No foreign file was ever staged or committed by this
session — `git status`/`git diff --stat` were checked before every `git
add`, and `git add` was always called with explicit paths, never `-A`/`.`.
Unit 4's commit (`a60d73f`) is confirmed to contain exactly its own 4
intended files (`git show --stat`). Unit 2 ended up isolated in its own
`git worktree` (`/Users/macos/Code/Projects/todo-ia-plf-02`) partway
through, which stopped further collisions for the rest of the session.

### Issues found

None blocking.
