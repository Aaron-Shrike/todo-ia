# Tasks: Saved-Phrase List Filters

Source of truth: `design.md` (Architecture Decisions, SQL, File Changes, Testing Strategy), the three delta specs under `specs/*/spec.md`, `proposal.md`.
Strict TDD is ON: inside every unit write RED (failing test) -> GREEN -> REFACTOR locally, then commit RED+GREEN squashed per unit (one green, bisectable commit). Tests and docs ship in the same unit as the behaviour they cover.

## Review Workload Forecast

| Field | Value |
|---|---|
| Estimated changed lines | ~1,450-1,600 across 4 units (largest ~510 incl. generated files, none of the 4 individually under ~400 with generated snapshots counted) |
| 400-line budget risk | High (as a single change); Medium-High per unit |
| Chained PRs recommended | Yes |
| Suggested split | PR 1: backend filter contracts + both adapters + migration + contract suite -> PR 2 (base PR 1): API wiring + EXPLAIN guard + OpenAPI/`api.ts` regen -> PR 3 (independent): frontend filter UI + copy -> PR 4 (independent): ADR-016 + decision-log test |
| Delivery strategy | ask-on-risk |
| Chain strategy | pending — orchestrator decision (stacked-to-main vs feature-branch-chain), not made here |

Decision needed before apply: Yes
Chained PRs recommended: Yes
Chain strategy: pending
400-line budget risk: High

Notes:
- Budget is `additions + deletions`. `docs/openapi.json` (~80-150 lines) and `apps/web/src/types/api.ts` (~20-40 lines) are generated; Unit 2's estimate includes them because no exclusion convention has been agreed for this change yet (unlike the archived `phrase-validation` change, which excluded generated files only "if the reviewer agrees"). Confirm with the reviewer before opening PR 2; if agreed, Unit 2's real diff drops to ~360-460.
- Unit 3 (frontend) is independent of Units 1-2: `ListPhrasesParams` in `client.ts` is hand-written, not derived from the generated `api.ts` schemas, and every frontend test injects a fake `fetchImpl`. It can be authored, tested and reviewed in any order relative to the backend units; only a real end-to-end deploy needs the backend params to exist first.
- Unit 4 (ADR-016 + decision-log test) is independent of Units 1-3 (docs + one assertion). Sequenced last to match the archived `phrase-validation` precedent (docs/ADRs cite already-shipped behaviour), not because of a hard dependency.
- If any unit measures over 400 on the actual diff, split at the seam named in its Verify line rather than requesting `size:exception` first — same rule the archived change used.

### Suggested Work Units

| Unit | Goal | Likely PR | Notes |
|---|---|---|---|
| 1 | `ListFilters` contract, both adapters filtered, migration `0002`, contract-suite filter cases | PR 1 | No dependencies |
| 2 | Query-param validation, router wiring, EXPLAIN guard (incl. `force_generic_plan`), OpenAPI/`api.ts` regen | PR 2 | Needs Unit 1 merged or authored-ahead against it |
| 3 | Filter controls, debounce hook, filtered counter/empty state, copy | PR 3 | Independent of 1-2 (see Notes) |
| 4 | ADR-016, decision-log test (5 -> 6), README summary link | PR 4 | Independent of 1-3 (see Notes) |

### Dependency and parallelism

Unit 1 has no dependencies. Unit 2 needs `ListFilters`, `count_filtered` and both adapters' builders from Unit 1 to exist before its 422/EXPLAIN tests can pass. Units 3 and 4 can be authored in parallel with Units 1-2 and with each other; merge order only matters for Unit 1 -> Unit 2. Sole bottleneck: Unit 2 blocks on Unit 1.

---

## Unit 1: Filter contracts and repository adapters (~475, PR 1)

