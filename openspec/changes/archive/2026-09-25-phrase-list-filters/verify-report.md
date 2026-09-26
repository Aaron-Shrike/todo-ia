# Verify Report: Saved-Phrase List Filters

**Verdict: PASS WITH WARNINGS**

Verified against `proposal.md`, `design.md`, all three delta specs
(`phrase-management`, `api-contract`, `phrase-ui`), `tasks.md`, and
`apply-progress.md`. Code was read directly across the 4 chained branches
(read-only, no checkout performed in the shared main worktree) and tests
were re-executed for real in this session, not trusted from
`apply-progress.md`'s claims alone.

## Branches inspected

| Unit | Branch | Commit | How inspected |
|---|---|---|---|
| 1 (backend contracts/adapters/migration) | `feat/plf-01-backend-filters` | `4da03ed` | Via Unit 2's worktree (`/Users/macos/Code/Projects/todo-ia-plf-02`), which has Units 1+2 combined |
| 2 (API wiring/EXPLAIN guard/OpenAPI) | `feat/plf-02-api-wiring` | `30adccf` | Same worktree, direct file reads + real pytest runs |
| 3 (frontend) | `feat/plf-03-frontend-filters` | main worktree HEAD | Direct file reads in `/Users/macos/Code/Projects/todo-ia`, real vitest/tsc runs |
| 4 (ADR-016/decision-log) | `feat/plf-04-decision-log` | `3267be8` | `git show feat/plf-04-decision-log:<path>` from the main worktree (no checkout) |

## Spec compliance matrix

### `phrase-management`

| Requirement/Scenario | Evidence | Status |
|---|---|---|
| MODIFIED "List phrases" — filters, filter-aware `total`, filter-agnostic cursor | `contracts.py:175-194` (`ListFilters`/`NO_FILTERS`), `list_phrases.py:52-59` (builds `ListFilters`, calls `list_page(..., filters=filters)`) | PASS |
| MODIFIED decision log — six `beyond-brief` entries | `git show feat/plf-04-decision-log:docs/decisions/ADR-016-list-filters.md` exists, front-matter `type: beyond-brief`, states the reversal + `pg_trgm` deferral triggers verbatim per spec's "ADR-016 documents the reversal" scenario. `git ls-tree feat/plf-04-decision-log docs/decisions` → exactly 6 top-level `.md` files (ADR-001..005, ADR-016). `test_decision_log.py::test_exactly_six_beyond_brief_adrs_at_top_level` exists and asserts count==6 with message "ADR-001..005, ADR-016" | PASS |
| ADDED "Filter status index" — migration `0002` | `services/api/migrations/versions/0002_list_filter_status_index.py` (Unit 2 worktree): `CREATE INDEX phrases_duplicate_confirmed_created_at_id_idx ON phrases (created_at DESC, id DESC) WHERE validation_status = 'duplicate_confirmed'`, plain `CREATE INDEX` (D7), working `downgrade`. Byte-for-byte match to `design.md` lines 108-116. Migration lifecycle test (`test_schema.py`) run for real: 1 passed | PASS |

### `api-contract`

| Requirement/Scenario | Evidence | Status |
|---|---|---|
| `GET /phrases` gains `status`/`q`/`min_score`, AND semantics | `router.py:274-294` (Unit 2 worktree): three new params passed to `container.list_phrases` | PASS |
| Invalid `status`/`min_score`/`q` → 422 `VALIDATION_ERROR` | `schemas.py:71-103`: `query_score()` (`Field(ge=0, le=1, allow_inf_nan=False)`), `query_text(max_length)` raising `PydanticCustomError("string_too_long", ...)`; `ValidationStatus` enum param rejects unknown values via pydantic | PASS |
| `q` matched via `LIKE...ESCAPE`, not `ILIKE`, per design's rationale | `pgvector_repository.py:154` (`_LIST_TEXT_PREDICATE = r"normalized_text LIKE :text_pattern ESCAPE '\'"`), `_contains_pattern` at lines 225-234 escapes `\`, `%`, `_` (backslash first) | PASS |
| `total` filter-aware | `list_page` (pgvector, lines 368-400 and in-memory, lines 165-189) both call `count_filtered(filters)` for `total`, not a cached/unfiltered count | PASS |
| Cursor unchanged/filter-agnostic | `_LIST_CURSOR_PREDICATE` carries only `(created_at, id)`, no filter fields; `list_phrases.py` decodes the cursor independent of filters | PASS |
| `docs/openapi.json` regenerated with new params | `rg` over `docs/openapi.json` (Unit 2 worktree) shows `"name": "status"` (L488), `"name": "q"` (L504), `"name": "min_score"` (L520). `pytest tests/contract/test_openapi.py -q` → 6 passed (snapshot + drift guard) | PASS |

