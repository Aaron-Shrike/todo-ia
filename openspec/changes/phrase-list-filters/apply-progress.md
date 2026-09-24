# Apply Progress: Saved-Phrase List Filters

Source of truth: `tasks.md` (Units 1-4), `design.md`. This file tracks
apply-phase execution batch by batch.

> **Reconstruction note (Unit 3 session)**: this file existed with a Unit 1
> section at the start of that session (read in full at session start) but
> had disappeared from the working tree by the time Unit 3 finished (it was
> never git-tracked — `git log`/`git show HEAD` confirm it was never
> committed). This repo's working tree is shared live across concurrent
> agents (Units 1/2/3/4 on sibling branches, same checkout), so this was
> most likely clobbered by the Unit 2 agent's own concurrent file
> operations, not something that session did. The Unit 1 section below is
> reconstructed verbatim from that session's own earlier read of the file
> (before it vanished), not re-derived or guessed.

> **Merge/reconciliation note (orchestrator, PR #48)**: this file hit an
> add/add git conflict when merging the tracker (which had Unit 4's
> section, landed via PR #49) into Unit 3's branch (which had the
> reconstructed Unit 1 section + Unit 3's own section). Both sides created
> this same path independently, unaware of each other — expected fallout of
> the feature-branch-chain strategy (each unit's apply session only writes
> its own branch's copy). Resolved by combining both sides' real content
> into the single running document below, in unit order (1 → 2 → 3 → 4). No
> content from either side was dropped.

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
| `services/api/tests/integration/test_pgvector_repository.py` | Modified | Added pure-logic (no-DB) tests for `_status_predicate`, `_contains_pattern`, `build_list_page_query` (including the "byte-identical to the pre-Unit-1 query when unfiltered" proof design.md requires), `build_count_list_query`. |
| `services/api/tests/integration/test_schema.py` | Modified | Added `_index_exists` helper and `TestListFilterStatusIndexMigration`, asserting the partial index exists after `upgrade head` and is gone after `downgrade base`. |

### TDD Cycle Evidence

| Task | RED | GREEN | REFACTOR | Notes |
|---|---|---|---|---|
| 1.1 `ListFilters`/`NO_FILTERS`/Protocol | N/A (pure type addition; see below) | Implemented alongside 1.2/1.4 | — | Protocol changes are structural (no runtime enforcement); driven RED by 1.4's contract-suite tests importing `ListFilters` and calling the new `list_page(filters=...)`/`count_filtered` signatures, same pattern this codebase used for `ListCursor`/`Page` (no dedicated `test_contracts.py`). |
| 1.2 in-memory adapter | Confirmed: 7 new contract-suite tests failed with `TypeError: ... got an unexpected keyword argument 'filters'` before the adapter change | Confirmed: `pytest tests/contract_suite -m "not integration and not slow"` → 20 passed | Ran full unit suite (310 passed) after | Real pytest RED→GREEN, executed in-session. |
| 1.3 pgvector adapter (pure SQL-shape) | Confirmed: `ImportError: cannot import name '_contains_pattern'` before the adapter change | Confirmed: 9/9 passed in `tests/integration/test_pgvector_repository.py` (marked `integration`, runs without a DB — pure string-builder logic) | ruff/mypy clean after | Real pytest RED→GREEN, executed in-session. |
| 1.3 pgvector adapter (DB-backed `list_page`/`count_filtered`) | Not executed as pytest RED (session sandbox — see below) | Not executed as pytest GREEN (session sandbox — see below) | — | Verified instead by hand-executing the exact rendered SQL against seeded data in a scratch `phrases_test` DB. |
| 1.5 migration `0002` + lifecycle test | Not executed as pytest RED (session sandbox) | Not executed as pytest GREEN (session sandbox) | — | Verified by hand-applying the migration's literal SQL (`CREATE INDEX` / `DROP INDEX`): index present after upgrade, absent after downgrade, definition matches the migration exactly. |

**Post-apply re-verification (orchestrator, this session)**: the DB-backed
tests above (`test_schema.py`, `test_list_page_pgvector.py`, plus Unit 2's
`test_list_filters_pgvector.py`) were later re-run for real via pytest
against the live Postgres container, after resolving a local port conflict
(this machine's native PostgreSQL 16 install was shadowing Docker's default
5432 — see Engram `discovery/native-postgres-port-conflict`; fixed via
`DB_HOST_PORT` in `.env`, no code change). Result: **28/28 passed**. The
"could not run this session" caveats below are historical and no longer
block anything.

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
  "strasse"). Implemented as two assertions instead: an already-folded
  query ("strasse") matches an already-folded stored value, and a raw
  un-folded query ("straße") does NOT match it — proving neither adapter
  performs its own casefolding, consistent with design.md's stated
  rationale for choosing `LIKE` over `ILIKE`.

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
                                    # calls this internally
```

## Unit 2: API wiring, EXPLAIN guard, OpenAPI/types regen — DONE

Branch: `feat/plf-02-api-wiring` (child of `feat/plf-01-backend-filters`,
stacked). Implemented `status`/`q`/`min_score` on `GET /phrases`, the
`force_generic_plan` EXPLAIN guard proving the partial index survives a
generic query plan, and regenerated `docs/openapi.json`/
`apps/web/src/types/api.ts`. Full detail lives on that branch's own
`apply-progress.md` (this worktree, being independent per the
feature-branch-chain strategy, does not have it merged in here yet — see
that branch/PR #47 directly). Test results at the time: 340 passed
(up from 310 after Unit 1), ruff/mypy/import-linter clean, 6/6
`test_openapi.py` passed. Real diff ~614 non-generated lines, recorded as
an accepted `size:exception` in `tasks.md` (user-reviewed).

## Unit 3: Frontend filter controls — DONE

Branch: `feat/plf-03-frontend-filters` (child of tracker
`feat/phrase-list-filters` DIRECTLY, per design.md: "Unit 3 is independent
of Units 1-2" — not stacked on Unit 1 or Unit 2's branches).

Independent of Units 1-2 per design.md/tasks.md's own notes:
`ListPhrasesParams` in `client.ts` is hand-written (not derived from the
generated `api.ts` OpenAPI schemas Unit 2 regenerates), and every frontend
test injects a fake `fetchImpl`/`listPhrases`. The exact query-param names
(`status`, `q`, `min_score`) were taken from `design.md`'s "Frontend"
section and Unit 1's "What Unit 2 needs" notes above, which already fix
those names/shapes independently of Unit 2's router code having landed.

### Files changed

| File | Action | What was done |
|---|---|---|
| `apps/web/src/lib/api/client.ts` | Modified | `ListPhrasesParams` gained `status?: "unique" \| "duplicate_confirmed"`, `q?: string`, `minScore?: number`; `listPhrases()` serializes them as `status`/`q`/`min_score` query params, only when defined. |
| `apps/web/src/lib/api/client.test.ts` | Modified | Two new cases: all three filter params encoded together; no filter params sent when `{}` is passed. |
| `apps/web/src/features/phrases/hooks/useDebouncedValue.ts` | Created | Generic `useState`/`useEffect`+`setTimeout`/`clearTimeout` debounce hook (`useDebouncedValue<T>(value, delayMs): T`). Debounces, not throttles — the value-clearing special case ("clearing applies immediately") is NOT inside this hook; it lives in `PhraseList.tsx`'s own `qDraft.trim() === "" ? "" : debouncedQ` composition, per design.md's exact snippet. |
| `apps/web/src/features/phrases/hooks/useDebouncedValue.test.ts` | Created | 5 tests: initial value, no update before delay, updates at delay, debounce-not-throttle (timer resets on every change), timer cleared on unmount. |
| `apps/web/src/features/phrases/constants.ts` | Modified | Added `LIST_FILTER_DEBOUNCE_MS = 300`. |
| `apps/web/src/features/phrases/components/PhraseListFilters.tsx` | Created | Presentational filter bar: status `<select>` (`Todas`/`Única`/`Duplicado confirmado`, status rendered FIRST — most prominent control per the confirmed UX decision), text `<input>` (`maxLength` = phrase max), min-score `<input type="number" min=0 max=100 step=1>` whose `onChange` sends `percent / 100` (a `[0,1]` fraction) up, or `null` when cleared. Purely controlled/presentational. |
| `apps/web/src/features/phrases/components/PhraseListFilters.test.tsx` | Created | 9 tests: status-select-first DOM order, option labels/default, `onStatusChange`/`onTextChange`/`onMinScoreChange` wiring, `maxLength` cap, placeholder from copy, percent→fraction conversion, clearing sends `null`, displayed value is a rounded percent, number-input bounds. |
| `apps/web/src/i18n/copy.es.ts` | Modified | New `filters` namespace (`statusLabel`, `statusAll`, `textLabel`, `textPlaceholder`, `minScoreLabel`); `list.emptyFiltered`; `button.clearFilters`. Status select's "Única"/"Duplicado confirmado" options reuse the EXISTING `badge.*` keys (no duplication). |
| `apps/web/src/i18n/copy.es.test.ts` | Modified | Extended the verbatim-comparison table with the same new keys. |
| `apps/web/src/features/phrases/components/PhraseList.tsx` | Modified | Filter state (`statusFilter`, `qDraft`, `minScore`) owned here; `debouncedQ = useDebouncedValue(qDraft, LIST_FILTER_DEBOUNCE_MS)`; `appliedQ = qDraft.trim() === "" ? "" : debouncedQ` (clearing applies immediately, only typing waits); `applied`/`appliedKey` built from active filters only; `filtersRef` kept current every render; `fetchedKey` ref skips the initial (unfiltered) refetch on mount; a `generation` ref-counter guards `refresh()`/`loadMore()` responses against being applied out of order. `refresh()` keeps its exact public signature — existing call sites (`PhraseWorkspace.onSaved`, Reintentar) are UNCHANGED and now transparently respect whatever filters are active. `loadMore()` sends `{...filtersRef.current, cursor}` and shares the same generation guard. Render: `PhraseListFilters` always renders; the zero-items+idle empty state now branches on `hasActiveFilters` — filtered shows `copy.list.emptyFiltered` + a "Limpiar filtros" button; unfiltered still shows the original `copy.list.empty`. |
| `apps/web/src/features/phrases/components/PhraseList.test.tsx` | Modified | New `describe("filters")` block, 9 tests (fake timers). All 15 pre-existing tests in this file still pass unmodified. |
| `apps/web/src/features/phrases/components/phrases.module.css` | Modified | Added `.filterBar`, `.filterField`, `.filterSelect`/`.filterInput`, `.emptyStateFiltered`. |
| `openspec/specs/phrase-ui/spec.md` | Modified | Mirrored the three ADDED requirements from `specs/phrase-ui/spec.md` (delta) verbatim — inserted after "Infinite scroll over the saved list" and before "Spanish copy table"; extended the copy table. |
| `openspec/changes/phrase-list-filters/tasks.md` | Modified | Marked 3.1-3.5 `[x]`, added a Verify-line DONE note. |

### TDD Cycle Evidence

| Task | RED | GREEN | REFACTOR | Notes |
|---|---|---|---|---|
| 3.1 `client.ts` params | Confirmed: new `client.test.ts` case failed — `url` was `"http://api.test/phrases"` instead of the filtered URL (params silently dropped) | Confirmed: `npx vitest run src/lib/api/client.test.ts` → 14/14 passed | None needed | Real vitest RED→GREEN, executed in-session. |
| 3.2 `useDebouncedValue` | Confirmed: `Failed to resolve import "./useDebouncedValue"` (module did not exist) | Confirmed: `npx vitest run .../useDebouncedValue.test.ts` → 5/5 passed | None needed | Real vitest RED→GREEN. |
| 3.3 `copy.es.ts` additions | Confirmed: `copy.es.test.ts` failed — actual `copy` object missing `filters`/`list.emptyFiltered`/`button.clearFilters` keys | Confirmed: `npx vitest run src/i18n/copy.es.test.ts` → 1/1 passed | None needed | Real vitest RED→GREEN. |
| 3.3 `PhraseListFilters.tsx` | Confirmed: `Failed to resolve import "./PhraseListFilters"` (component did not exist) | Confirmed: `npx vitest run .../PhraseListFilters.test.tsx` → 9/9 passed | None needed | Real vitest RED→GREEN. |
| 3.4/3.5 `PhraseList.tsx` wiring | Confirmed: 9 new filter-scenario tests failed with `TestingLibraryElementError: Unable to find a label with the text of: Estado` (filter bar not yet rendered); the 15 pre-existing tests in the same file still passed at this point | Confirmed: `npx vitest run .../PhraseList.test.tsx` → 24/24 passed after wiring | Fixed 4 of the 9 new tests that initially used `waitFor` under `vi.useFakeTimers()` (RTL's `waitFor` polls with real timers internally and hung at 5000ms once timers were faked) — switched to explicit `act(async () => { await Promise.resolve(); })` microtask flushes. Also fixed 2 TypeScript errors where `client.listPhrases.mockClear()` was called on a `Pick<PhraseApiClient, "listPhrases">`-typed value with no mock methods — kept the `vi.fn(...)` reference in a separately-typed local instead. | Real vitest RED→GREEN, executed in-session; both intermediate failures were diagnosed and fixed for real. |

### Test results (Unit 3 apply session)

```
cd apps/web && npx vitest run
→ Test Files  13 passed (13)
→ Tests  202 passed (202)

cd apps/web && npx tsc --noEmit
→ (no output — clean)
```

### Deviations from design.md

- `PhraseListFilters`'s `onMinScoreChange` prop is typed to deliver the
  ALREADY-CONVERTED `[0,1]` fraction (or `null`), not the raw percent —
  design.md's own prose ("It sends `percent / 100`") followed literally.
- `useDebouncedValue.ts` is a plain generic debounce hook with NO special
  case for "clearing applies immediately" — that logic lives entirely in
  `PhraseList.tsx`'s `qDraft.trim() === "" ? "" : debouncedQ` line.
- `PhraseListFilters`'s text-input `maxLength` default duplicates
  `PhraseForm.tsx`'s `ENV_MAX_LENGTH`-computation pattern locally, because
  `PhraseForm.tsx` does not export that constant and Unit 3's scope does
  not include modifying `PhraseForm.tsx`.

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

This repo has one working directory, not per-unit git worktrees, at the
time Units 1/3/4 ran concurrently. Mid-session, another agent's `git
checkout` (observed switching HEAD to `feat/plf-03-frontend-filters`, and
at another point uncommitted edits to
`services/api/src/app/modules/phrases/api/schemas.py` and
`tests/unit/phrases/test_schemas.py` appeared — Unit 2's live WIP) silently
changed this branch's checked-out working-tree contents out from under
this session. No foreign file was ever staged or committed by this session
— `git status`/`git diff --stat` were checked before every `git add`, and
`git add` was always called with explicit paths, never `-A`/`.`. Unit 4's
commit (`a60d73f`) is confirmed to contain exactly its own 4 intended files
(`git show --stat`). Unit 2 ended up isolated in its own `git worktree`
(`/Users/macos/Code/Projects/todo-ia-plf-02`) partway through, which
stopped further collisions for the rest of the session.

### Issues found

None blocking.