Commit: `feat(phrases): filterable list_page and count_filtered on both repository adapters`. Rollback: revert; no callers changed yet (`NO_FILTERS` default keeps every existing call site valid).
Covers (phrase-management): filter-by-status/text/AND scenarios, total-reflects-filter, cursor-stays-filter-agnostic (repository level); "Filter status index" ADDED requirement's migration-lifecycle scenario.
- [ ] 1.1 RED then GREEN `services/api/src/app/modules/phrases/contracts.py`: `ListFilters` frozen dataclass (`status: ValidationStatus | None`, `text: str | None`, `min_score: float | None`), module-level `NO_FILTERS = ListFilters()` (D1, avoids ruff B008), `PhraseRepository.list_page(..., *, filters: ListFilters = NO_FILTERS)`, new `count_filtered(filters) -> int`, `count_all()` re-expressed as `count_filtered(NO_FILTERS)`; update `__all__`.
- [ ] 1.2 RED then GREEN `adapters/in_memory_repository.py`: `_passes(row, filters)` (status equality; `filters.text in row.normalized_text`; `row.similarity_score is not None and row.similarity_score >= filters.min_score`, matching SQL three-valued NULL semantics); filtered `list_page`/`count_filtered`.
- [ ] 1.3 RED then GREEN `adapters/pgvector_repository.py`: `_LIST_TEXT_PREDICATE`, `_LIST_MIN_SCORE_PREDICATE`, `_status_predicate` (D4: enum-only SQL literal, never bound), `_list_where`, `build_list_page_query`/`build_count_list_query` (D6: real, EXPLAIN-able variants per flag combination), `_contains_pattern` (LIKE-escapes `\`, `%`, `_`), `count_filtered`.
- [ ] 1.4 RED then GREEN `tests/contract_suite/repository_contract.py`: `_new_phrase(status, score, neighbour)` helper; `ListPageContractSuite` filter cases registered for BOTH adapters — status-only, text-only (incl. literal `%`/`_`/`\`, `q="ß"` matching stored `"strasse"`), min_score-only (NULL excluded, `>=` boundary), AND-combination, full cursor walk under a filter, `total == count_filtered ==` filtered size on every page.
- [ ] 1.5 `services/api/migrations/versions/0002_list_filter_status_index.py`: `CREATE INDEX phrases_duplicate_confirmed_created_at_id_idx ON phrases (created_at DESC, id DESC) WHERE validation_status = 'duplicate_confirmed'` (D7: plain `CREATE INDEX`, no `CONCURRENTLY`) with working `downgrade`; extend `tests/integration/test_schema.py` (or a small dedicated test) asserting the index exists after `upgrade head` and is gone after `downgrade base`.
- Verify: `pytest tests/unit tests/contract_suite -m "not integration" -q`; `pytest -m integration tests/contract_suite tests/integration/test_schema.py -q` (needs `db` up); `lint-imports`. Seam if over budget: split 1.4's contract-suite cases into their own follow-up commit inside this unit.

## Unit 2: API wiring, EXPLAIN guard, OpenAPI/types regen (~460-560, PR 2, base PR 1)

Commit: `feat(api): GET /phrases status/q/min_score query params with 422 validation and EXPLAIN guard`. Rollback: revert; new params are optional, older clients unaffected.
Covers (api-contract): all `GET /phrases` filter/422/AND/total/cursor scenarios; (phrase-management): "Partial index used for the rare status" and "Unfiltered and status=unique paths unaffected" scenarios.
- [ ] 2.1 RED then GREEN `api/schemas.py`: `query_score()` (`Annotated[float, Field(ge=0, le=1, allow_inf_nan=False)]`), `query_text(max_length)` (`AfterValidator` raising `PydanticCustomError("string_too_long", ...)` with `details.max_length`); `api/router.py::list_phrases` gains `status: ValidationStatus | None`, `q: query_text(phrase_max_length) | None`, `min_score: query_score() | None`, passed to `container.list_phrases`.
- [ ] 2.2 RED then GREEN `application/list_phrases.py`: normalize `q` as `comparison_form(display_form(q))` (D2), blank -> `None`; build `ListFilters`; call `count_filtered(filters)`. `tests/unit/phrases/test_list_phrases.py`: blank/whitespace `q` treated as absent, casefold normalization, `None` passthrough.
- [ ] 2.3 RED then GREEN `tests/contract/test_phrases_endpoints.py`: `status=bogus` -> 422; `min_score=1.1`/`nan` -> 422; over-length `q` -> 422 `VALIDATION_ERROR`; a valid combo passes through and `data.total` matches the filtered count; `q` containing `%`/`_` matched literally end-to-end.
- [ ] 2.4 Create `tests/integration/test_list_filters_pgvector.py`: seed a skewed table per `explore-db-findings.md`, `ANALYZE`; `EXPLAIN` for `status=duplicate_confirmed` (with and without cursor, plus the count) uses `phrases_duplicate_confirmed_created_at_id_idx`, no Seq Scan — **including under `SET plan_cache_mode = force_generic_plan`**, which guards D4's enum-literal-not-bound-param decision; unfiltered builder output byte-identical to today's query (no plan regression on the default path).
- [ ] 2.5 Regenerate `docs/openapi.json` via `app.openapi()` per `tests/contract/test_openapi.py`'s docstring, then run `make types` to regenerate `apps/web/src/types/api.ts`; confirm `test_snapshot_matches_docs_openapi_json` and the CI drift guard pass.
- Verify: `pytest -m "unit or contract" tests/unit tests/contract -q`; `pytest -m integration tests/integration/test_list_filters_pgvector.py -q`; `pytest tests/contract/test_openapi.py -q`.

## Unit 3: Frontend filter controls (~430, PR 3, independent)

Commit: `feat(phrase-ui): status/text/min-score filter controls with debounced text input`. Rollback: revert; unfiltered list behaviour unchanged.
Covers (phrase-ui): all three ADDED requirements — filter controls, filtered counter/empty state, filter copy keys.
- [x] 3.1 RED then GREEN `apps/web/src/lib/api/client.ts` (+ `client.test.ts`): `ListPhrasesParams` gains `status?`, `q?`, `minScore?`, serialized as `status`/`q`/`min_score`; only defined values are serialized.
- [x] 3.2 RED then GREEN `apps/web/src/features/phrases/hooks/useDebouncedValue.ts` (new, + test): `useState` + `useEffect`/`setTimeout`/`clearTimeout`; `constants.ts` gains `LIST_FILTER_DEBOUNCE_MS = 300`.
- [x] 3.3 RED then GREEN `apps/web/src/features/phrases/components/PhraseListFilters.tsx` (new, presentational, + test): status `<select>` (`Todas`/`Única`/`Duplicado confirmado`), text input (`maxLength` = phrase max), min-score `<input type="number" min=0 max=100 step=1>` sending `percent/100`; `apps/web/src/i18n/copy.es.ts` (+ test): status label/options, text label/placeholder, min-score label, `emptyFiltered`, `clearFilters`, all in neutral Spanish, none hardcoded outside the copy module.
- [x] 3.4 RED then GREEN `apps/web/src/features/phrases/components/PhraseList.tsx` (+ test): filter state (`debouncedQ`, `appliedKey`, `fetchedKey`/`generation` guard per design.md); `refresh()` reused unchanged for "page 1 with current filters"; `loadMore` sends `{...filtersRef.current, cursor}`; filtered `{loaded}/{total}` counter; filtered empty state with a "Limpiar filtros" action; `phrases.module.css` filter-bar styles.
- [x] 3.5 Frontend scenario tests (Vitest, fake timers, injected client): debounce fires once after 300ms, not per keystroke; status/min-score refetch immediately and reset to page 1; a stale response is dropped (generation guard); `refresh()` after save keeps active filters; clear-filters resets all three controls and refetches unfiltered from page 1; the query string matches the active combination.
- Verify: `cd apps/web && npm test`. **DONE** — `npx vitest run` (202/202 passed) and `npx tsc --noEmit` (clean), see `apply-progress.md`'s Unit 3 section.

## Unit 4: Decision log — ADR-016 (~66, PR 4, independent)

Commit: `docs(decisions): add ADR-016 list filters, decision log now six entries`. Rollback: revert; drop `docs/decisions/ADR-016-list-filters.md`, restore `test_decision_log.py` and `README.md`.
Covers (phrase-management): "Beyond the brief decision log" MODIFIED requirement (five entries -> six), all four of its scenarios.
- [ ] 4.1 Create `docs/decisions/ADR-016-list-filters.md` (front-matter `type: beyond-brief`): states the original brief called filtering out of scope, the decision to add `status`/`q`/`min_score` to `GET /phrases`, the rationale, and the deferred `pg_trgm` trigger conditions (~100k rows or filtered p95 > 100ms, per `proposal.md`).
- [ ] 4.2 RED then GREEN `services/api/tests/unit/test_decision_log.py::test_exactly_five_beyond_brief_adrs_at_top_level`: rename to `test_exactly_six_beyond_brief_adrs_at_top_level`, update the expected count from 5 to 6 and the assertion message from "ADR-001..005" to "ADR-001..005, ADR-016"; confirm `_top_level_adr_files()`'s `Path.glob("*.md")` admits `ADR-016-list-filters.md` at top level (not under `technical/`).
- [ ] 4.3 Update `README.md`'s decision-log summary section with ADR-016's one-line summary and relative link; `test_readme_links_every_adr` already covers this generically (no test code change needed).
- Verify: `pytest services/api/tests/unit/test_decision_log.py -q`.