### `phrase-ui`

| Requirement/Scenario | Evidence | Status |
|---|---|---|
| ADDED filter controls (status/text/min-score) | `PhraseListFilters.tsx` (main worktree): status `<select>` first, text `<input maxLength>`, min-score `<input type="number" min=0 max=100 step=1>` | PASS |
| Debounced text, immediate status/min-score refetch | `PhraseList.tsx:112-119` (`debouncedQ = useDebouncedValue(qDraft, LIST_FILTER_DEBOUNCE_MS)`, clearing applies immediately via `qDraft.trim() === "" ? "" : debouncedQ`); `appliedKey` effect at lines 179-184 fires on any change to `applied` | PASS |
| Filtered empty state + "Limpiar filtros" | `PhraseList.tsx:262-286`: `hasActiveFilters` branches to `copy.list.emptyFiltered` + `clearFilters()` button, vs. unfiltered `copy.list.empty` | PASS |
| Copy keys mirrored in `copy.es.ts` and `copy.es.test.ts` | `rg` confirms `filters.statusLabel/statusAll/textLabel/textPlaceholder/minScoreLabel`, `list.emptyFiltered`, `button.clearFilters` present verbatim in both files | PASS |

## Cross-cutting checks

- **Both adapters implement `ListFilters`/`count_filtered` identically per the contract suite**: `repository_contract.py` (Unit 2 worktree) has 7 filter scenarios (`test_list_page_filters_by_status_only`, `..._by_text_only`, `..._case_folding...`, `..._wildcard_characters_literally`, `..._by_min_score_only`, an AND-combination case, a filtered cursor-walk case). Ran for real against BOTH adapters:
  - In-memory (part of the full non-integration suite): included in the 410 passed.
  - pgvector (DB-backed): `pytest tests/integration/test_list_page_pgvector.py -k filter -q` → **7 passed**.
  This directly contradicts `apply-progress.md`'s Unit 1 claim that pgvector-backed filter tests "could not be executed" in a sandboxed session — they run cleanly in this environment (port 5433). Good news, not a regression.
- **`status` literal-in-SQL (D4), never a bind parameter**: `pgvector_repository.py:163-171`, `_status_predicate` returns `f"validation_status = '{status.value}'"` sourced only from the closed `ValidationStatus` enum — confirmed real, not aspirational.
- **`force_generic_plan` EXPLAIN guard actually tests D4**: `test_list_filters_pgvector.py:177-219`, `test_status_filter_uses_the_partial_index_under_a_forced_generic_plan` runs `SET plan_cache_mode = force_generic_plan`, `PREPARE`/`EXECUTE` 5 times (to also exercise psycopg3's real auto-prepare threshold), then asserts the partial index is still chosen. Ran for real: **passed**.
- **Unit 2 `size:exception`**: legitimate. `tasks.md`'s recorded note states the real diff (~614 non-generated lines) had no natural sub-seam under strict TDD (`query_score`/`query_text`, router wiring, and `ListPhrases`'s filter/normalize logic all had to land together for any test to pass), and states the user reviewed and chose the exception live. This matches the Review Workload Guard's allowance for an "explicitly accepted `size:exception`." Not a blocker.

## Real test execution (this session, not paraphrased from `apply-progress.md`)

Backend, full suite, from `/Users/macos/Code/Projects/todo-ia-plf-02/services/api` (port 5433):
```
$ DATABASE_URL=postgresql+psycopg://todo_ia:todo_ia@localhost:5433/todo_ia \
  /Users/macos/Code/Projects/todo-ia/services/api/.venv/bin/python -m pytest -q
...
FAILED tests/unit/similarity/test_sentence_transformers.py::test_the_real_model_loads_and_reports_384_dimensions
ERROR tests/slow/test_calibration.py::test_the_real_model_is_deterministic
ERROR tests/slow/test_calibration.py::test_duplicate_pairs_score_at_or_above_the_threshold
ERROR tests/slow/test_calibration.py::test_distinct_pairs_score_below_the_threshold
ERROR tests/slow/test_calibration.py::test_expected_weakness_pairs_are_reported_not_gated
ERROR tests/slow/test_calibration.py::test_evidence_file_was_written
1 failed, 410 passed, 2 warnings, 5 errors in 46.33s
```
All 6 failures/errors are `ModuleNotFoundError: No module named 'sentence_transformers'` in `tests/unit/similarity/test_sentence_transformers.py` and `tests/slow/test_calibration.py` — pre-existing, unrelated to this change (no PyTorch wheel for macOS x86_64 + Python 3.14 on this machine). Confirmed matches the expected/known baseline; not flagged as a blocker.

EXPLAIN guard + migration lifecycle, targeted:
```
$ pytest -q tests/integration/test_list_filters_pgvector.py tests/integration/test_schema.py -k "ListFilter or list_filter"
tests/integration/test_list_filters_pgvector.py .....                    [ 83%]
tests/integration/test_schema.py .                                       [100%]
6 passed, 9 deselected in 2.05s
```

pgvector-backed filter contract suite:
```
$ pytest tests/integration/test_list_page_pgvector.py -q -k filter
.......                                                                  [100%]
7 passed, 6 deselected in 1.90s
```

OpenAPI snapshot/drift guard:
```
$ pytest tests/contract/test_openapi.py -q
......                                                                   [100%]
6 passed in 0.99s
```

Static analysis (Unit 2 worktree, main worktree's venv):
```
$ ruff check src tests   → All checks passed!
$ mypy src               → Success: no issues found in 44 source files
$ lint-imports            → Contracts: 5 kept, 0 broken.
```

Frontend, from `/Users/macos/Code/Projects/todo-ia/apps/web`:
```
$ npx vitest run
 Test Files  13 passed (13)
      Tests  202 passed (202)

$ npx tsc --noEmit
(no output — clean)
```

## Issues

### CRITICAL

None.

### WARNING

1. **`tasks.md` reconciliation needed before archive.** The user's brief stated tasks.md shows "all 18 tasks across 4 units, now all marked `[x]`" — this is NOT true of any single copy of the file. Verified directly:
   - Main worktree (`feat/plf-03-frontend-filters`, current HEAD): only `3.1`-`3.5` are `[x]`; `1.1`-`1.5`, `2.1`-`2.5`, `4.1`-`4.3` are still `[ ]`.
   - Unit 2 worktree (`feat/plf-02-api-wiring`): `1.1`-`1.5` and `2.1`-`2.5` are `[x]`; `3.x`/`4.x` are `[ ]`.
   - Unit 4 branch (`feat/plf-04-decision-log`, via `git show`): `4.1`-`4.3` are `[x]`; `1.x`/`2.x`/`3.x` are `[ ]`.

   Summed across the 4 branches, all 18 tasks ARE done and checked (5+5+5+3=18), each in its own branch's copy — this is an artifact of the feature-branch-chain strategy (each unit's `sdd-apply` session only had its own unit's file in its working tree) and is not itself a functional defect; all underlying work is real and independently verified above. But no single reconciled `tasks.md` with all 18 checked exists yet. Recommend `sdd-archive` (or whichever step merges the chain to `develop`) reconcile `tasks.md` into one file with all 18 boxes checked as part of the merge, so the archived record doesn't understate completion on any individual branch's history.

2. **`apply-progress.md`'s own "could not run" claims are stale/overcautious**, specifically for Unit 1's pgvector-backed contract-suite filter scenarios and Unit 2's EXPLAIN-guard/migration-lifecycle tests. Both suites run cleanly in this environment once pointed at port 5433 (this session confirmed all of them pass for real, see above). Not a code defect — flagging only so `apply-progress.md` isn't taken at face value as "still needs a DB-capable re-run"; that re-run has now happened and passed.

### SUGGESTION

None.

## Success Criteria (from `proposal.md`) — spot-checked

- Each filter/combination returns only matching rows, reachable via cursor: confirmed via the 7 contract-suite scenarios (both adapters) and the API contract tests.
- `total` equals filtered count on every page: confirmed (`count_filtered` used for `total` in both adapters).
- Invalid `status`/`min_score`/over-length `q` → 422: confirmed via schema validators.
- `q` containing `%`/`_` matched literally: confirmed via `_contains_pattern` + contract-suite wildcard test.
- `EXPLAIN` for `status=duplicate_confirmed` uses the partial index, no Seq Scan: confirmed, including under `force_generic_plan`.
- Both adapters pass the same filter contract cases: confirmed (7/7 each).
- UI changes restart pagination, filtered counter/empty state: confirmed.
- Six `beyond-brief` ADRs, decision-log test updated: confirmed.

## Skill Resolution

`none` — no project skill in `.atl/skill-registry.md` matched this task, per the orchestrator's own instruction; proceeded without project skill injection.
