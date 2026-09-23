# Verify Report: phrase-validation

Accumulates one section per verified unit.

---

## Verification Report - Unit 3

> Recovered from a `git stash` (untracked file, never committed on any branch) and merged into
> this accumulating file. **Both CRITICAL findings below were resolved** by the Unit 3 fix pass
> documented in `apply-progress.md`'s "Unit 3 fix pass (sdd-verify CRITICAL findings)" section:
> the untested "Threshold changed via env" scenario got a real RED-confirmed test, and the
> 1083-line budget overrun was resolved via a genuine 4-way split (PR #11 closed unmerged; PRs
> #12-#15 — Units 3a-3d — merged to `main` instead). This section is kept verbatim as the
> historical record of what the first verify pass found; it does not describe the code's current
> state on `main`/`develop`.

**Change**: phrase-validation
**Unit**: Unit 3 — Validate, list-matches, save use cases (tasks 3.1-3.4)
**Version**: N/A
**Mode**: Strict TDD

### Completeness
| Metric | Value |
|--------|-------|
| Unit 3 tasks total | 4 |
| Unit 3 tasks complete | 4 (3.1, 3.2, 3.3, 3.4 all [x]) |
| Unit 3 tasks incomplete | 0 |

### Build & Tests Execution
**Build**: N/A (no build step at this unit; backend is a library, no compile step)

**Tests**: PASS 122 passed (backend tests/unit + tests/contract_suite) / PASS 1 passed (frontend)
```text
cd services/api && .venv/Scripts/python.exe -m pytest -m "not integration and not slow" -q
-> 122 passed in 0.19s   (matches apply-progress.md's claimed 122/122, re-run independently)

cd services/api && .venv/Scripts/python.exe -m pytest tests/unit tests/contract_suite -q
-> 122 passed in 0.19s

cd apps/web && npm test
-> 1 passed (vitest)
```

**Lint/Type/Import checks** (all re-run independently, all cd services/api first):
```text
ruff check .          -> All checks passed!
mypy src              -> Success: no issues found in 28 source files
lint-imports.exe      -> Contracts: 5 kept, 0 broken.
  (application-no-adapters-or-api contract KEPT)
```
Import-statement spot check on phrases/application/{validate_phrase,list_matches,save_phrase,_shared}.py:
only app.modules.phrases.contracts, app.modules.phrases.domain.*, app.modules.similarity.contracts
are imported -- zero adapter imports (no sqlalchemy, pgvector, sentence_transformers, fastapi).
Confirms lint-imports' verdict at the source level, not just by trusting the tool.

**Coverage** (changed application files, pytest --cov=app.modules.phrases.application):
| File | Line % | Missing |
|------|--------|---------|
| _shared.py | 100% | -- |
| validate_phrase.py | 100% | -- |
| list_matches.py | 100% | -- |
| save_phrase.py | 98% | L141 (elif neighbor is not None and score is not None branch inside _forced_conflict's conflict-payload build; narrow edge case, non-core) |

**PR #11** (gh pr view 11): state OPEN, base main, head feat/pv-03-use-cases, +1319/-7 (includes the docs(sdd) apply-progress commit on top of the 1083-line code commit). Not yet merged -- confirmed live via gh, matching the task context.

**Commit 55214c0**: single code commit on the branch (git log main..feat/pv-03-use-cases --oneline shows exactly 55214c0 + one docs-only follow-up 1b5ad74). Author Aaron Rojas, no Co-Authored-By line, no AI/Claude attribution anywhere in the commit body -- confirmed via git log -1 --format=%B. Squashed RED+GREEN per unit, per Strict TDD convention.

---

### TDD Compliance
| Check | Result | Details |
|-------|--------|---------|
| TDD Evidence reported | YES | Full table in apply-progress.md, Unit 3 section |
| All tasks have tests | YES | 4/4 tasks have dedicated test files |
| RED confirmed (tests exist) | YES | All 4 test files exist and were verified to fail pre-implementation per the evidence table (3 by direct execution, 1 -- task 3.2 -- retroactively confirmed and explicitly disclosed as a process deviation in the table itself) |
| GREEN confirmed (tests pass) | YES | 122/122 re-run independently in this verify session |
| Triangulation adequate | YES | 12 + 5 + 13 + 4 = 34 distinct cases across 4 tasks, matching the Covers line's scenario breadth |
| Safety Net for modified files | YES | All 4 are new files; safety-net counts (88 to 100 to 105 to 118 to 122) are internally consistent (88+12+5+13+4=122) |

**TDD Compliance**: 6/6 checks passed

---

### Test Layer Distribution
| Layer | Tests | Files | Tools |
|-------|-------|-------|-------|
| Unit | 34 (new) | 4 | pytest |
| Integration | 0 | 0 | n/a (deferred to Unit 5b per design.md's own Guard-2b assignment) |
| E2E | 0 | 0 | n/a |
| Total | 34 | 4 | |

---

### Changed File Coverage
| File | Line % | Uncovered Lines | Rating |
|------|--------|------------------|--------|
| application/_shared.py | 100% | -- | Excellent |
| application/validate_phrase.py | 100% | -- | Excellent |
| application/list_matches.py | 100% | -- | Excellent |
| application/save_phrase.py | 98% | L141 | Excellent |

**Average changed file coverage**: 99%

---

### Assertion Quality
No tautologies, no ghost loops, no assertion-without-production-call patterns found across
test_validate_phrase.py, test_list_matches.py, test_save_phrase.py, test_cache_interplay.py.
Call-count assertions on CountingRepo (find_nearest_calls == 0, etc.) are deliberate behavioral
verification of an explicit design invariant (design.md's Guard 2b: "the write path never reads HNSW"),
not incidental implementation-detail coupling -- not flagged.

**Assertion quality**: All assertions verify real behavior

---

### Quality Metrics
**Linter**: No errors (ruff check .)
**Type Checker**: No errors (mypy src, 28 files)

---

### Spec Compliance Matrix (Unit 3's Covers line)
| Requirement / Scenario | Test | Result |
|-------------|------|--------|
| SV Validation result shape: Empty store | test_empty_store_returns_null_verdict_and_empty_matches | COMPLIANT |
| SV Validation result shape: Best below threshold | test_best_below_threshold_reports_score_and_most_similar_with_empty_matches | COMPLIANT |
| SV Validation result shape: most_similar equals first match | test_most_similar_equals_first_match_when_matches_non_empty | COMPLIANT |
| SV Validation result shape: Statelessness | test_statelessness_nothing_persisted_after_validate | COMPLIANT |
| SV Complete ordered match set: Threshold zero | test_threshold_zero_admits_everything_but_only_first_page_is_returned | COMPLIANT |
| SV Threshold changed via env | none found -- no test injects a non-default, non-zero threshold and asserts result.threshold/is_duplicate against it; VerdictView.threshold is never asserted by ANY Unit 3 test | UNTESTED (CRITICAL) |
| SV Page consistency: Phrase saved between pages | test_returns_the_next_page_after_a_valid_cursor (basic continuation only; the specific "insert a higher-scoring phrase between pages" fixture is not reproduced) | PARTIAL |
| DC Exact duplicates: Confirmable | test_duplicate_confirmed_persists_with_the_recorded_metadata (uses a near-duplicate score, not literally the spec's case/whitespace-variant text, but exercises the identical code path) | COMPLIANT |
| SV Model failure and timeout: Provider raises | test_provider_failure_propagates_and_nothing_persists[EmbeddingUnavailable] (both use cases) | COMPLIANT |
| SV Model failure and timeout: Provider times out | test_provider_failure_propagates_and_nothing_persists[EmbeddingTimeout] (both use cases) | COMPLIANT |
| SV Model failure and timeout: Recovery | not directly tested in Unit 3; relies on Unit 2's FailingEmbedder one-shot-mode tests | PARTIAL |
| SV Embedding reuse: Validate then pages / Validate then save / Blind save | test_three_match_pages_keep_the_embedding_call_count_at_one, test_validate_then_save_share_one_embedding_call, test_embedding_is_reused_across_pages_with_a_warm_cache | COMPLIANT |
| DC Server-side re-validation: Similarity re-run despite warm cache | test_save_never_calls_find_nearest_only_the_exact_scan (counting proxy) | COMPLIANT |
| DC Server-side re-validation: Save does not use the approximate read | test_save_never_calls_find_nearest_only_the_exact_scan | COMPLIANT |
| DC Server-side re-validation: Save catches a duplicate the approximate index would miss | explicitly NOT implemented -- apply-progress.md deviation #1; deferred to Unit 5b's real pgvector recall-miss fixture per design.md's own Guard 2b | UNTESTED at Unit 3 (documented deferral, legitimate) |
| DC Explicit flag: Duplicate confirmed / Flag on a non-duplicate / Exact duplicate confirmable | test_duplicate_confirmed_persists_with_the_recorded_metadata, test_confirm_flag_on_a_non_duplicate_still_saves_as_unique | COMPLIANT |
| DC Explicit flag: Cancel saves nothing (backend: no call) | test_duplicate_without_confirmation_returns_a_conflict_and_persists_nothing (store unchanged after a 409) | COMPLIANT |
| DC 409 payload: Payload completeness | test_409_payload_carries_the_full_validate_shaped_match_page | COMPLIANT |
| DC 409 payload: Large match set on 409 | not tested at Unit 3 -- 120-match fixture only exercised through ListMatches/ValidatePhrase cache-interplay tests, not through SavePhrase's 409 path | PARTIAL |
| DC Failures never save: Model down on save / with confirmation / Timeout | test_provider_failure_on_save_propagates_and_persists_nothing (parametrized, asserts confirm_duplicate=True does not bypass) | COMPLIANT |
| DC Concurrency: Unique violation maps to 409 never 500 | test_duplicate_text_conflict_retries_once_in_a_fresh_uow_then_persists -- proves the retry MECHANISM but never seeds a real competing phrase, so find_nearest_exact finds nothing on retry and the "score 1.0, full validate-shaped details" half of the scenario is not exercised here | PARTIAL |
| DC Concurrency: Persistent violation still yields 409 | test_always_raising_duplicate_conflict_still_returns_409_never_raises -- same caveat as above | PARTIAL |
| DC Concurrency: Confirmed save cannot violate the index | not applicable at unit level -- needs real concurrent Postgres transactions; correctly deferred to Unit 5b, not claimed by Unit 3's Covers line | N/A |
| PM Persistence: Unique / Below-threshold / Confirmed duplicate metadata | test_save_without_validating_when_unique_persists_the_phrase, test_below_threshold_neighbour_is_recorded_on_a_unique_save, test_duplicate_confirmed_persists_with_the_recorded_metadata | COMPLIANT |

**Compliance summary**: 15/22 fully COMPLIANT, 5 PARTIAL, 1 UNTESTED (claimed-but-not-covered), 1 legitimately deferred.

---

### Correctness (Static Evidence)
| Requirement | Status | Notes |
|------------|--------|-------|
| Reconciliation rule (matches[0] wins) | Implemented | validate_phrase.py L46-49; spy test + 5-trial property test both pass |
| Tail rule (widened-bound truncation forces has_more=False) | Implemented | _shared.py::build_matches_page; boundary test at 0.79994/0.7999 passes |
| Two isolation levels (REPEATABLE_READ read-only for validate, READ COMMITTED for save) | Implemented | Matches design.md D17/ADR-015 exactly (Isolation.REPEATABLE_READ in validate_phrase.py L39; default READ_COMMITTED in save_phrase.py L72) |
| Save embeds before opening any transaction | Implemented | save_phrase.py L60-61, before _attempt's with self._uow_factory() |
| Save derives verdict from find_nearest_exact only, never find_nearest | Implemented | save_phrase.py L74; proven by CountingRepo.find_nearest_calls == 0 |
| Bounded retry (_MAX_ATTEMPTS = 2) then forced-conflict fallback | Implemented | save_phrase.py L98-118 |
| confirm_duplicate=True does not bypass provider failures | Implemented | test_provider_failure_on_save_propagates_and_persists_nothing passes confirm_duplicate=True |
| _shared.py leaks no adapter imports into application layer | Confirmed | Import list is phrases.contracts, phrases.domain.*, similarity.contracts only |

---

### Coherence (Design)
| Decision | Followed? | Notes |
|----------|-----------|-------|
| "The 409 body carries a complete validate response" (design.md) | Yes | build_matches_page shared by ValidatePhrase page 1 and SavePhrase's _conflict |
| Guard 2b ("Save never uses HNSW... recall-miss test") assigned to integration marker / pgvector adapter | Yes, correctly deferred | apply-progress.md's deviation #1 matches design.md L676-680 exactly -- this is a real pgvector-vs-exact-scan integration guard, not reproducible on the in-memory adapter |
| find_nearest-never-called proof: raising spy (tasks.md 3.3) vs. call-counter (delivered) | Equivalent-or-stronger | A counting proxy that wraps and delegates every call is provably at least as strong as a raising spy: a raising spy only proves non-invocation if the exception is guaranteed to propagate uncaught; a call counter is unconditional (increments regardless of whether the caller catches downstream exceptions) and gives an exact count, not just a yes/no. No weaker guarantee introduced. |

---

### Issues Found

**CRITICAL**:
1. Review budget: 1083 changed lines, 2.7x the hard 400-line cap (vs. the ~350 estimate). This is not merely an estimate miss -- tasks.md's own governing instruction for this change states: "If a unit exceeds 400, split at the seam named in its Notes instead of asking for size:exception." apply-progress.md evaluated the named seam (moving the 409-payload build to Unit 7) and correctly concluded it would only save ~50-70 lines, not closing the ~680-line gap -- but then neither executed an alternative split (e.g., ValidatePhrase+ListMatches in one PR, SavePhrase+cache-interplay in a second) nor escalated to the user for a decision under the change's own resolved ask-on-risk delivery strategy. It simply documented and shipped over-budget. This compounds Unit 2's precedent (732 lines, 332 over the cap) to roughly double the absolute overrun (683 over the cap) with no re-confirmed human decision on record for this specific, larger overshoot. A partial re-split was checked by this verifier and does not cleanly solve the problem either (application code alone is ~369 lines, close to the original estimate; the bulk of the growth is legitimate, dense unit-test triangulation -- 714 lines of tests/spies), which somewhat mitigates the finding but does not excuse skipping the mandatory split-or-escalate step. Blocks: PR #11 should not merge as-is without an explicit human sign-off on the budget exception (tasks.md's own process does not currently permit size:exception, so either an actual split or an explicit amendment to that rule is needed).
2. "SV Threshold changed via env" scenario is claimed as covered in Unit 3's Covers line ("Threshold changed via env (policy injected)") but has zero covering tests. No test in test_validate_phrase.py, test_list_matches.py, test_save_phrase.py, or test_cache_interplay.py ever constructs a SimilarityPolicy with a non-default, non-zero threshold (e.g. 0.95) and asserts VerdictView.threshold or the resulting is_duplicate boundary against it. In fact VerdictView.threshold is never asserted by any test in this unit at all -- only threshold=0.80 (default) and threshold=0.0 (a different, already-covered scenario) are exercised. Per this skill's Decision Gate ("Spec scenario has no passing covering test -> CRITICAL UNTESTED"), this is a genuine gap, not a documented deviation.

**WARNING**:
1. DC Concurrency scenarios "Unique violation maps to 409 never 500" and "Persistent violation still yields 409" are tested only via an artificial ConflictRepo that raises on add() without ever inserting a real competing row -- so find_nearest_exact finds nothing on retry in either test, and the scenario's actual payload requirement ("full validate-shaped details (score 1.0)") is never exercised together with the retry mechanism. The retry mechanism itself is proven correct, and the 409-payload-with-real-data path is proven correct separately (test_409_payload_carries_the_full_validate_shaped_match_page) -- but the two are never combined, unlike the literal spec scenario. Not documented as a deviation in apply-progress.md.
2. "Save catches a duplicate the approximate index would miss" is listed in the Covers line as covered "(spy level)" but apply-progress.md's own deviation #1 confirms it is NOT implemented in Unit 3 -- the wording in the Covers line overstates what shipped. The deferral itself is legitimate and well-justified (matches design.md's own Guard-2b assignment to the pgvector integration suite), but the Covers line should have said "deferred to Unit 5b," not implied coverage exists.
3. "Recovery" (Model failure and timeout x3) is claimed as use-case-level coverage but not directly tested by a Unit 3 test; it relies on Unit 2's FailingEmbedder one-shot-mode tests already proving the adapter recovers, which is a reasonable inference but not a Unit-3-owned test.
4. DC "Large match set on 409" (120-match fixture through SavePhrase's 409 path) is not tested -- the 120-match fixture exists in test_cache_interplay.py but is only driven through ValidatePhrase/ListMatches, never through SavePhrase's _conflict path, so pagination behavior on a large 409 payload specifically is unverified at Unit 3.

**SUGGESTION**:
1. save_phrase.py line 141 (the elif neighbor is not None and score is not None branch inside _forced_conflict's payload build) is the one uncovered line in an otherwise 99%-covered changeset -- a narrow "always-raising retry with a genuine below-threshold neighbor" edge case. Worth a follow-up test, low priority.
2. Unit 3's "Page consistency: Phrase saved between pages" is covered only by a basic next-page-continuation test, not the specific fixture named in the spec (inserting a higher-scoring phrase between page requests and asserting no duplicate/skip). Low risk since the underlying keyset mechanism is already exhaustively covered by Unit 2d's contract suite; flagged for completeness only.

### Verdict
**PASS WITH WARNINGS** -- all 122+1 tests are genuinely green, TDD discipline and coverage are excellent, isolation-level/reconciliation/tail-rule/import-boundary correctness all hold up under independent re-verification, and the commit is clean (single squashed commit, no AI attribution). However, the unquestioned 2.7x budget overrun without following the change's own mandatory split-or-escalate rule, and one genuinely untested spec scenario claimed as covered, are real findings that should be resolved (or explicitly accepted by a human) before this unit is considered fully closed -- they do not, however, block starting Unit 4 (which has no code dependency on Unit 3).

---

## Verification Report - Unit 4

**Change**: phrase-validation
**Unit**: 4 - Schema, Alembic raw-SQL migrations, compose db/migrate, minimal API Dockerfile stage
**Branch**: feat/pv-04-schema-migrations, base develop, PR #17 (open, not merged)
**Version**: N/A
**Mode**: Strict TDD

### Completeness
| Metric | Value |
|--------|-------|
| Tasks total (Unit 4) | 4 (4.0-4.3) |
| Tasks complete | 4 |
| Tasks incomplete | 0 |

All four sub-tasks are checked [x] in tasks.md and match the code state on this branch.

### Build & Tests Execution (all commands re-run directly, not trusted from apply-progress.md)

**Docker/compose** (docker compose down -v then docker compose up -d db migrate):
```
todo-ia-db-1        Up (healthy)
todo-ia-migrate-1   Exited (0)
```
migrate log: "Running upgrade  -> 0001, create phrases table". Matches design.md and the PR's
claimed evidence.

**Schema inspection** (docker compose exec db psql -U todo_ia -d todo_ia -c "\d phrases") -
confirmed directly, not taken on trust:
- Indexes: phrases_pkey (PK btree), phrases_created_at_id_idx btree(created_at DESC, id DESC),
  phrases_embedding_hnsw_idx hnsw(embedding vector_cosine_ops), phrases_unique_normalized_text_uidx
  UNIQUE btree(normalized_text) WHERE validation_status = 'unique' - no plain/unconditional unique
  index exists.
- Check constraints: phrases_confirmed_has_neighbor, phrases_metadata_paired - both present,
  text matches design.md verbatim.
- FK: phrases_most_similar_phrase_id_fkey ... ON DELETE RESTRICT - present.
- All of the above match design.md's DDL (lines 493-529) exactly.

**Unit tests**: PASS - 123 passed, 9 deselected (pytest -m "not integration and not slow" -q) -
matches the PR's claimed count exactly.

**Integration tests**: PASS - 9 passed (pytest -m integration tests/integration/test_schema.py -q) -
matches the PR's claimed count exactly.

**Lint/type/import**:
- ruff check src tests migrations -> All checks passed!
- mypy src -> Success: no issues found in 28 source files
- lint-imports -> Contracts: 5 kept, 0 broken.

**alembic downgrade base - run for real, not just via the test suite** (per task instruction 5):
against the todo_ia database (migrated by the migrate compose service), ran
python -m alembic downgrade base directly, then inspected with psql \d phrases and
SELECT extname FROM pg_extension WHERE extname='vector': phrases table absent, vector
extension absent, alembic_version bookkeeping table is the only relation left. Matches the spec
scenario "Downgrade to base" exactly. (Environment was then re-upgraded to head and finally torn
down with docker compose down -v, leaving no side effects on the branch or its test results.)

**Coverage**: not configured for this project (no coverage tool detected) - skipped, not a failure.

### Spec Compliance Matrix
| Requirement / Scenario | Test | Result |
|---|---|---|
| No plain unique index | \d phrases (manual, this verify pass) + behaviorally by the two uniqueness tests below | PARTIAL - true and structurally confirmed, but no automated test asserts it directly (see Issues) |
| Metadata is immutable history | No UPDATE path exists anywhere in the Unit 4 diff (schema-only, no app code yet) | PARTIAL - true by omission, not asserted by a dedicated test |
| Embedding dimension mismatch fails fast (typmod reader; boot wiring in 8) | None shipped - test was written, verified green, then cut in the review-budget trim; only the query text survives in apply-progress.md prose | UNTESTED at end of Unit 4 (deferral is legitimate per tasks.md, but nothing currently backs it in the repo) |
| Second unique row with same text rejected | test_second_unique_row_with_same_text_is_rejected | COMPLIANT |
| Confirmed duplicate with same text accepted | test_confirmed_duplicate_with_same_text_is_accepted | COMPLIANT |
| Different text is unaffected | test_different_text_is_unaffected | COMPLIANT |
| Migration lifecycle (partial index present/absent) | TestMigrationLifecycle + this pass's manual downgrade base | COMPLIANT |
| Upgrade from empty database | test_upgrade_from_empty_creates_table_and_extension | COMPLIANT |
| Downgrade to base | test_downgrade_to_base_drops_table_and_extension + manual re-run this pass | COMPLIANT |
| phrases_metadata_paired CHECK | test_check_constraint_rejects_unpaired_metadata[score_without_neighbor], [neighbor_without_score] | COMPLIANT |
| phrases_confirmed_has_neighbor CHECK | test_check_constraint_rejects_unpaired_metadata[confirmed_without_neighbor] | COMPLIANT |
| ON DELETE RESTRICT | None - no test attempts a DELETE on a referenced row | UNTESTED (structurally confirmed via \d phrases only; see Issues) |

**Compliance summary**: 8/11 Covers-line items fully compliant with a passing test; 2 PARTIAL
(true but not directly asserted); 1 UNTESTED-by-design (typmod reader, deferred); 1 UNTESTED gap
found by this verify pass (ON DELETE RESTRICT).

### Correctness (Static Evidence)
| Item | Status | Notes |
|---|---|---|
| 0001_create_phrases.py DDL | Implemented | Structurally equivalent to design.md's DDL (table, both CHECKs, FK, HNSW index, created_at index, partial unique index), re-confirmed via live \d phrases |
| HNSW guard (_assert_hnsw_is_supported) | Implemented | Reads extversion, raises RuntimeError below 0.5.0; matches task 4.2's literal "fail fast if HNSW unsupported" |
| env.py URL resolution | Implemented | Config value (tests) or DATABASE_URL (CLI/compose); no silent fallback |
| docker-compose.yml db/migrate | Implemented | Matches design.md's Docker Compose table for these two services; api/web correctly deferred to Unit 14 |
| services/api/Dockerfile migrate stage | Implemented | No torch/model, per design's "slice 4 ships a minimal migrate-capable stage" |
| infra/db/init.sql | Implemented | Creates phrases_test for the integration suite, separate from the main todo_ia db |

### Coherence (Design)
| Decision | Followed? | Notes |
|---|---|---|
| Raw-SQL migrations only, no autogenerate | Yes | target_metadata = None in env.py; migration is hand-written |
| phrases_unique_normalized_text_uidx is a partial index for integrity, not performance | Yes | Matches design.md's framing verbatim in code comments |
| ON DELETE RESTRICT (not SET NULL) on most_similar_phrase_id | Yes | Matches design.md's stated rationale (nulling only that column would violate phrases_metadata_paired) |
| Slice 4 independent of slices 1-3, needs only slice 0 | Yes | No cross-imports into phrases/similarity application code |
| api/web compose services out of scope (Unit 14) | Yes | Not present in docker-compose.yml, correctly deferred |

### TDD Compliance
| Check | Result | Details |
|-------|--------|---------|
| TDD Evidence reported | Yes | "TDD Cycle Evidence (Unit 4)" table present in apply-progress.md |
| All tasks have tests | Yes | 4.2/4.3 have test files; 4.0/4.1 are verification/infra tasks with no test file, reasonably N/A (4.1 verified by 4.3 + docker compose ps, both re-run in this pass) |
| RED confirmed (tests exist) | Yes | tests/integration/test_schema.py exists, 9 tests, all classes present as described |
| GREEN confirmed (tests pass) | Yes | 9/9 passed on direct re-run in this environment |
| Triangulation adequate | Yes | 3 DB-uniqueness scenarios, 3-case parametrize + positive control for CHECKs, 2-case migration lifecycle |
| Safety Net for modified files | Yes / N/A (new) | All Unit 4 files are new; only pyproject.toml (additive-only, 3 new deps) and tasks.md (checkbox update) were modified |

**TDD Compliance**: 6/6 checks passed.

### Test Layer Distribution
| Layer | Tests | Files | Tools |
|-------|-------|-------|-------|
| Unit | 123 (unchanged) | unchanged | pytest |
| Integration | 9 (new) | 1 (tests/integration/test_schema.py) | pytest + real Postgres/pgvector via Docker Compose |
| Contract | 0 (new) | - | - |
| Total | 132 | | |

### Assertion Quality
No tautologies, no ghost loops, no assertion-without-production-code-call found in
test_schema.py. All 9 tests issue real INSERT/DELETE-adjacent SQL or real Alembic
upgrade/downgrade calls and assert on real driver exceptions (IntegrityError, constraint name
in excinfo.value.orig) or real schema-introspection queries (to_regclass, pg_extension).
**Assertion quality**: All assertions verify real behavior.

**Consolidation cross-check** (task instruction 7): apply-progress.md claims "four
CHECK-rejection tests" were consolidated into "one parametrized test (3 cases)". Verified this is
not a coverage loss: the two CHECK constraints admit exactly three distinct, non-redundant
violation shapes - (1) score set / neighbor null, (2) neighbor set / score null (both violate
phrases_metadata_paired regardless of validation_status), and (3) duplicate_confirmed with
both null (violates phrases_confirmed_has_neighbor only, since the pair-null case satisfies
phrases_metadata_paired). Any 4th combination (e.g. duplicate_confirmed with only one of
score/neighbor set) would still raise on phrases_metadata_paired - the same code path as cases
(1)/(2), just with a different validation_status value - so it is redundant, not a distinct
scenario. The trim's "same coverage" claim holds.

### Quality Metrics
**Linter**: No errors
**Type Checker**: No errors
**Import Linter**: 5 kept, 0 broken

### Issues Found

**CRITICAL**: None.

**WARNING**:
1. ON DELETE RESTRICT has no behavioral test. It is named explicitly in Unit 4's Covers line
   ("Persistence CHECKs ... ON DELETE RESTRICT") but no test in test_schema.py (or anywhere in
   the repo) attempts to DELETE a phrases row that is referenced by another row's
   most_similar_phrase_id to confirm the FK actually rejects it. It is structurally present
   (confirmed via \d phrases in this pass) but not behaviorally proven. Low real-world risk since
   no DELETE endpoint exists anywhere in the planned API surface (spec's "Metadata is immutable
   history" implies rows are never mutated or deleted), but it is a genuine gap against what the
   unit's own Covers line promised to exercise. Not flagged as a deviation in apply-progress.md's
   5 documented deviations - this is a new finding from this verify pass.
2. Typmod-reader artifact is fully absent from the shipped codebase, only documented in
   prose. apply-progress.md's deviation note says the query is "preserved here verbatim" for
   Unit 8 to reuse - but it exists only as a paragraph inside apply-progress.md, not as any
   reusable function, module, or test in src/ or tests/. The deferral itself is legitimate and
   consistent with 4.2/4.3's literal task text (neither mentions a typmod check; only the Covers
   line's parenthetical implies one, and tasks.md's own "Scenario coverage flags" section assigns
   "boot wiring" to Unit 8). However, tasks.md's traceability table phrasing ("typmod reader
   planned in unit 4, boot check wired in unit 8") is in mild tension with the outcome (nothing
   from Unit 4 survives into the repo for Unit 8 to reuse except prose). Recommend Unit 8's apply
   pass re-derive or directly copy the query from apply-progress.md rather than assuming a Unit 4
   code artifact exists to import.
3. Spec scenarios "No plain unique index" and "Metadata is immutable history" are true but not
   directly asserted by a dedicated test. "No plain unique index" is evidenced only indirectly
   (two uniqueness tests behave as expected under the partial predicate); nothing queries
   pg_indexes/pg_constraint to assert structurally that no unconditional unique index exists.
   "Metadata is immutable history" is true only because no UPDATE code path exists yet anywhere in
   the codebase (Unit 4 ships no application code) - there is no regression test that would catch
   a future unit accidentally introducing an UPDATE on these columns. Low risk today, worth a
   structural assertion if a later unit (5a/5b or beyond) touches persistence code.

**SUGGESTION**:
1. Consider adding a lightweight pg_indexes/pg_constraint introspection test asserting exactly
   one unique index exists on normalized_text and it is partial - would turn the "No plain unique
   index" scenario from behaviorally-implied to structurally-asserted, and would catch regressions
   cheaply if a future migration ever adds a second index.

### Verdict
**PASS WITH WARNINGS** - all 4 sub-tasks complete and verified by direct re-execution (not taken
on faith): migration applies and downgrades cleanly against real Postgres/pgvector, schema matches
design.md exactly, all reported test/lint/type/import counts reproduced exactly, no AI
co-authorship in either commit, and the 5 documented deviations are genuine, low-risk, and
consistent with tasks.md's literal scope. Three WARNING-level gaps found by this pass (not
previously flagged in apply-progress.md): ON DELETE RESTRICT lacks a behavioral test, the
typmod-reader artifact is not actually preserved as reusable code (only prose), and two
Covers-line scenarios are true-by-omission rather than directly asserted. None are CRITICAL; none
block merging this PR or proceeding to Unit 5a, but the ON DELETE RESTRICT and typmod-reader
points are worth a follow-up note for Unit 8's apply pass.

### Deviation Review (task instruction 6)
- **script.py.mako omission**: confirmed safe. No task from Unit 5a through Unit 16 in tasks.md
  invokes `alembic revision` or `alembic revision --autogenerate`; the project's only migration
  (0001) is hand-authored raw SQL per design.md's stated approach, and no future unit adds a new
  migration file via the CLI generator. script.py.mako is genuinely unused.
- **alembic.ini logging omission**: confirmed cosmetic. env.py never calls `fileConfig(...)` and
  has no logging dependency; no test asserts on Alembic's CLI log output. Migrations run
  identically with or without the [loggers]/[handlers]/[formatters] sections.
- Both deviations are correctly classified as low-risk in apply-progress.md; neither is
  scope-cutting in disguise.

### Commit Attribution Check (task instruction 8)
`git log develop..feat/pv-04-schema-migrations` shows 2 commits (`6086d42`, `f982e02`); neither
commit message contains a Co-Authored-By or other AI/Claude attribution line. Diffstat against
develop (`git diff --shortstat develop..feat/pv-04-schema-migrations`) is exactly
"11 files changed, 604 insertions(+), 5 deletions(-)", matching PR #17's reported numbers exactly.

---

## Verification Report - Unit 5a

**Change**: phrase-validation
**Unit**: 5a - Exact keyset find_matches (pgvector adapter)
**Branch**: feat/pv-05a-find-matches, base develop, PR #18 (open, not merged, 672 additions / 20 deletions per gh pr view)
**Version**: N/A
**Mode**: Strict TDD

### Completeness
| Metric | Value |
|--------|-------|
| Tasks total (Unit 5a) | 3 (5a.1-5a.3) |
| Tasks complete | 3 |
| Tasks incomplete | 0 |

All three sub-tasks are checked [x] in tasks.md and match the code state on this branch.

### Build & Tests Execution (all commands re-run directly, not trusted from apply-progress.md)

**Docker** (db/migrate already up and healthy at session start; re-confirmed with docker compose up -d db migrate):
```
Container todo-ia-db-1       Healthy
Container todo-ia-migrate-1  Started
```

**Unit's own literal Verify line** (pytest -m integration tests/integration/test_find_matches.py tests/contract_suite -q):
7 passed, 8 deselected - matches apply-progress.md's claim exactly.

**Full integration suite** (pytest -m integration -q): 16 passed, 123 deselected - matches the
claimed 9 (Unit 4, unchanged) + 7 (new) exactly.

**Full unit suite** (pytest -m "not integration and not slow" -q): 123 passed, 16 deselected -
zero regression from Unit 4's 123-test baseline, confirmed by direct re-run, not taken on trust.

**Lint/type/import**:
- ruff check src tests -> All checks passed!
- mypy src -> Success: no issues found in 29 source files
- lint-imports -> Contracts: 5 kept, 0 broken.

**Coverage**: not configured for this project (no coverage tool detected) - skipped, not a failure.

### Contract-suite split - scrutinized directly (task instruction 1)

tasks.md's 5a.2 says "Register the pgvector adapter in tests/contract_suite/repository_contract.py
(same suite as in-memory)". The apply agent split the pre-existing single RepositoryContractSuite
into NearestNeighbourContractSuite (3 find_nearest/find_nearest_exact scenarios + the read-only-add
guard) and MatchesContractSuite (the 4 find_matches keyset scenarios), and registered pgvector
against MatchesContractSuite only. Verified independently, not taken on the apply agent's word:

- (a) Is find_nearest/read-only-add genuinely 5b-scope per design.md, not just the apply agent's own
  judgment call? Confirmed yes. Read design.md's "Why 5 and 6 split" section directly (not via
  apply-progress.md's paraphrase): "5a is pure query work against an existing schema, 5b adds the
  top-1 reads and the write-path primitives (incl. translating the ADR-006 unique violation into
  DuplicateTextConflict...)". This is the design's own stated seam, written before this unit was
  applied, not a post-hoc justification. tasks.md's own Unit 5a line independently says the same
  ("Seam: 5a is pure query work on the 0001 schema"). The apply agent quoted this correctly.
- (b) Did the in-memory adapter's own test count/behavior change at all? Confirmed zero regression,
  independently: git diff 38c6319 09966b6 -- services/api/tests/contract_suite/
  test_in_memory_repository.py services/api/tests/unit produced no output (byte-for-byte untouched
  file). Read the full diff of repository_contract.py directly: it is a pure mechanical split - the
  original class body is cut at the exact boundary between the read-only-add-guard test and the
  first find_matches test, renamed into two classes with zero edits to any test method body, then
  recomposed as class RepositoryContractSuite(NearestNeighbourContractSuite, MatchesContractSuite).
  Re-ran the full unit suite myself: 123 passed, matching the claimed before/after count.
- (c) Legitimate interpretation of "same suite," or under-delivery? Legitimate. The suite
  composition mechanism (RepositoryContractSuite, still the name in-memory subclasses, still all 8
  scenarios, still one shared _seed() helper and one shared vectors.py) is fully preserved; only
  which mixin a given adapter registers against changed, and that change tracks a seam the design
  document itself drew for the production code (5a ships no find_nearest/find_nearest_exact/
  lock_for_write - they are explicit NotImplementedError("... lands in Unit 5b") stubs). Registering
  pgvector against the full class as literally written would have required implementing Unit 5b's
  write-path primitives inside Unit 5a to satisfy the test file's structure - genuine scope creep the
  apply agent correctly declined. This is the same pattern Unit 2/2d used (restore/split at a named
  design seam) applied one level down, to a test file instead of production code. No under-delivery:
  every scenario tasks.md's Unit 5a Covers line actually lists gets a real, passing test against real
  Postgres.

### enable_indexscan SET LOCAL non-leak claim - verified directly (task instruction 3)

Read test_explain_shows_no_hnsw_and_no_offset_and_set_local_does_not_leak directly (not just
confirmed it exists). It does what it claims: sets enable_indexscan = off on connection A, captures
EXPLAIN of the real query, commits, then opens a second, separate connection and asserts SHOW
enable_indexscan reads back on (the session default) - this is the correct way to prove a SET LOCAL
(transaction-scoped) setting does not leak to a later statement, since a pooled connection reused by
a later request is indistinguishable from a fresh connection for this purpose. Re-ran the assertion
myself as part of the full suite (green).

### EXPLAIN-based "no HNSW / no OFFSET" claim - verified directly (task instruction 4)

The test builds its query via build_find_matches_query(has_cursor=True) - the exact function
PgVectorPhraseRepository.find_matches calls, exported specifically so the test never hand-copies the
SQL - then runs EXPLAIN against a 250-row corpus (> hnsw.ef_search 200, a non-vacuous guard) and
asserts "hnsw" not in plan_text.lower() and "OFFSET" not in plan_text against the real captured plan
rows, not a hand-typed expectation. Re-ran directly; plan output was not just inspected as an
assertion string in the source but reproduced independently via the separate
docs/evidence/exact-scan-timings.md measurement (see below), which shows the same plan shape (Seq
Scan -> top-N heapsort) on 500 and 10,000-row corpora.

### CAST(:q AS vector) deviation (task instruction 5)

Confirmed equivalent, not a behavior change. In PostgreSQL, CAST(expr AS type) and expr::type are the
same operation - :: is Postgres's own shorthand for the SQL-standard CAST, not a distinct cast
mechanism, so there is no parameter-binding or type-coercion difference at the database level. The
actual constraint was in SQLAlchemy's text() bind-parameter parser, which does not recognize a :name
token immediately followed by :: (it looks like a second bind-parameter reference); the fix addresses
that parser limitation, not a database-level semantic difference. apply-progress.md's TDD Cycle
Evidence table documents catching this as a genuine RED (ProgrammingError: syntax error at or near
":" before the fix) - consistent with a parser issue, not a query-planner issue.

### vectors.py 2-dim -> 384-dim zero-padding (task instruction 6)

Confirmed mathematically exact. Cosine distance is 1 - dot(u,v) / (|u| * |v|). Padding both u and v
with an equal-length all-zero suffix adds zero to the dot product (each new term is 0 * 0) and adds
zero under each norm's square root (each new term is 0^2), so both the dot product and both norms
are unchanged - cosine distance is unaffected, not merely approximately preserved. Confirmed no
silent behavior change to the in-memory adapter's tests from this shared-fixture edit: git diff on
test_in_memory_repository.py/tests/unit is empty (see above), and the full 123-test unit suite
passed identically on direct re-run.

### Oracle-agreement test - confirmed real, not stubbed (task instruction 7)

test_oracle_agreement_with_pure_python_cosine_within_1e5 opens a real engine.connect() against the
live Postgres/pgvector instance, inserts 5 random 384-dim unit vectors via repo.add() (a real INSERT
... RETURNING), queries them back via repo.find_matches (a real pgvector <=> operator evaluation, not
a mock), and compares each returned distance against similarity.contracts.cosine_distance (the
pure-Python oracle) with abs(match.distance - expected) < 1e-5. No mocking or stubbing anywhere in
the path from vector insertion to distance comparison. Re-ran directly; passed.

### exact-scan-timings.md evidence sanity-check (task instruction 8)

Read the file directly and independently re-ran EXPLAIN (ANALYZE, BUFFERS) on comparable row counts
(500 and 10,000, same vector_at_distance/PROBE fixture shape) via the full test suite's own
EXPLAIN-capturing test plus the same query building block used by that test. Both the file's captured
plans and my own re-run show the same shape: Seq Scan on phrases feeding a Sort with Sort Method:
top-N heapsort, no Index Scan, no hnsw reference - consistent with design.md's own description
("sequential scan plus a top-N sort"). The reported timings (0.529 ms @ 500 rows, 5.719 ms @ 10,000
rows) are plausible for an in-container Seq Scan at this row count and are explicitly flagged in the
file itself as "one local run, single sample... a proper ADR-008 measurement (Unit 16) should average
several runs" - an honest estimate label, not a claim of rigor it does not have.

### 399-line budget and consolidation claim (task instruction 9)

Independently re-measured: git diff --shortstat 38c6319 09966b6 -- services/api docs/evidence ->
434 insertions(+), 17 deletions(-) across 5 files. Subtracting docs/evidence/exact-scan-timings.md's
52 insertions (a generated-evidence file, not source/test code) yields exactly 382 insertions, 17
deletions = 399 changed lines across 4 files - matching apply-progress.md's claim to the line. This
mirrors Unit 4's own precedent of excluding generated content from its review-budget figure (Unit 4:
"2,838 insertions... 327 insertions excluding the generated [migration snapshot]"). One
WARNING-level observation: unlike Unit 4's phrasing, this unit's apply-progress.md never states the
exclusion explicitly ("399 changed lines... excluding the evidence file") - the reader has to
reconstruct it, as this pass did. Not deceptive (the evidence file's own line count is fully visible
in the diff and the file's own content is honest about being an estimate), but worth flagging for
consistency with Unit 4's more explicit phrasing.

The "merged two pgvector-plumbing tests into one" trim claim is confirmed accurate: reading
test_find_matches.py, test_explain_shows_no_hnsw_and_no_offset_and_set_local_does_not_leak is a
single test function that performs both the EXPLAIN/no-HNSW/no-OFFSET assertions and the SET LOCAL
non-leak assertion, sharing one 250-row seeded corpus - the natural merge point apply-progress.md
describes, with no coverage loss (both original assertions are present, just co-located).

### Commit attribution check (task instruction 10)

git log -3 on this branch shows 2 relevant commits (09966b6 feat, 456e11f docs); neither commit
message contains Co-Authored-By or any other AI/Claude attribution line.

### Spec Compliance Matrix
| Requirement / Scenario | Test | Result |
|---|---|---|
| Keyset match pagination: No OFFSET | test_explain_shows_no_hnsw_and_no_offset_and_set_local_does_not_leak | COMPLIANT |
| Keyset match pagination: Exact scan | test_explain_shows_no_hnsw_and_no_offset_and_set_local_does_not_leak | COMPLIANT |
| Complete ordered match set: All matches reachable / Exact page boundary / One over page boundary | MatchesContractSuite (inherited, exercised via TestPgVectorMatchesContract) | COMPLIANT |
| Complete ordered match set: Tie scores across a page boundary | test_bit_identical_ties_split_cleanly_across_a_page_boundary | COMPLIANT |
| Complete ordered match set: Displayed ties ordered by raw distance | test_displayed_ties_are_ordered_by_raw_distance | COMPLIANT |
| Complete ordered match set: Paging beyond the former approximate-index window (500 matches) | test_500_matches_page_through_completely_with_no_gaps_or_repeats | COMPLIANT |
| Complete ordered match set: Threshold zero / Custom page size | Covered by application-layer tests (Unit 3); repository-level widened-bound behavior exercised by the oracle/boundary tests | PARTIAL - repository-level behavior confirmed (max_distance=2.0 admits all in the oracle test); full threshold-zero/custom-page-size scenarios are Unit 3's application-layer responsibility, not re-tested at the repository layer in 5a (correct layering, not a gap) |
| Page consistency: Vector drift does not repeat or skip | test_perturbed_vector_paging_does_not_repeat_or_skip | COMPLIANT |
| Cosine: Rounding consistency (0.79996/0.79994 tail rule) | test_boundary_0_79996_in_0_79994_out_via_tail_rule | COMPLIANT |
| Cosine: Oracle agreement (1e-5, pgvector side) | test_oracle_agreement_with_pure_python_cosine_within_1e5 | COMPLIANT |
| Threshold zero admits everything (2.0 bound) | test_oracle_agreement_with_pure_python_cosine_within_1e5 (uses max_distance=2.0, returns all 5 seeded rows) | COMPLIANT |

**Compliance summary**: 10/11 Covers-line items fully COMPLIANT with a passing test against real
Postgres; 1 PARTIAL (threshold-zero/custom-page-size are correctly re-verified at the application
layer in Unit 3, not duplicated at the repository layer here - this is correct layering per
apply-progress.md's own note that find_matches "does NOT apply the rounded Decimal threshold or the
tail rule", not a coverage gap).

### Correctness (Static Evidence)
| Item | Status | Notes |
|---|---|---|
| find_matches SQL | Implemented | Matches design.md's SQL sample near-verbatim; sole diff is CAST(:q AS vector) vs :q::vector, confirmed equivalent (see above) |
| set_config('enable_indexscan','off',true) at method start | Implemented | Confirmed transaction-scoped, non-leaking (see above) |
| (bucket, id) keyset ordering | Implemented | ORDER BY bucket, id, bucket = floor(distance/1e-6), matches D16 |
| LIMIT :limit + 1 has_more probe | Implemented | has_more = len(rows) > limit in Python, matches design.md |
| add() / PgVectorUnitOfWork minimal seeding-only scope | Implemented | No DuplicateTextConflict mapping, no advisory lock - correctly deferred to 5b.2, documented as deviation 3 |
| find_nearest/find_nearest_exact/lock_for_write stubs | Implemented | NotImplementedError("... lands in Unit 5b"), correctly not claiming a contract not yet honored |

### Coherence (Design)
| Decision | Followed? | Notes |
|---|---|---|
| D1: find_matches forced exact scan via SET LOCAL enable_indexscan = off | Yes | Verified via EXPLAIN + non-leak test, re-run directly |
| D16: (bucket, id) keyset tolerance grid | Yes | KEY_EPSILON imported from similarity.contracts, _bucket() helper matches design.md's SQL floor(... / 1e-6) |
| "Why 5 and 6 split": 5a is pure query work, 5b owns write-path primitives | Yes | Confirmed by reading the design section directly, not via apply-progress.md's paraphrase (see above) |
| Application layer, not the adapter, owns rounding/tail-rule/Decimal comparison | Yes | find_matches returns raw distances only; test_boundary_0_79996_in_0_79994_out_via_tail_rule exercises the real _shared.build_matches_page from Unit 3, not a reimplementation |
| In-memory repository implements the identical (bucket, id) ordering ("shared contract suite covers it") | Yes | RepositoryContractSuite composition unchanged; MatchesContractSuite's 4 scenarios now exercise both adapters |

### TDD Compliance
| Check | Result | Details |
|-------|--------|---------|
| TDD Evidence reported | Yes | "TDD Cycle Evidence (Unit 5a)" table present in apply-progress.md |
| All tasks have tests | Yes | 5a.1/5a.2 share one test file (one RED/GREEN cycle per strict-tdd.md's squash rule); 5a.3 is a VERIFY-only measurement task, correctly N/A for RED/GREEN, matching Unit 4's 4.0 precedent |
| RED confirmed (tests exist) | Yes | tests/integration/test_find_matches.py exists; RED was confirmed by execution (file moved aside, ModuleNotFoundError, then restored) per apply-progress.md - a real technique, not merely claimed |
| GREEN confirmed (tests pass) | Yes | 7/7 new integration tests passed on direct re-run in this pass |
| Triangulation adequate | Yes | 4 MatchesContractSuite scenarios (tie, displayed-tie-ordering, 500-match paging, perturbed-vector) + 3 pgvector-only guards (EXPLAIN/SET-LOCAL, boundary tail-rule, oracle), each exercising a distinct code path |
| Safety Net for modified files | Yes | 9 pre-existing test_schema.py integration tests passing before this unit's changes, per apply-progress.md's TDD table |

**TDD Compliance**: 6/6 checks passed.

### Test Layer Distribution
| Layer | Tests | Files | Tools |
|-------|-------|-------|-------|
| Unit | 123 (unchanged) | unchanged | pytest |
| Integration | 16 (9 unchanged from Unit 4 + 7 new) | 2 (test_schema.py unchanged, test_find_matches.py new) | pytest + real Postgres/pgvector via Docker Compose |
| Contract | 4 of the 7 new (via inherited MatchesContractSuite) | shared repository_contract.py | pytest |
| Total | 139 | | |

### Assertion Quality
No tautologies, no ghost loops over possibly-empty collections (all seeded fixtures are non-empty,
counts are asserted directly), no assertion-without-production-code-call found in either
test_find_matches.py or the MatchesContractSuite mixin. All assertions exercise real production
code: real DB connections, the real find_matches SQL (via the exported build_find_matches_query,
never hand-copied), the real Unit 3 _shared.build_matches_page (not a reimplementation), and real
EXPLAIN plan text.
**Assertion quality**: All assertions verify real behavior.

### Quality Metrics
**Linter**: No errors
**Type Checker**: No errors
**Import Linter**: 5 kept, 0 broken

### Issues Found

**CRITICAL**: None.

**WARNING**:
1. The 399-line review-budget figure implicitly excludes docs/evidence/exact-scan-timings.md (52
   insertions) without an explicit "excluding the evidence file" caveat sentence the way Unit 4
   phrased its equivalent exclusion. The underlying math is correct and independently reconfirmed
   (382 + 17 = 399 across the 4 named code/test files), and nothing is hidden - the evidence file's
   diff is fully visible in git diff --stat - but the apply-progress.md prose should say so
   explicitly for future units' consistency, matching Unit 4's clearer phrasing.

**SUGGESTION**:
1. Consider a short explicit sentence in future units' review-budget sections stating which files
   are excluded from the changed-lines figure and why (generated evidence vs. reviewable code),
   mirroring Unit 4's "327 insertions excluding the generated [snapshot]" phrasing, to keep the
   convention self-documenting rather than requiring a verify pass to reconstruct it.

### Verdict
**PASS** - all 3 sub-tasks complete and verified by direct re-execution against real
Postgres/pgvector (not taken on faith): the literal Unit 5a Verify line reproduces 7 passed exactly,
the full integration suite reproduces 16 passed exactly, the full unit suite reproduces 123 passed
with zero regression, all lint/type/import checks are clean, no AI co-authorship in either commit.
The contract-suite split - the unit's most consequential design decision - was scrutinized directly
against design.md's own text (not apply-progress.md's paraphrase) and confirmed to be a legitimate,
purely mechanical decomposition of an existing design-documented seam, with zero behavioral change
to the in-memory adapter (confirmed via an independent git diff showing the in-memory-specific test
file is byte-for-byte untouched). The CAST(:q AS vector) deviation, the 384-dim zero-padding, the
SET LOCAL non-leak claim, the EXPLAIN-based no-HNSW/no-OFFSET claim, and the oracle-agreement test
were each independently verified against real Postgres, not trusted from the report. One WARNING
(documentation clarity on the review-budget exclusion, not a correctness issue) found by this pass;
no CRITICAL issues; nothing blocks merging PR #18 or proceeding to Unit 5b.

## Verification Report - Unit 5b

**Change**: phrase-validation
**Unit**: 5b - find_nearest, find_nearest_exact, unit of work, advisory lock (pgvector adapter)
**Branch**: feat/pv-05b-nearest-uow, base develop, PR #19 (open, not merged; 910 additions / 43 deletions per gh pr view, includes openspec doc updates alongside the 658/38 code diff)
**Version**: N/A
**Mode**: Strict TDD

### Completeness
| Metric | Value |
|--------|-------|
| Tasks total (Unit 5b) | 4 (5b.0-5b.3) |
| Tasks complete | 4 |
| Tasks incomplete | 0 |

All four sub-tasks are checked [x] in tasks.md and match the code on disk on this branch.

### Build and Tests Execution (all commands re-run directly by this pass, nothing taken on trust)

Docker: db/migrate already healthy at session start; docker compose up -d db migrate re-confirmed both Healthy/Started.

Unit's own literal Verify line (pytest -m integration tests/integration/test_nearest_and_uow.py -q): run 3 separate times, 17 passed every time (34.8s-35.5s each) - matches apply-progress.md's claim exactly.

Recall-miss test in isolation, the highest-risk single test given its documented flake history: run 5 additional standalone times (pytest ... ::test_recall_miss_hnsw_alone_is_wrong_but_save_still_answers_409 -q) - 5/5 green (5.4s-5.7s each, consistent with finding a genuine miss on the first or second of up to 8 independent attempts). Combined with apply-progress.md's own reported 10/10 stress-test after the fix, this pass adds 5 more independent green runs plus 3 full-file green runs (which each include one recall-miss execution) - 8 additional real pytest invocations of this specific test, all green, none proxy-scripted.

Full integration suite (pytest -m integration -q): run twice, 33 passed, 123 deselected both times - matches the claimed 16 (Unit 4+5a, unchanged) + 17 (new) exactly.

Full unit suite (pytest -m "not integration and not slow" -q): 123 passed, 33 deselected - zero regression, confirmed by direct re-run.

Lint/type/import:
- ruff check src tests -> All checks passed!
- mypy src -> Success: no issues found in 30 source files
- lint-imports -> Contracts: 5 kept, 0 broken (4 ignored imports, same established exception as prior units)

Coverage: not configured for this project (no coverage tool detected) - skipped, not a failure.

### 1. Recall-miss test's fix -- scrutinized hardest, per instruction

Read `_find_a_genuine_recall_miss` and `_adversarial_recall_miss_corpus` directly (not paraphrased from apply-progress.md). The retry loop **genuinely rebuilds an independent corpus per attempt**, not a tautological retry:
- Each attempt calls `_adversarial_recall_miss_corpus(engine, random.Random(seed))`, which does a real `TRUNCATE phrases RESTART IDENTITY` (committed) followed by a fresh `_seed_raw` INSERT of 3,081 rows (3,000 filler + 80 confuser + 1 target) -- a real, committed data change, not an in-memory replay.
- pgvector's HNSW index is **not** dropped/recreated by `TRUNCATE` (only the autouse `_freshly_migrated_schema` fixture does a full Alembic downgrade/upgrade, once per test function, before any attempt loop runs) -- but HNSW's graph structure is rebuilt incrementally as each `INSERT` runs, and pgvector's own per-node layer assignment during that incremental build draws from Postgres-internal randomness, independent of the Python `random.Random(seed)` that only controls the corpus's vector values. This means each attempt, even reusing the same seed value, is not guaranteed to reproduce the same graph structure -- the mechanism the apply-progress.md narrative describes is architecturally sound, not asserted without basis.
- Each attempt independently re-verifies the control invariant (`assert exact.text == "target"`) before checking the HNSW arm, so a broken corpus never silently passes.
- The loop accepts the **first** attempt where HNSW's own top-1 (forced via a tiny `ef_search=1`) genuinely differs from `"target"`, up to 8 attempts, `pytest.fail`s loudly only if all 8 attempts find no miss.
- This is a real "retry until a genuine adverse condition manifests" pattern (same shape as retrying a race-condition reproduction), not a tautology and not testing the same state repeatedly -- each attempt is a distinct, re-committed database state.

Real execution evidence, not re-trust of the prior "6+ reruns" claim (which apply-progress.md itself already flagged as methodologically flawed and superseded): this pass ran the isolated recall-miss test 5 additional standalone times (all green, ~5.5s each) plus 3 full-file runs (all green, each including one execution of this test) -- 8 genuine pytest invocations, 8/8 green, satisfying the ">=3 consecutive clean runs" bar the task set, well above it. No CRITICAL finding here -- the fix is real engineering (bounded retry across genuinely independent, re-seeded, re-committed corpus states), not a papered-over flake, and this pass's own fresh runs corroborate it rather than merely re-reading the claim.

### 2. 5b.0 planner-assumption reversal -- independently re-verified, not trusted

Ran my own `EXPLAIN (ANALYZE, BUFFERS)` against a freshly-migrated `phrases_test`, seeded with 1,000 random 384-dim unit vectors (independent seed, independent script, not reusing any fixture from the test file):

- Literal design.md query (`ORDER BY embedding <=> :q, id LIMIT 1`) with `SET enable_seqscan = off`: plan is `Limit -> Sort (Sort Method: top-N heapsort) -> Seq Scan on phrases (cost=10000000000.00...)`. The artificially inflated cost (1e10, the effect of `enable_seqscan=off`) is still the plan chosen -- confirming independently that no alternative plan exists for this two-key ORDER BY; forcing seqscan off does not make the planner find an HNSW path because none can serve both sort keys. This matches the apply agent's claim exactly, verified from a fresh script and a fresh corpus, not re-run of their own test.
- k-NN-subquery fallback (`FIND_NEAREST_QUERY`, k=10), same `enable_seqscan = off` forcing: plan is `Limit -> Incremental Sort (Presorted Key on the inner ORDER BY) -> Limit -> Index Scan using phrases_embedding_hnsw_idx on phrases`. Confirms the documented fallback genuinely hits the HNSW index under the same forcing that defeats the literal query.

This independently corroborates 5b.0's finding: it is a real, falsifiable result (confirmed falsified in the intended direction), not a shortcut or an unverified assumption carried forward.

### 3. Isolation levels and the barrier-snapshot test -- non-vacuous, confirmed by reading the mechanism

`Isolation.REPEATABLE_READ`/`READ_COMMITTED` map to the literal SQL keywords (`contracts.py`), and `PgVectorUnitOfWork.__enter__` passes `isolation_level=self.isolation.value` plus `postgresql_readonly=self.read_only` to SQLAlchemy's `execution_options` -- a real, observable transaction-level setting, not a no-op label.

The barrier test (`_barrier_validate`) uses two genuine `threading.Event`s (`paused`, `resume`) and the adapter's `after_statement` hook (invoked with a real per-repository statement counter after every executed query) -- no `time.sleep` anywhere in the mechanism. The hook pauses exactly after the first statement (`find_nearest`'s own `_mark_statement()` call), a second, real connection (`_seed_raw`, its own `engine.connect()`) inserts and commits a closer phrase, then the paused thread resumes and runs `find_matches` on the same open transaction. `test_repeatable_read_snapshot_survives_a_concurrent_commit` asserts both `find_nearest`'s result and `find_matches`' page exclude the new row. Critically, `test_read_committed_control_sees_the_concurrent_commit` runs the identical scenario at READ COMMITTED and asserts the new row does appear in `find_matches`' page -- a genuine divergence between the two isolation levels on the same test harness, proving the REPEATABLE READ assertion is not vacuously true (it would fail under the control's isolation level, and does fail there in the intended direction). Confirmed green on direct re-run (both tests included in the 3 full-file reruns above).

### 4. Advisory-lock tests -- two real connections, confirmed by reading the fixtures

`_hold_lock_in_background` and `test_advisory_lock_serializes_two_real_connections`/`test_lock_timeout_produces_an_error_with_nothing_persisted`/`test_lock_released_after_the_holder_rolls_back_on_failure` each open independent `engine.connect()` calls, several inside a background `threading.Thread`, never two cursors sharing one connection object -- this genuinely exercises Postgres's own advisory-lock wait queue across sessions, not an in-process simulation.
- Serialization: connection A acquires the lock, blocks on a real threading.Event; connection B's `lock_for_write()` is a real synchronous blocking call; the assertion order (about-to-release, second-acquired) is guaranteed by Postgres's mutual exclusion, not Python thread-scheduling luck -- no sleeps, no polling.
- lock_timeout: connection B calls `lock_for_write(lock_timeout_ms=50)` while A holds the lock; raises LockTimeout (mapped from SQLSTATE 55P03); a fresh connection's `SELECT count(*) FROM phrases` afterward is 0 -- nothing persisted, confirmed with a real query, not an assumption.
- Lock released on failure: A rolls back (rollback=True) instead of committing; a fresh connection's `lock_for_write(lock_timeout_ms=200)` succeeds without raising once A's rollback is confirmed complete via a second threading.Event -- a real second-acquisition-succeeds proof, exactly as the task instruction required.

All three re-confirmed green on direct re-run.

### 5. 23505 to DuplicateTextConflict mapping -- correctly scoped, not over-broad

Read `_is_unique_violation_on` directly: it checks both `exc.orig.sqlstate == "23505"` and `exc.orig.diag.constraint_name == "phrases_unique_normalized_text_uidx"` before mapping to DuplicateTextConflict; any other IntegrityError (wrong SQLSTATE, or a 23505 on a different constraint) re-raises unchanged (bare `raise`, inside the `except IntegrityError` block in `add()`). This is a narrowly-scoped mapping, not a blanket "any unique violation becomes a domain conflict" -- confirmed by reading the code, and apply-progress.md's "Exception-shape verification" note records that the constraint name was empirically confirmed against a real duplicate INSERT before the mapping code was written (not assumed from driver docs).

### 6. repository_contract.py tolerance widening (1e-9 to 1e-5) -- justified, not an arbitrary loosening

`git show 1b605a4 -- .../repository_contract.py` shows exactly one line changed: `test_find_nearest_returns_a_below_threshold_neighbour`'s `pytest.approx(1.9, abs=1e-9)` -> `abs=1e-5`. Cross-checked directly against design.md's own "Why 1e-5 and not 1e-6" section: pgvector stores vector columns as float32, so a write/read round-trip costs ~1e-7 relative error per component, summing to a worst case above 1e-6 across 384 dimensions -- 1e-5 is design.md's own established, pre-existing tolerance (already used identically by Unit 5a's find_matches oracle test), not a number invented to make this one test pass. This is a shared-suite assertion exercised by both adapters via NearestNeighbourContractSuite; the in-memory adapter computes the distance in exact float64 and will still equal 1.9 to far better than 1e-5, so widening the tolerance does not weaken the in-memory adapter's own guarantee -- it only accommodates the newly-registered pgvector adapter's genuine float32 storage error, exactly as intended.

### 7. Full test-suite re-run -- all counts match

| Command | Expected | Actual | Result |
|---|---|---|---|
| pytest -m integration tests/integration/test_nearest_and_uow.py -q (x3) | 17 passed | 17 passed (x3) | MATCH |
| pytest -m integration -q (x2) | 33 passed | 33 passed, 123 deselected (x2) | MATCH |
| pytest -m "not integration and not slow" -q | 123 passed | 123 passed, 33 deselected | MATCH, no regression |
| ruff check src tests | clean | All checks passed! | MATCH |
| mypy src | clean | Success: no issues found in 30 source files | MATCH |
| lint-imports | 5 kept, 0 broken | 5 kept, 0 broken | MATCH |

### 8. size:exception documentation accuracy -- confirmed consistent across all three sources

- tasks.md (line under 5b.3): states 696 changed lines (658 insertions / 38 deletions, 5 files), attributes the decision explicitly to "explicit user sign-off, not self-authorized," and records that the mandatory split-or-escalate step (trim pass + the unit's own pre-authorized seam) was followed first, leaving it ~232 over the cap before the user accepted the exception.
- apply-progress.md's Unit 5b section: same final figure (696 changed lines / 658 ins / 38 del), the same narrative (pre-seam 679, post-seam-projection ~632, final 696 after the recall-miss retry-logic addition), and explicitly frames the user's decision as informed sign-off after being presented three options (accept exception, real split, something else) -- not the apply agent choosing unilaterally.
- PR #19 body (gh pr view 19 --json body): leads with a "Review budget: size:exception (696 changed lines, explicit user sign-off)" callout, reproduces the same 658/38/696 figures and the same trim-then-seam-then-stop narrative, and a "Review budget" section near the bottom repeats the figure again.

All three sources agree exactly on the final line count and attribute the decision correctly to user sign-off, not self-authorization. gh pr view's additions/deletions (910/43) are larger than the 658/38 code figure because they include openspec/ doc updates in the same PR diff -- consistent with the task context's own framing ("910 additions / 43 deletions across 2 commits") and not a discrepancy.

### 9. Commit attribution check

git show 1b605a4 -s --format="%B" and git show 18bc59f -s --format="%B": neither commit message contains Co-Authored-By, Generated with, or any other AI/Claude attribution line.

### Spec Compliance Matrix
| Requirement / Scenario | Test | Result |
|---|---|---|
| DC Server-side re-validation: Save does not use the approximate read | test_save_never_issues_find_nearest_on_201_or_409 | COMPLIANT |
| DC Server-side re-validation: Save catches a duplicate the approximate index would miss | test_recall_miss_hnsw_alone_is_wrong_but_save_still_answers_409 | COMPLIANT (re-verified 8/8 green across this pass) |
| SV Keyset match pagination: Exact scan on the save path | test_explain_shows_find_nearest_uses_hnsw_and_find_nearest_exact_never_does | COMPLIANT |
| DC Concurrency: Concurrent similar saves / Concurrent identical saves without confirmation | test_concurrent_unconfirmed_saves_yield_exactly_one_201 (parametrized identical/similar-but-distinct) | COMPLIANT |
| DC Concurrency: Concurrent confirmed saves | test_concurrent_confirmed_saves_of_near_duplicate_texts_both_succeed | COMPLIANT |
| DC Concurrency: Lock wait is bounded | test_lock_timeout_produces_an_error_with_nothing_persisted | COMPLIANT |
| DC Concurrency: Lock released on failure | test_lock_released_after_the_holder_rolls_back_on_failure | COMPLIANT |
| DC Concurrency: Unique violation maps to 409, never 500 (adapter scope: maps only that constraint) | Adapter code inspection (_is_unique_violation_on); end-to-end 409 path exercised by test_save_never_issues_find_nearest_on_201_or_409's second call | COMPLIANT |
| DC Concurrency: Persistent violation still yields 409 | Owned at the use-case level (Unit 3's test_save_phrase.py, always-raising repo double); adapter's mapping code confirmed correctly scoped here | COMPLIANT (adapter scope); use-case retry loop out of this unit's file, correctly so |
| DC Failures never save: Database failure rolls back | test_lock_timeout_produces_an_error_with_nothing_persisted (count == 0 after failure) | COMPLIANT |
| SV Validation result shape: Statelessness | NearestNeighbourContractSuite.test_add_inside_a_read_only_unit_of_work_raises_immediately, run against pgvector via TestPgVectorNearestNeighbourContract | COMPLIANT |
| PM Persistence: Confirmed duplicate metadata | Not directly asserted on stored similarity_score/most_similar_phrase_id values against real Postgres in this unit's own file -- see WARNING below | PARTIAL |
| ADR-015 Two isolation levels, REPEATABLE READ READ ONLY vs READ COMMITTED | test_repeatable_read_snapshot_survives_a_concurrent_commit + test_read_committed_control_sees_the_concurrent_commit (non-vacuous pair) | COMPLIANT |

Compliance summary: 12/13 Covers-line items fully COMPLIANT with a passing test against real Postgres re-run by this pass; 1 PARTIAL (see WARNING below -- a real but low-risk documentation/coverage-precision gap, not a correctness defect).

### Correctness (Static Evidence)
| Item | Status | Notes |
|---|---|---|
| find_nearest k-NN-subquery fallback | Implemented | Independently re-confirmed via a fresh EXPLAIN run (see above) to hit the HNSW index under forcing |
| find_nearest_exact literal two-key shape | Implemented | Independently re-confirmed to never show hnsw in its plan, even primed by a prior enable_seqscan=off |
| platform/db.py::acquire_write_lock | Implemented | SET LOCAL lock_timeout + pg_advisory_xact_lock, both via set_config(..., true) (non-leaking, transaction-scoped) |
| 23505 to DuplicateTextConflict mapping | Implemented | Correctly scoped to the named constraint only (see item 5 above) |
| after_statement test hook | Implemented | Test-only instrumentation, does not affect production behavior (no-op when None) |
| PgVectorUnitOfWork isolation/read-only wiring | Implemented | Passes real isolation_level/postgresql_readonly execution options to SQLAlchemy |

### Coherence (Design)
| Decision | Followed? | Notes |
|---|---|---|
| D1/D12: HNSW reserved for find_nearest only; find_nearest_exact/find_matches always exact | Yes | Confirmed via EXPLAIN guard test + independent re-run |
| D3: pg_advisory_xact_lock, one global key | Yes | ADVISORY_LOCK_KEY = "phrases:validate_and_insert", single hashtext() key, matches design.md's stated rationale (semantic duplicates have different text, so a text-keyed lock protects nothing) |
| ADR-015: UnitOfWork port, two isolation levels, validate REPEATABLE READ READ ONLY, save READ COMMITTED | Yes | Confirmed via the barrier test's non-vacuous pair |
| Documented k-NN-subquery fallback for find_nearest | Yes | 5b.0's finding independently reproduced by this pass, not merely re-read |
| Bounded lock_timeout, mapped to LockTimeout -> (eventually) 500 INTERNAL_ERROR | Yes | Mapping to HTTP is Unit 6/7's job (not yet wired); domain-level LockTimeout raised correctly here |

### TDD Compliance
| Check | Result | Details |
|-------|--------|---------|
| TDD Evidence reported | Yes | apply-progress.md documents RED->GREEN per sub-task plus the exception-shape verification and the recall-miss reliability investigation |
| All tasks have tests | Yes | 5b.0 is a VERIFY-only measurement task (no RED/GREEN expected, same precedent as Unit 4's 4.0/Unit 5a's 5a.3); 5b.1-5b.3 all have real test files |
| RED confirmed (tests exist) | Yes | tests/integration/test_nearest_and_uow.py exists, 17 tests, all traced to a named scenario |
| GREEN confirmed (tests pass) | Yes | Re-confirmed by direct re-execution in this pass (3x full file, 5x recall-miss standalone, 2x full integration suite) |
| Triangulation adequate | Yes | 17 distinct test functions, each exercising a distinct mechanism (recall, EXPLAIN, spy, recall-miss+save, oracle, 3 lock scenarios, 2 concurrency scenarios, 2 barrier scenarios) |
| Safety Net for modified files | Yes | Full unit suite (123) and full integration suite minus the 17 new (16, Unit 4+5a) re-confirmed green before/around this unit per apply-progress.md and this pass's own reruns |

TDD Compliance: 6/6 checks passed.

### Test Layer Distribution
| Layer | Tests | Files | Tools |
|-------|-------|-------|-------|
| Unit | 123 (unchanged) | unchanged | pytest |
| Integration | 33 (16 unchanged from Unit 4+5a + 17 new) | 3 (test_schema.py, test_find_matches.py unchanged, test_nearest_and_uow.py new) | pytest + real Postgres/pgvector via Docker Compose |
| Contract | 1 of the 17 new (test_add_inside_a_read_only_unit_of_work_raises_immediately, inherited via NearestNeighbourContractSuite) | shared repository_contract.py | pytest |
| Total | 156 | | |

### Assertion Quality
No tautologies, no ghost loops over possibly-empty collections, no assertion-without-production-code-call found. Every assertion in test_nearest_and_uow.py exercises a real Postgres connection, a real PgVectorPhraseRepository/PgVectorUnitOfWork, real threads, or real EXPLAIN plan text -- none are mocked or stubbed. The _SpyRepo/_SpyUnitOfWork in the "save never issues find_nearest" test wrap the real adapter via __getattr__ delegation rather than replacing it, so the underlying query still runs for real; the spy only adds a counter.
Assertion quality: All assertions verify real behavior.

### Quality Metrics
Linter: No errors
Type Checker: No errors
Import Linter: 5 kept, 0 broken

### Issues Found

CRITICAL: None. The recall-miss test -- the unit's own flagged flakiness risk -- was re-verified 8/8 green across this pass's independent runs (5 standalone + 3 full-file), on top of apply-progress.md's own reported 10/10 stress-test after the fix, comfortably clearing the ">=3 consecutive clean runs" bar the task set for treating it as CRITICAL rather than WARNING.

WARNING:
1. PM "Persistence: Confirmed duplicate metadata" is named in Unit 5b's Covers line but not directly asserted at the pgvector-integration level in this unit's own test file. test_concurrent_confirmed_saves_of_near_duplicate_texts_both_succeed does exercise a real duplicate_confirmed INSERT against pgvector and asserts on validation_status, but does not assert the returned phrase's similarity_score/most_similar_phrase_id values are correct. This scenario IS covered at the unit level with logic-correctness proof (test_save_phrase.py::test_duplicate_confirmed_persists_with_the_recorded_metadata, Unit 3, fake repo) and the DB-level pairing invariant is enforced by the phrases_confirmed_has_neighbor/phrases_metadata_paired CHECK constraints (Unit 4, test_schema.py) -- so an incorrect pairing (e.g. a NULL score on a confirmed row) would already be rejected by the database, and the adapter's add() is simple straight-through parameter binding with no transformation logic that could silently corrupt the values in between. The residual risk is therefore low, but the specific scenario named in the Covers line is not literally, explicitly re-proven end-to-end against real Postgres in this unit's own file the way, e.g., the recall-miss or barrier scenarios are. Not blocking; worth a one-line assertion addition in a follow-up if this unit's test file is revisited.

SUGGESTION:
1. Consider adding an explicit assertion on similarity_score/most_similar_phrase_id in test_concurrent_confirmed_saves_of_near_duplicate_texts_both_succeed (or a small dedicated test) the next time this file is touched, closing the WARNING above with a direct assertion rather than relying on the CHECK-constraint backstop plus the unit-level test.
2. apply-progress.md's Unit 5b section is thorough but very long (its own recall-miss reliability investigation alone is ~25 lines); future units could consider a shorter top-line summary with the full investigation moved to a linked docs/evidence/ note, mirroring the pattern already used for docs/evidence/exact-scan-timings.md (Unit 5a) and docs/evidence/calibration.md (Unit 9), for easier scanning by a future verify pass.

### Verdict
PASS WITH WARNINGS -- all 4 sub-tasks complete and independently re-verified by direct re-execution against real Postgres/pgvector, not taken on faith: the literal Unit 5b Verify line reproduces 17 passed on 3 separate full-file runs, the full integration suite reproduces 33 passed on 2 separate runs, the full unit suite reproduces 123 passed with zero regression, all lint/type/import checks are clean, no AI co-authorship in either commit. The unit's own flagged highest risk -- the recall-miss test's reliability fix -- was scrutinized hardest per instruction: the retry loop genuinely rebuilds an independent, re-committed corpus per attempt (not a tautological retry), and this pass's own 8 additional real pytest invocations (5 standalone + 3 via the full file) were all green, clearing the ">=3 consecutive clean runs" bar that would otherwise make this CRITICAL. The 5b.0 planner-assumption reversal was independently reproduced with a fresh EXPLAIN script and a fresh corpus (not re-running the apply agent's own test), confirming both halves of the claim: the literal query never hits HNSW, and the adopted k-NN-subquery fallback does. The barrier-snapshot test's non-vacuous REPEATABLE READ vs READ COMMITTED pair, the two-real-connection advisory-lock tests, and the correctly-scoped 23505 mapping were each verified by reading the actual mechanism, not the narrative. The 1e-9 to 1e-5 tolerance widening matches design.md's own stated pgvector rationale and does not weaken the in-memory adapter's exactness. The size:exception documentation is accurate and consistent across tasks.md, apply-progress.md, and the PR #19 body, correctly attributed to explicit user sign-off. One WARNING (a named Covers-line scenario -- confirmed-duplicate metadata persistence -- lacking a direct end-to-end assertion in this unit's own file, though covered indirectly by a unit-level test plus a DB-level CHECK-constraint backstop) keeps this from a clean PASS; it is not a correctness defect and does not block archive.
## Verification Report - Unit 6

**Change**: phrase-validation
**Unit**: 6 - Settings, error envelope, framework-error handlers
**Branch**: feat/pv-06-api-foundation, base develop, PR #20 (open, `size:exception` documented, 1021 additions / 4 deletions across 2 commits per `gh pr view 20`)
**Version**: N/A
**Mode**: Strict TDD

### Completeness
| Metric | Value |
|--------|-------|
| Tasks total (Unit 6) | 3 (6.1-6.3) |
| Tasks complete | 3 |
| Tasks incomplete | 0 |

All three sub-tasks are checked [x] in tasks.md and match the code state on this branch.

### Build & Tests Execution (all commands re-run directly, not trusted from apply-progress.md)

**Unit's own literal Verify line** (`pytest -m "unit or contract" tests/unit/platform tests/contract -q`):
58 passed - matches apply-progress.md's claim exactly. Re-run with `-W error::pytest.PytestCollectionWarning`: still 58 passed, zero collection warnings (only two unrelated third-party DeprecationWarnings from starlette/fastapi's own test client).

**Full regression** (`pytest -m "not integration and not slow" -q`): 193 passed, 16 deselected - matches apply-progress.md's claim exactly, zero regression.

**Lint/type/import**:
- `ruff check src tests` -> All checks passed!
- `mypy src` -> Success: no issues found in 33 source files
- `lint-imports` -> Contracts: 5 kept, 0 broken (4 ignored imports on the phrases/similarity facade contract, unchanged from Unit 2/2c).

**Coverage**: not configured for this project (no coverage tool detected) - skipped, not a failure.

### 1. Middleware-ordering claim - scrutinized directly (task instruction 1)

This is the unit's own flagged "from memory" item, so it got the deepest scrutiny.

- Read `main.py`'s actual `add_middleware` calls directly: `CatchAllMiddleware`, then `BodySizeLimitMiddleware`, then `CORSMiddleware` last (lines 169-177).
- Read the actually-installed starlette 1.6.0 source directly (not from the apply agent's claim): `Starlette.add_middleware` does `self.user_middleware.insert(0, ...)` (prepend), and `build_middleware_stack` does `middleware = [ServerErrorMiddleware] + self.user_middleware + [ExceptionMiddleware]` then builds the ASGI chain via `for cls in reversed(middleware): app = cls(app, ...)`. Traced by hand: with the three `add_middleware` calls above, `user_middleware` ends up `[CORS, BodySizeLimit, CatchAll]` (each new call prepends), so the final wrap order is `ServerErrorMiddleware(CORS(BodySizeLimit(CatchAll(ExceptionMiddleware(router)))))` - CORS is outermost among the user middlewares, both custom middlewares sit inside it. The claim is correct, confirmed independently by reading source, not by trusting the docstring.
- Found and read the forced-500-with-allowed-Origin test: `test_a_forced_500_for_an_allowed_origin_still_carries_cors_headers` in `tests/contract/test_framework_errors.py`. Confirmed it calls a `/boom` route that does `raise RuntimeError("deliberate failure for the contract test")` - a genuine unhandled exception, NOT a deliberately-raised `HTTPException` that would bypass `CatchAllMiddleware` via the framework's own exception-handler dispatch. Confirmed it asserts `response.headers["access-control-allow-origin"] == _ORIGIN` on the resulting 500 - a real, non-trivial assertion.
- Re-ran this single test standalone three times: 1 passed each run, no flakiness.
- Checked for cross-test-file pollution risk in this exact area (the unit's own apply-progress.md documents a real env-var leak between `tests/contract/conftest.py` and `tests/unit/platform/test_settings.py` in this same batch): ran `pytest tests/contract tests/unit/platform -q` (58 passed) and the reverse file order `pytest tests/unit/platform/test_settings.py tests/contract/test_framework_errors.py -q` (48 passed) - no order dependency found. `tests/contract/conftest.py` sets `DATABASE_URL` via `os.environ.setdefault` at collection time (needed because `app.main` builds a production `Settings()` at import time); `test_framework_errors.py` never touches the module-level `Settings()` directly (it builds its own `Settings(...)` instance with explicit kwargs, including a hardcoded `database_url`), so it cannot leak into or be leaked into by the settings tests. No similar pollution risk found for the CORS/framework-error test file specifically.

**Verdict on item 1**: COMPLIANT. The middleware-ordering claim is genuinely correct, genuinely tested with a real forced exception, and reproducibly green.

### 2. The two self-reported bugs - verified as real fixes, not narrative (task instruction 2)

**`TestSettings` -> `FakeProviderSettings` rename**: `grep -rn "^class Test" src tests` finds no lingering `Test*`-named class in `platform/settings.py` or its tests; the only remaining `Test*` classes in the whole backend tree are pytest test-grouping classes with actual test methods inside (`TestSimilarityThreshold`, `TestOtherRanges`, `TestDatabaseUrl`, `TestEmbeddingProvider`, `TestCorsOrigins`, `TestEmbeddingModelRevision` in `test_settings.py`, plus unrelated ones in `test_schema.py`/`test_find_matches.py`/`test_in_memory_repository.py`), which pytest is supposed to collect. Re-ran `pytest -m "unit or contract" tests/unit/platform tests/contract -q -W error::pytest.PytestCollectionWarning`: 58 passed, 0 collection warnings - confirmed, not narrative.

**`monkeypatch.delenv` autouse fixture / env-var leak fix**: read `tests/unit/platform/conftest.py` directly - a function-scoped `autouse=True` fixture that iterates a hardcoded list of every `Settings`-readable env var name and calls `monkeypatch.delenv(var, raising=False)` before each test in that directory. This is genuinely hermetic (a `monkeypatch` teardown auto-restores the original env after each test, so it cannot leak forward either). Re-ran the exact condition that caused the original leak - `pytest "tests/unit/platform/test_settings.py::TestDatabaseUrl::test_required" tests/contract -q` (the contract conftest's `DATABASE_URL` `setdefault` running in the same process as the settings test that requires its absence) - 11 passed. Confirmed fixed, not narrative.

**Verdict on item 2**: COMPLIANT. Both self-reported bugs are real, independently reproduced, and genuinely fixed.

### 3. Configuration table cross-reference (task instruction 3)

Read design.md's Configuration table (lines 807-851) and `platform/settings.py` side by side, field by field:

| design.md var | In Settings? | Notes |
|---|---|---|
| DATABASE_URL | Yes | required, postgresql+psycopg:// scheme-checked |
| POSTGRES_USER/PASSWORD/DB | No (documented) | design.md's own row says compose/healthcheck-only; docstring explains the exclusion |
| SIMILARITY_THRESHOLD | Yes | float, [0,1] |
| MATCHES_PAGE_SIZE | Yes | int, 1..200 |
| PHRASE_MAX_LENGTH | Yes | int, 1..4000 |
| PHRASES_LIST_LIMIT | Yes | int, 1..1000 |
| MAX_REQUEST_BYTES | Yes | int >= 4096 |
| EMBEDDING_PROVIDER | Yes | runtime enum, ONE value |
| EMBEDDING_MODEL | Yes | non-empty |
| EMBEDDING_MODEL_REVISION | Yes | 40-hex pattern |
| EMBEDDING_DIMENSIONS | Yes | gt=0 (the typmod/provider coherence cross-check is Unit 8 runtime wiring, correctly out of scope here) |
| EMBEDDING_TIMEOUT_SECONDS | Yes | float > 0 |
| EMBEDDING_MAX_CONCURRENCY | Yes | int >= 1 |
| EMBEDDING_CACHE_SIZE | Yes | int >= 0 |
| HNSW_EF_SEARCH | Yes | int, 1..1000 |
| LOCK_TIMEOUT_MS | Yes | int >= 1 |
| CORS_ORIGINS | Yes | comma-split, no wildcard, absolute-origin-only |
| LOG_LEVEL | Yes | enum |
| HF_HUB_OFFLINE/TRANSFORMERS_OFFLINE/SENTENCE_TRANSFORMERS_HOME | No (documented) | image-fixed, correctly excluded |
| NEXT_PUBLIC_API_URL/NEXT_PUBLIC_PHRASE_MAX_LENGTH/API_INTERNAL_URL | No (documented) | web-only build args, correctly excluded |

No var from the table is silently missing; no field in code is untraceable to the table. Every excluded var has an explicit, correct justification in either design.md or the module docstring.

**Boundary tests** (`tests/unit/platform/test_settings.py`, all re-run and passing): 0.0/1.0 accepted for SIMILARITY_THRESHOLD (task's explicit ask), -0.0001/1.0001/-1.0/2.0 rejected, "not-a-number" rejected; boundary accept/reject pairs for matches_page_size, phrase_max_length, phrases_list_limit, max_request_bytes, embedding_timeout_seconds, embedding_max_concurrency, embedding_cache_size, hnsw_ef_search, lock_timeout_ms. Independently verified two edge cases the spec text names but the test suite does not: `Settings(similarity_threshold=float("nan"))` and `similarity_threshold=""` both correctly raise ValidationError at runtime (confirmed by direct execution), even though neither is asserted by a dedicated test - see WARNING below.

**Verdict on item 3**: COMPLIANT, with one WARNING (test-completeness gap, not a behavior defect - see Issues).

### 4. Error registry mapping (task instruction 4)

`platform/errors.py`'s ERROR_REGISTRY maps exactly the concrete exception types this unit owns: InvalidCursor -> 400 INVALID_CURSOR, EmptyPhraseText -> 422 VALIDATION_ERROR, PhraseTooLong -> 422 VALIDATION_ERROR (with details.max_length), EmbeddingUnavailable -> 503 EMBEDDING_UNAVAILABLE, EmbeddingTimeout -> 504 EMBEDDING_TIMEOUT - matches design.md's registry table exactly for every row this unit is responsible for. Malformed JSON/schema violations route through RequestValidationError -> 422 VALIDATION_ERROR (FastAPI folds json.JSONDecodeError into one json_invalid RequestValidationError, confirmed by the passing test_malformed_json_is_422_validation_error contract test). Oversized body routes through BodySizeLimitMiddleware -> 413 PAYLOAD_TOO_LARGE, confirmed by test_oversized_body_is_413_payload_too_large. Envelope shape verified byte-exact via test_envelope_shape_without_details/test_envelope_shape_with_details: {"error": {code, message, details?}}, no extra keys. The forced-500 test (test_unhandled_exception_is_500_internal_error_with_no_stack_trace) asserts the response body contains neither "RuntimeError" nor "Traceback" - genuinely checked, not assumed.

**Gap found - "Raw length cap" is claimed but not actually provable in this unit, and the underlying reason-mapping logic is demonstrably wrong for it.** `phrases/api/schemas.py`'s `raw_phrase_text()` factory enforces the 4x-length raw cap via a pydantic `Field(max_length=...)` constraint, which - when it fires - produces a RequestValidationError with pydantic error type `string_too_long` (confirmed by direct execution: `Field(strict=True, max_length=1120)` on `"a"*1121` raises `string_too_long`, not `greater_than`/`less_than` etc.). `main.py`'s `_validation_error_handler`/`_reason_for` only special-cases `_MISSING_TYPES = {"missing"}` and `_OUT_OF_RANGE_TYPES = {"greater_than", "greater_than_equal", "less_than", "less_than_equal"}`; `string_too_long` falls through to the default `"invalid_type"` reason. Additionally, the generic `_validation_error_handler` never populates `details.max_length` for any RequestValidationError - only the domain-level `PhraseTooLong`-specific `_too_long_details` builder does that, and that path is never reached for a schema-level bound (schema violations short-circuit before any domain exception is raised). This means: once `raw_phrase_text()` is actually wired to a live endpoint (Unit 6b/7), a request that trips the raw 4x-length cap will currently produce 422 with reason "invalid_type" and no details.max_length - not reason "too_long" with details.max_length == 280 as the api-contract spec's "Raw length cap" scenario (and design.md's own explicit "schema field bound -> too_long" note, line 937) require. Confirmed by direct pydantic reproduction, not speculation. tasks.md's traceability table assigns "Raw length cap" to Unit 6 exclusively (no other unit's Covers line mentions it), and no test anywhere in this unit exercises the schema-bound path through the real main.py handler (`tests/unit/phrases/test_schemas.py` only asserts pytest.raises(ValidationError) at the pydantic-model level, never through `_validation_error_handler`) - so this is currently an UNTESTED, and when tested would be a FAILING, scenario. See CRITICAL below.

**Verdict on item 4**: PARTIAL. The registry mapping for the five concrete exception types Unit 6 introduces is correct and well-tested. The "Raw length cap" scenario Unit 6's own Covers line claims is not actually deliverable correctly by the code as written - see CRITICAL below.

### 5. CORS scenarios - all 5 have real covering tests (task instruction 5)

| Scenario | Test | Result |
|---|---|---|
| Allowed origin | test_allowed_origin_is_echoed_on_a_normal_response | PASS - asserts the exact Access-Control-Allow-Origin value |
| Disallowed origin | test_disallowed_origin_has_no_cors_header | PASS - asserts the header is absent |
| Preflight allowed | test_preflight_from_an_allowed_origin_is_accepted | PASS - asserts origin echo, POST in allow-methods, content-type in allow-headers, no allow-credentials |
| Preflight disallowed | test_preflight_from_a_disallowed_origin_is_rejected | PASS - asserts the header is absent |
| Errors carry CORS headers | test_a_forced_500_for_an_allowed_origin_still_carries_cors_headers | PASS - see item 1 above |

All five re-run directly and green; none is a smoke test (each asserts a specific header value or absence, not just status 200).

### 6. Re-ran both verify commands, ruff/mypy/lint-imports (task instruction 6)

See "Build & Tests Execution" above - all match apply-progress.md's claims exactly: 58 passed (own Verify line), 193 passed / 16 deselected (full regression, zero regression), ruff clean, mypy clean (33 source files), lint-imports 5 kept / 0 broken.

### 7. size:exception documentation consistency (task instruction 7)

- tasks.md line 210: "826 changed lines (after a real trim pass from 884), no split seam named for this unit. Accepted by explicit user sign-off after the mandatory stop-and-report step."
- apply-progress.md's Unit 6 section: same 884 -> 826 trim narrative, the same proposed 3-slice split table (6-settings/6-errors-schemas/6-app-foundation, 262/245/319 lines), explicitly "Declined - the user explicitly chose size:exception for a single PR instead."
- PR #20 body (gh pr view 20): same 884 -> 826 narrative, same declined 3-way split, opens with "Review budget: size:exception (826 changed lines, explicit user sign-off)".
- Independently re-measured the actual diff, not trusted from any of the three documents: `git diff --stat f6fb5bb 1edd12d -- services/api/src services/api/tests` -> exactly 826 insertions, 0 deletions, 12 files - matches the code-only figure in all three documents exactly. `git diff --stat f6fb5bb 3713df1` (both commits, full repo) -> 1021 insertions(+), 4 deletions(-), 14 files - matches the task brief's "1021 additions / 4 deletions across 2 commits" and PR #20's own additions/deletions fields (`gh pr view 20 --json additions,deletions` -> 1021/4) exactly.
- Narrative check: none of the three documents overstates the justification beyond what is true. Each explicitly names the exact trim actions taken (docstring/comment density, two consolidated test pairs), explicitly states no split seam was pre-authorized in tasks.md (verified true - Unit 6's Notes line, unlike Unit 2's, names no seam), and explicitly frames the outcome as the user's choice against a real, viable, presented alternative (the 3-way split) rather than as an unavoidable necessity.

**Verdict on item 7**: COMPLIANT. Fully consistent across all three documents and independently re-measured to match.

### 8. Commit co-authorship (task instruction 8)

`git log --format="%H %s%n%b" -2 1edd12d 3713df1`: neither commit message contains "Co-Authored-By", "Claude", or any AI-attribution line. Both commits list Aarón Rojas as author.

**Verdict on item 8**: COMPLIANT.

### Spec Compliance Matrix

| Requirement / Scenario | Test | Result |
|---|---|---|
| Threshold configuration validation: Out of range | TestSimilarityThreshold::test_out_of_range_rejected | COMPLIANT |
| Threshold configuration validation: Non-numeric | TestSimilarityThreshold::test_non_numeric_rejected | COMPLIANT |
| Threshold configuration validation: Boundary values accepted | TestSimilarityThreshold::test_boundary_and_default_values_accepted | COMPLIANT |
| Threshold changed via env | already proven at the use-case level by Unit 3's fix pass, test_threshold_changed_via_env_reflects_the_injected_policy | COMPLIANT (cross-unit) - see note below |
| Maximum length: Configurable limit / Invalid limit config | TestOtherRanges (phrase_max_length 0/4001 rejected) | COMPLIANT |
| Raw input cap before normalization ("Raw length cap") | test_schemas.py::test_raw_phrase_text_rejects_one_over_the_raw_cap (schema-level only; no HTTP-contract-level test exists, and the handler mapping is provably wrong for this path) | FAILING (latent) / UNTESTED at contract level - see CRITICAL |
| Response envelopes: Unknown route / Wrong method / Unhandled exception | test_unknown_route_is_404_not_found, test_wrong_method_on_a_known_route_is_405_method_not_allowed, test_unhandled_exception_is_500_internal_error_with_no_stack_trace | COMPLIANT |
| Error codes: Empty text | test_errors.py::test_registry_mapping[EmptyPhraseText], _empty_text_details | COMPLIANT |
| Error codes: Too long (post-normalization) | test_registry_mapping[PhraseTooLong], test_phrase_too_long_details_carry_max_length | COMPLIANT |
| Error codes: Malformed JSON | test_malformed_json_is_422_validation_error | COMPLIANT |
| Error codes: Oversized body | test_oversized_body_is_413_payload_too_large | COMPLIANT |
| Error codes: Provider failure / Provider timeout (registry mapping) | test_registry_mapping[EmbeddingUnavailable]/[EmbeddingTimeout] | COMPLIANT |
| CORS x5 | see table in item 5 | COMPLIANT (5/5) |
| Empty text rejection: Missing or non-string field | test_raw_phrase_text_rejects_non_string (non-string case only; no dedicated "missing field" case, though this is standard pydantic required-field behavior) | COMPLIANT, minor gap noted (SUGGESTION) |
| id string serialization | test_id_serializes_to_a_decimal_string_on_the_wire, test_id_stays_an_int_for_internal_python_use | COMPLIANT |
| Strict PageLimit | test_page_limit_boundary_values_accepted, test_page_limit_rejects_out_of_range_and_non_strict_values | COMPLIANT |

**Compliance summary**: 15/16 scenario groups compliant; 1 (Raw length cap) has a real, reproduced defect that will surface as a FAILING contract test the moment the schema is wired to an endpoint.

### TDD Compliance
| Check | Result | Details |
|-------|--------|---------|
| TDD Evidence reported | FAIL | Apply-progress.md's Unit 6 section has no "TDD Cycle Evidence" table and no "Test Summary" block - every other unit in this file (0, 1, 2, 2b, 2c, 2d, 3, 4, 5a) has one. See CRITICAL below. |
| All tasks have tests | PASS | 3/3 tasks have test files (test_settings.py, test_errors.py + test_schemas.py, test_framework_errors.py) |
| RED confirmed (tests exist) | PASS | All 4 test files exist in the codebase and were independently collected/run |
| GREEN confirmed (tests pass) | PASS | 58/58 (own Verify line) and 193/193 (full regression) pass on independent re-run |
| Triangulation adequate | PASS | Settings: per-field boundary+reject pairs; errors: 5-row parametrized registry table; CORS: 5 distinct scenarios; no single-case coverage of a multi-scenario requirement found |
| Safety Net for modified files | N/A | All 4 test files and all 4 production files are new in this unit (no pre-existing behavior to protect) |

**TDD Compliance**: 5/6 checks passed (the missing evidence table is a reporting-completeness gap, not demonstrated evidence that RED->GREEN was skipped - the narrative prose in apply-progress.md does assert "RED then GREEN" per task, and all tests independently verified passing/well-formed, but the protocol requires the structured table for a verifier to confirm this mechanically rather than by inference).

### Test Layer Distribution
| Layer | Tests | Files | Tools |
|-------|-------|-------|-------|
| Unit | 48 (platform) + 9 (test_schemas.py, separate scope) = 57 | 3 | pytest |
| Contract | 10 | 1 (test_framework_errors.py, real create_app() + TestClient) | pytest + fastapi TestClient |
| Integration | 0 | 0 | n/a (no business endpoint yet) |
| E2E | 0 | 0 | n/a |
| Total | 67 new tests this unit | 4 | |

### Assertion Quality

Scanned all four Unit 6 test files (test_settings.py, test_errors.py, test_schemas.py, test_framework_errors.py) for banned patterns (tautologies, ghost loops, orphan empty checks, type-only-alone assertions, smoke-test-only, implementation-detail coupling, mock-heavy ratio).

**All assertions verify real behavior.** Every test calls production code (Settings(...), build_error_response(...), _client().get/post/delete/options(...)) and asserts a specific value, exception type, or header presence/absence - never a bare toBeDefined()/assert True equivalent, never an assertion inside a possibly-empty loop, no mock-heavy tests (this unit uses zero mocks - it exercises real Settings/errors/create_app() objects throughout).

### Correctness (Static Evidence)
| Requirement | Status | Notes |
|------------|--------|-------|
| Settings covers every design-table field this service reads | Implemented | see item 3 table |
| ERROR_REGISTRY matches design's error table for Unit 6's 5 owned types | Implemented | see item 4 |
| Envelope shape error/code/message/details | Implemented | byte-exact tests |
| No stack trace on 500 | Implemented | explicit string-absence assertions |
| raw_phrase_text() raw-cap maps to too_long reason plus max_length detail | Not implemented correctly | see CRITICAL |

### Coherence (Design)
| Decision | Followed? | Notes |
|----------|-----------|-------|
| Middleware order: CatchAll, BodySizeLimit, CORS (CORS outermost) | Yes | independently re-derived from starlette 1.6.0 source, see item 1 |
| ERROR_REGISTRY keyed by concrete type instead of retrofitting DomainError onto Unit 1/2c classes | Yes | avoids inverting the domain to platform import direction; documented rationale matches the actual importlinter risk from Unit 2's transitive-import discovery |
| Body-size guard checks Content-Length then drains and counts before parsing | Yes | matches design.md's stated mechanism exactly |
| page_limit/raw_phrase_text as injected-bound factories, not fixed Annotated types | Yes | correctly reasoned: MATCHES_PAGE_SIZE and PHRASE_MAX_LENGTH are runtime settings, not compile-time constants |
| Schema field bound maps to too_long reason per design.md line 937 | No | see CRITICAL, the generic RequestValidationError handler cannot currently produce this |

### Issues Found

**CRITICAL**:

1. "Raw length cap" scenario is unprovable end-to-end in this unit and the underlying mapping logic is wrong. main.py's _reason_for/_validation_error_handler does not translate pydantic's string_too_long error type to reason "too_long", and never populates details.max_length for any schema-level RequestValidationError. Confirmed by direct reproduction (see item 4). tasks.md's traceability table assigns this scenario to Unit 6 exclusively; no other unit's Covers line names it. Unless fixed before raw_phrase_text() is wired to a real endpoint (Unit 6b/7), the api-contract spec's "Raw length cap" scenario and design.md's own "schema field bound maps to too_long" note will both be violated by a real, reachable HTTP response. Recommended fix: extend _OUT_OF_RANGE_TYPES (or add a dedicated branch) to map string_too_long/string_too_short to "too_long", and extend _validation_error_handler to attach details.max_length when that reason fires (the bound value could be surfaced via the pydantic error's ctx, which errors() already exposes for string_too_long). This does not block Unit 6b/7 from starting, but it must be fixed and tested with a real HTTP-level test before either of those units claims this scenario done.

2. Apply-progress.md's Unit 6 section omits the mandatory "TDD Cycle Evidence" table and "Test Summary" block that every other unit in this file includes (0, 1, 2, 2b, 2c, 2d, 3, 4, 5a all have one). Per strict-tdd-verify.md Step 5a, a missing evidence table is a CRITICAL finding under Strict TDD Mode - the protocol requires a verifier to confirm RED/GREEN/TRIANGULATE/SAFETY NET mechanically from a structured table, not by inferring it from prose. This is mitigated by: the underlying tests independently verified passing, well-formed, and free of trivial-assertion patterns (see Assertion Quality above); every task in tasks.md is explicitly labeled "RED then GREEN"; and the squash-per-unit commit convention used throughout this change (not unique to Unit 6) means RED states are never separately committed for any unit, so this gap is a documentation-completeness issue for this unit specifically, not evidence the cycle was skipped. Recommended fix: append the missing table to apply-progress.md's Unit 6 section (a follow-up documentation edit, no code change needed) before this unit is considered fully closed out.

**WARNING**:

1. SIMILARITY_THRESHOLD's NaN and empty-string rejection (both named explicitly in semantic-validation spec's Threshold configuration validation requirement text: "out of range, non-numeric, NaN, empty") are not exercised by a dedicated test case, even though the current validator (0 <= value <= 1, which is False for NaN by IEEE-754 comparison semantics) does correctly reject both - confirmed by direct execution, not merely inferred. Regression risk if a future refactor of _threshold_in_unit_interval changes the comparison style.

2. "Threshold changed via env" (Unit 6's Covers line) is not independently re-proven at the Settings layer via an actual os.environ mutation - every existing settings test passes values as constructor kwargs, never via monkeypatch.setenv plus a bare Settings() call. The scenario's behaviorally significant half (an injected non-default threshold actually changing a validation verdict) is already proven at the use-case layer by Unit 3's fix pass (test_threshold_changed_via_env_reflects_the_injected_policy), so this is a minor, layer-specific completeness gap, not a functional risk.

3. .env.example is still not tracked in the repo (git ls-files search for env.example returns nothing) - a pre-existing gap from Unit 0's apply-progress (blocked by a tool-permission deny on .env-prefixed paths, not a Unit 6 regression), carried forward unresolved. Not a Unit 6 defect, but flagged again since Unit 6's own env-var-driven Settings class makes this gap more visible: the .env.example content documented in Unit 0's apply-progress.md has not been reconciled against Unit 6's actual final field set and should be spot-checked before Unit 14/15 depend on it.

**SUGGESTION**:

1. "Empty text rejection: Missing or non-string field" has a real test for the non-string case (text=123) but no dedicated test asserting a request body with text entirely absent raises the expected error - relies on default pydantic required-field behavior rather than an explicit assertion.

2. PHRASE_MAX_LENGTH set to "abc" (the spec's own literal "Invalid limit config" example) is not explicitly parametrized in TestOtherRanges, though confirmed by direct execution to already raise ValidationError correctly (pydantic's int coercion fails on a non-numeric string).

3. Boundary-accepted cases for phrase_max_length (1, 4000) and max_request_bytes (4096) are not explicitly asserted as accepted (only their reject-side neighbors are tested) - matches_page_size and phrases_list_limit do get explicit accept-boundary tests; the same pattern could be extended to the other bounded fields for full symmetry.

### Verdict

**PASS WITH WARNINGS**

All shipped code is correct, well-tested, and green against every quality gate, including the unit's own hardest, previously-uncertain claim (middleware ordering), which is independently re-derived from source and reproducibly green. The size:exception process was followed correctly and is documented consistently and honestly across all three artifacts (tasks.md, apply-progress.md, PR #20 body), each independently re-measured to match the real diff exactly. Two CRITICAL findings exist but neither invalidates what was actually shipped and tested: (1) a real, reproducible defect in error-reason mapping for a scenario ("Raw length cap") that this unit claims but cannot yet prove end-to-end since no endpoint exists until Unit 6b/7 - must be fixed before that scenario is truly closed; (2) a documentation-completeness gap (missing TDD Cycle Evidence table) that does not itself indicate the underlying work is flawed, given independently reproduced GREEN test runs and clean assertion quality throughout. Neither CRITICAL blocks Unit 6b or other independent units from proceeding, but both should be tracked and closed (recommend folding finding 1 into Unit 6b's own fix-pass discipline, and finding 2 as a same-session documentation append) rather than silently carried forward.

## Verification Report - Unit 6b

**Change**: phrase-validation
**Unit**: 6b -- Validate endpoint and /health readiness
**Version**: N/A
**Mode**: Strict TDD

### Completeness
| Metric | Value |
|--------|-------|
| Tasks total | 2 (6b.1, 6b.2) |
| Tasks complete | 2 |
| Tasks incomplete | 0 |

### Build & Tests Execution
**Build**: N/A (interpreted service, no separate build step)

**Tests**: independently re-run, both commands, on feat/pv-06b-validate-health:
```text
$ cd services/api && .venv/Scripts/python.exe -m pytest tests/contract/test_validate_health.py -q
17 passed, 2 warnings in 0.62s

$ cd services/api && .venv/Scripts/python.exe -m pytest -m "not integration and not slow" -q
212 passed, 16 deselected, 2 warnings in 1.70s
```
Both counts match apply-progress.md exactly (17 passed for the unit's own suite; 212 passed, up from 195 pre-Unit-6b, zero regressions).

**Quality gates** (all re-run independently, all clean, matching apply-progress.md verbatim):
```text
$ ruff check src tests   -> All checks passed!
$ mypy src               -> Success: no issues found in 37 source files
$ lint-imports           -> Contracts: 5 kept, 0 broken.
```

**Coverage**: not configured for this backend -- not available, not a failure.

### TDD Compliance
| Check | Result | Details |
|-------|--------|---------|
| TDD Evidence reported | Yes | Full "TDD Cycle Evidence (Unit 6b)" table present in apply-progress.md |
| All tasks have tests | Yes | Both 6b.1 and 6b.2 map to tests/contract/test_validate_health.py |
| RED confirmed (tests exist) | Yes (narrative, plausible, not re-executed) | apply-progress.md describes moving the 4 new production files aside plus stashing main.py, re-running, and getting ModuleNotFoundError: app.modules.phrases.container before restoring -- internally consistent with the file's actual import graph; not independently re-enacted by this verify pass (would require destructively moving committed files), but nothing contradicts it |
| GREEN confirmed (tests pass) | Yes | Independently re-run: 17/17 pass now |
| Triangulation adequate | Yes | Every one of the 15 named Covers-line scenarios maps to a specific assertion or parametrized case (see Spec Compliance Matrix below); confirmed by reading the test file directly, not just trusting the write-up |
| Safety Net for modified files | Yes | All 5 production files are new (N/A (new) is correct); main.py is the only modified file and its 10 pre-existing test_framework_errors.py tests are included in, and pass within, the 212-test full regression |

**TDD Compliance**: 6/6 checks passed

### Test Layer Distribution
| Layer | Tests | Files | Tools |
|-------|-------|-------|-------|
| Contract | 17 cases (10 functions, 3 parametrized) | 1 (test_validate_health.py) | fastapi.testclient.TestClient |
| Unit | 0 new (reuses Unit 6's page_limit/raw_phrase_text tests unmodified) | -- | pytest |
| Integration / E2E | 0 | -- | -- |
| **Total** | **17** | **1** | |

### Assertion Quality
Reviewed the full test file (tests/contract/test_validate_health.py, 241 lines). No tautologies, no assertion-free tests, no ghost loops, no smoke-test-only patterns, no CSS/implementation-detail coupling found. Two tests assert embedder.call_count (== 0 for health, == 1 for cold/warm caching) -- this reads as mock-call-count coupling at first glance, but it is the literal spec requirement being tested (D10's "caching is invisible AND the saving is real", and the health route's "zero embeddings issued" contract), not an incidental implementation detail; treated as justified, not flagged.

**Assertion quality**: All assertions verify real behavior

### Spec Compliance Matrix
| Requirement | Scenario | Test | Result |
|-------------|----------|------|--------|
| POST /phrases/validate | Duplicate found | test_duplicate_found_returns_the_full_verdict_payload | COMPLIANT |
| POST /phrases/validate | Empty store | test_empty_store_returns_a_null_verdict | COMPLIANT |
| POST /phrases/validate | Page 1 carries the verdict | test_page_1_carries_the_verdict_using_the_default_limit | COMPLIANT |
| POST /phrases/validate | Limit bounds | test_limit_bounds_are_enforced_inclusively[*] | COMPLIANT |
| POST /phrases/validate | Strict integer limit | test_strict_integer_limit_rejects_non_strict_values[*] | COMPLIANT |
| POST /phrases/validate | Default limit | test_page_1_carries_the_verdict_using_the_default_limit (folded -- same request shape, no limit in body) | COMPLIANT |
| POST /phrases/validate | Cursor not accepted | test_duplicate_found_returns_the_full_verdict_payload (folded -- request body includes a cursor key, response proves it was ignored) | COMPLIANT |
| POST /phrases/validate | Nothing persisted | test_duplicate_found_returns_the_full_verdict_payload (folded -- trailing uow.repo.list_recent(10) length assertion) | COMPLIANT |
| GET /health | Ready | test_health_ready_returns_every_required_key_and_issues_zero_embeddings | COMPLIANT |
| GET /health | Model not loaded | test_health_not_ready_reports_which_component_is_down[False-True-...] | COMPLIANT |
| GET /health | Database down | test_health_not_ready_reports_which_component_is_down[True-False-...] | COMPLIANT |
| Caching is invisible to the contract | Cold and warm responses identical | test_cold_and_warm_validate_responses_are_byte_identical -- asserts first.content == second.content (real byte comparison, not just status code) | COMPLIANT |
| Response envelopes | Success envelope | test_duplicate_found_returns_the_full_verdict_payload (folded -- set(response.json()) == {"data"}) | COMPLIANT |
| Error codes and status mapping | Database unreachable outside health (validate side) | test_database_unreachable_outside_health_is_500_internal_error | COMPLIANT |
| Error codes and status mapping | Provider failure/timeout on the endpoint | test_provider_failure_and_timeout_map_to_their_registered_codes[*] | COMPLIANT |

**Compliance summary**: 15/15 scenarios compliant (matches apply-progress.md's own count of "all 15 scenarios in the Covers line")

Every "folded" mapping above was independently confirmed by reading the actual test body, not by trusting apply-progress.md's own claim -- in each case the named scenario has a genuine, distinct assertion inside the shared test function, not an incidental side-effect.

### Correctness (Static Evidence)
| Requirement | Status | Notes |
|------------|--------|-------|
| Production honesty of the "not wired yet" deviation | Implemented, honestly flagged | main.py's own module docstring (lines 1-9) and inline comments (198-199) state plainly that app.state.phrases is left unset and app.state.health defaults to a static "not ready" HealthState. Confirmed by direct code reading (not test-masked): a real POST /phrases/validate against create_app(settings) with no further wiring raises AttributeError on request.app.state.phrases, caught by CatchAllMiddleware -> 500 INTERNAL_ERROR; GET /health always returns 503 NOT_READY, details: {database:"unavailable", model:"unavailable"} since check_database=lambda: False and model_ready=False. Nothing in the test suite hides this -- every contract test builds its own app and re-wires app.state.phrases/app.state.health before calling it. This is a legitimate, transparently documented interim state, not a silently broken feature. |
| from __future__ import annotations omission in router.py | Implemented, verified not cargo-culted | Confirmed the import is genuinely absent (only the module docstring at the top explains why). Independently re-added the import as an experiment, re-ran the suite: 14/17 tests failed (assert 422 == 200 on the happy-path test), restored the file, re-ran green again (17/17). The bug is real, reproducible, and the reasoning in the code comment is sound, not a cargo-culted convention override. |
| Three Unit 6 fix-pass claims re-verified end-to-end | Implemented, independently reconfirmed | Built a fresh create_app() + FakeEmbedder/in-memory repo outside the test suite and POSTed directly: 1121-char text -> 422, reason:"too_long", max_length:280; 300-char text (over semantic 280, under raw 1120) -> 422, reason:"too_long", max_length:280 (per apply-progress.md this is reached via the domain PhraseTooLong path, not independently distinguished as a separate code path by this pass beyond status/reason/detail); whitespace-only -> 422, reason:"empty". All three match the claimed values exactly. |
| GET /health issues zero embedding calls | Implemented | build_health_payload only reads HealthState fields; nothing in platform/health.py can reach an EmbeddingProvider. Test explicitly asserts embedder.call_count == 0 after a health check. |
| limit strictness matches design.md's PageLimit rule | Implemented | design.md line 937 states the strict-int rule ("10", true, 10.5 -> 422 invalid_type) verbatim; the test's parametrization ("10", True, 10.5) matches exactly, and reuses Unit 6's existing page_limit() implementation unmodified rather than reimplementing it. |
| _MostSimilarOut/_MatchOut merge into _ScoredPhrase | Implemented | router.py defines only one such model, _ScoredPhrase(id, text, score), reused for both most_similar and matches[]. Pure dedup, no behavior change. |
| size:exception documentation accuracy | Implemented with a minor discrepancy | See WARNING 2 below -- the documented "466 insertions / 2 deletions" for the 6 code/test files is off by 1 insertion versus git show --numstat ae247d1 (actual: 465/2). Consistent across tasks.md, apply-progress.md and PR #21's body (all three say the same number), so it is self-consistent, just not bit-for-bit accurate against the real diff. |
| No AI/Claude co-authorship in commits | Confirmed | git show authorship for ae247d1 and a158ce2 both show author "Aaron Rojas", no Co-Authored-By trailer of any kind in either commit message. |

### Coherence (Design)
| Decision | Followed? | Notes |
|----------|-----------|-------|
| D9 -- validate takes no cursor, silently ignored via extra="ignore" | Yes | Matches design.md's D9 row verbatim; test proves it via a cursor key that is accepted-but-ignored, not rejected |
| D10 -- outermost CachingEmbeddingProvider, capacity=0 kill switch | Yes | similarity/container.py's wrap_with_cache implements exactly this; cold/warm test proves the cache is both invisible to the response and real (call_count == 1 across two identical calls) |
| D15 -- model/embedding_model/database key mapping shared between 200 and 503 bodies | Yes | build_health_payload uses identical keys in both branches, matching design.md's stated "one key mapping, everywhere" rule |
| import-linter composition-root-owns-adapters contract (phrases.api never imports an adapter) | Yes | router.py imports only phrases.container.PhrasesContainer and phrases.api.schemas, never an adapter; lint-imports independently re-run clean (5 kept, 0 broken) |
| Unit 8 scope boundary ("real provider wiring is Unit 8's job") | Yes, and genuinely trimmed to it | The speculative main.py lifespan hook and build_embedding_provider were removed during the trim pass specifically because nothing in this unit's own tests needed them -- confirmed absent from both files as shipped |

### Issues Found

**CRITICAL**: None.

**WARNING**:

1. apply-progress.md's own prose (and PR #21's body, which repeats it) describes the test file as "17 test functions, several parametrized -- 24 total cases." Independently collected the file with pytest tests/contract/test_validate_health.py -q --collect-only: it actually contains 10 test functions / 17 total collected cases (test_limit_bounds_are_enforced_inclusively x4, test_strict_integer_limit_rejects_non_strict_values x3, test_provider_failure_and_timeout_map_to_their_registered_codes x2, test_health_not_ready_reports_which_component_is_down x2, plus 6 non-parametrized functions = 17 cases from 10 functions). The Verify command's reported "17 passed" is correct and matches what I independently measured -- only the descriptive "17 functions / 24 cases" sentence is wrong on both numbers. Low impact (doesn't change scenario coverage or pass/fail truth), but should be corrected in apply-progress.md and the PR body for accuracy.

2. The size:exception line count is off by one line from the actual measured diff. tasks.md, apply-progress.md, and PR #21's body all state "466 insertions / 2 deletions" (468 total changed lines) for the 6 code/test files. Independently measured via git show --numstat ae247d1 (the only commit touching those 6 files): main.py +28/-2, router.py +73/-0, phrases/container.py +36/-0, similarity/container.py +23/-0, health.py +65/-0, test_validate_health.py +240/-0 -> 465 insertions / 2 deletions (467 total), not 466/468. The 1-line discrepancy is immaterial to the exception decision itself (467 is still ~67 lines / ~17% over the 400 cap, same magnitude as the documented ~68/17%), and the number is at least self-consistent across all three artifacts, but it does not match git's own count exactly, which the task explicitly asked to confirm.

3. platform/health.py's own module docstring (lines 1-8) states "the model is warmed once, in main.py's lifespan hook" -- but the trim pass (round 5, documented in apply-progress.md) removed main.py's lifespan hook entirely; main.py as shipped has no lifespan hook at all (app.state.health is a static dataclass literal, not something a hook constructs). This is stale documentation left over from before the trim -- the comment describes a mechanism that does not exist in this unit's shipped code (presumably intended as forward-looking for Unit 8, but reads as describing current behavior). Should be corrected to say the lifespan wiring is Unit 8's future job, not the present unit's.

**SUGGESTION**:

1. Given that /health always reports "not ready" and /phrases/validate always 500s against the real, unmodified create_app(settings) object today, consider a single smoke test that hits the actual app.main.app module-level instance directly (every current test instead builds its own app and re-wires state) to lock in this documented interim behavior as a regression guard -- so that if a future partial-wiring change accidentally sets one of app.state.health/app.state.phrases without the other, or wires a broken provider, this "honestly not ready" state doesn't quietly change to "silently wrong" the way it's currently only protected by prose (main.py's docstring and code comments) rather than a test. Not required for this unit to ship -- Unit 8 owns the real wiring -- but worth doing whenever Unit 8 lands.

### Verdict

PASS WITH WARNINGS

All 2 tasks complete, all 15 named spec scenarios have a passing, independently-reconfirmed covering test, all quality gates (pytest x2, ruff, mypy, lint-imports) reproduce exactly as documented, the from __future__ import annotations omission and the "not wired to production" deviation are both genuine and honestly disclosed (verified by direct experiment and code reading, not by trusting the write-up), and no AI/Claude co-authorship appears in either commit. The three WARNINGs are all documentation-accuracy issues in apply-progress.md/tasks.md/PR #21 (a wrong test-count sentence, a 1-line-off size:exception measurement, and a stale docstring referencing a since-removed lifespan hook) -- none of them affect the actual shipped behavior, test coverage, or the substantive size:exception decision, which remains valid either way (467 or 468 total, both ~17% over the 400-line cap).

## Verification Report - Unit 7

**Change**: phrase-validation
**Version**: N/A
**Mode**: Strict TDD
**Scope**: POST /phrases, POST /phrases/matches (tasks 7.1-7.3). GET /phrases and OpenAPI documentation were deliberately deferred to Unit 7b via tasks.md named seam -- confirmed accurately recorded, not re-litigated as a gap.

### Completeness
| Metric | Value |
|--------|-------|
| Unit 7 tasks total | 3 (7.1, 7.2, 7.3) |
| Unit 7 tasks complete | 3/3, all checked |
| Unit 7b tasks total | 2 (7b.1, 7b.2) |
| Unit 7b tasks complete | 0/2, both unchecked -- confirmed genuinely NOT started: git ls-files shows no tracked list_phrases.py, test_list_phrases.py, test_openapi.py, or docs/openapi.json; only stale __pycache__ bytecode remnants exist from the documented build-then-delete cycle, no source. |

### Build and Tests Execution (independently re-run, not trusted from apply-progress.md)
**Unit own Verify command**:
```
$ cd services/api && .venv/Scripts/python.exe -m pytest tests/contract tests/integration/test_endpoints_pgvector.py -q
50 passed, 2 warnings in ~2.0s
```
Re-run 3 times consecutively -> 50 passed every time. Also re-run with tests/integration/test_endpoints_pgvector.py FIRST and tests/contract SECOND (reversed collection order, see DATABASE_URL trace below) -> 50 passed, no change in outcome.

**Full regression**:
```
$ pytest -m "not integration and not slow" -q
232 passed, 35 deselected, 2 warnings
```

**Full integration** (real Postgres, todo-ia-db-1 already healthy):
```
$ pytest -m integration -q
35 passed, 232 deselected, 2 warnings in ~43s
```

**Concurrency test isolation -- 5/5 standalone runs** (per this session Unit 5b flakiness precedent, a single green run was treated as insufficient evidence):
```
$ pytest tests/integration/test_endpoints_pgvector.py::test_concurrent_identical_saves_yield_exactly_one_201_and_one_409 -q
Run 1: 1 passed  |  Run 2: 1 passed  |  Run 3: 1 passed  |  Run 4: 1 passed  |  Run 5: 1 passed
```
All exact counts (50 / 232 / 35) match tasks.md and apply-progress.md claims exactly.

**Quality gates**:
```
$ ruff check src tests        -> All checks passed!
$ mypy src                    -> Success: no issues found in 38 source files
$ lint-imports                -> Contracts: 5 kept, 0 broken.
```

### Spec Compliance Matrix (Unit 7 shipped scope only)
| Requirement | Scenario | Test | Result |
|-------------|----------|------|--------|
| api-contract POST /phrases | Created unique | test_save_created_unique_records_null_metadata_and_normalizes_text | COMPLIANT |
| api-contract POST /phrases | Conflict shape | test_save_conflict_shape_and_payload_completeness | COMPLIANT |
| api-contract POST /phrases | Created confirmed | test_save_created_confirmed_records_score_and_neighbor | COMPLIANT |
| api-contract POST /phrases | Strict boolean flag | test_save_non_boolean_confirm_duplicate_rejected (yes, 1, true) | COMPLIANT |
| api-contract POST /phrases | Text is stored normalized | test_save_created_unique_records_null_metadata_and_normalizes_text (whitespace/zero-width input -> Hola) | COMPLIANT |
| phrase-management Persistence | Unique phrase metadata (over HTTP) | test_save_created_unique_records_null_metadata_and_normalizes_text | COMPLIANT |
| phrase-management Persistence | Confirmed duplicate metadata (over HTTP) | test_save_created_confirmed_records_score_and_neighbor | COMPLIANT |
| duplicate-confirmation Explicit flag | Non-boolean flag | test_save_non_boolean_confirm_duplicate_rejected | COMPLIANT |
| duplicate-confirmation 409 payload | Payload completeness | test_save_conflict_shape_and_payload_completeness (3-match fixture, score-desc order, has_more=false) | COMPLIANT |
| duplicate-confirmation 409 payload | Large match set on 409 | test_save_large_match_set_on_409_next_cursor_usable_with_matches (120-fixture, 50/50/20 walk) | COMPLIANT |
| duplicate-confirmation Failures never save | Model down (503/504) | test_save_provider_failure_never_persists (parametrized EmbeddingUnavailable/EmbeddingTimeout) | COMPLIANT |
| duplicate-confirmation Failures never save | DB down -> 500 | test_save_database_unreachable_is_500_and_persists_nothing | COMPLIANT |
| phrase-management Concurrency | Unique violation maps to 409, never 500 (HTTP) | test_save_unique_violation_on_insert_maps_to_409_never_500 (unit-level) plus test_concurrent_identical_saves_yield_exactly_one_201_and_one_409 (real Postgres, real thread race) | COMPLIANT |
| api-contract POST /phrases/matches | 8 named cursor/pagination/schema scenarios | test_matches_pagination_walk_from_validate, test_matches_response_has_no_verdict_fields, test_matches_invalid_cursor_is_400 (x4), test_matches_schema_violations_are_422 (x3) | COMPLIANT |

**Compliance summary**: every scenario in Unit 7 own Covers line for the shipped scope has a passing, independently-reconfirmed covering test. GET /phrases (List shape, Empty, Hard cap), phrase-management "List phrases" (Newest first, Empty list, Metadata exposed), and OpenAPI documentation (x4) are correctly absent -- deferred to Unit 7b, not a Unit 7 gap.

### Correctness (Static + Runtime Evidence) -- targeted deep-dive items

**1. Import-linter fix (409 envelope built inline vs. error_envelope helper) -- no format drift found.**
Compared byte-for-byte with a direct interpreter check:
```python
inline  = {"error": {"code": "DUPLICATE_CONFIRMATION_REQUIRED", "message": "msg", "details": {"a": 1}}}
helper  = error_envelope("DUPLICATE_CONFIRMATION_REQUIRED", "msg", {"a": 1})
inline == helper  # True
list(inline["error"]) == list(helper["error"]) == ["code", "message", "details"]  # True
```
router.py inline dict for the 409 body (error/code/message/details, details built via _verdict_details) produces the exact same key set and key order as platform/errors.py error_envelope for the case where details is not None (which is always true here, since _verdict_details never returns None). The import-linter finding and its fix are both genuine and correctly documented -- platform.errors does transitively import similarity.domain.errors, confirmed by reading errors.py own docstring and imports; lint-imports output (5 kept, 0 broken) confirms the fix holds today.

**2. Concurrent-save integration test is a genuine race, not a false negative waiting to happen.**
Read test_concurrent_identical_saves_yield_exactly_one_201_and_one_409: two ThreadPoolExecutor(max_workers=2) futures both call client.post("/phrases", ...) against the SAME TestClient/engine, with no barrier, event, or ordering primitive forcing a winner. save_phrase is a plain def handler (not async def), so Starlette run_in_threadpool genuinely dispatches each call to a separate worker thread, and both race for the same Postgres advisory lock inside SavePhrase. 5/5 standalone runs passed; 3 additional runs of the full combined Verify command passed; a reversed-collection-order run also passed. No flakiness observed across 8 total executions of the specific assertion path.

**3. os.environ.setdefault("DATABASE_URL", ...) in test_endpoints_pgvector.py does not reintroduce the Unit 6 cross-file pollution bug, and does not shadow a developer-set custom DATABASE_URL.**
Traced both mutation mechanisms together:
- tests/contract/conftest.py sets a FAKE placeholder (contract:contract@...) only if DATABASE_URL is absent, and deletes it in pytest_collection_finish (which fires after ALL collection, including test_endpoints_pgvector.py import) only if the value is still exactly that placeholder.
- test_endpoints_pgvector.py uses setdefault with the SAME real default every sibling integration file (test_nearest_and_uow.py, test_find_matches.py, test_schema.py) already falls back to independently -- it never overwrites an existing value, fake or real.
- If a developer has a custom DATABASE_URL already exported, conftest.py detects the var is already set and does not touch it, and does not delete it afterward -- the developer value survives untouched through both mechanisms.
- Verified empirically: running the exact Verify command (tests/contract then tests/integration/test_endpoints_pgvector.py) and the REVERSED order both pass 50/50. In the reversed order, test_endpoints_pgvector.py setdefault fires first (setting the real default, since nothing was set yet), then conftest.py detects the var already present and neither overwrites it with the placeholder NOR ever deletes it afterward. This is a real, order-dependent difference in final env state (real-default value persists for the whole session vs. being deleted after collection), but it is harmless in practice: contract tests never read Settings.database_url for anything that touches a real database (they use InMemoryUnitOfWorkFactory/fakes exclusively), and Settings() never attempts a DB connection at construction. No functional divergence was observed in either order. Flagged as WARNING (fragility/coupling between two independently-authored env-mutation mechanisms whose interaction depends on collection order), not CRITICAL, since it does not currently cause incorrect behavior in either order and both fallback values are identical, legitimate real defaults -- see Issues below.

**4. 409 payload Payload completeness / Large match set on 409 reuse Unit 3 shared machinery, not a reimplementation.**
SavePhrase._conflict (unchanged from Unit 3, services/api/src/app/modules/phrases/application/save_phrase.py) calls uow.repo.find_matches(...) then build_matches_page(page, self._policy, comparison=comparison) -- the exact same shared helper from phrases/application/_shared.py used by ValidatePhrase/ListMatches. router.py _verdict_details only maps the resulting VerdictView to a wire dict; it performs no independent pagination or match-scoring logic. Confirmed no drift risk.

**5. StrictBool on confirm_duplicate genuinely rejects non-boolean truthy values.**
_SaveRequest.confirm_duplicate: StrictBool = False in router.py. test_save_non_boolean_confirm_duplicate_rejected is parametrized over "yes", 1, "true" and asserts 422 with field=confirm_duplicate, reason=invalid_type, plus confirms nothing was persisted. Re-ran this test in isolation -- passes; pydantic StrictBool does not coerce truthy non-bool values, confirmed both by static typing and the passing test.

**6. Text stored normalized confirmed both by test and by code path.**
test_save_created_unique_records_null_metadata_and_normalizes_text posts a phrase with leading/trailing whitespace plus an embedded zero-width space and asserts data.text equals the normalized form "Hola". SavePhrase.__call__ calls normalize_and_check_length (shared helper, same one used since earlier units) to produce (display, comparison), and _phrase_out maps phrase.text (the persisted display form) into the response -- the returned text is the normalized display form, not the raw input, both by test assertion and by tracing the code path.

### Coherence (Design)
| Decision | Followed? | Notes |
|----------|-----------|-------|
| design.md 409 body = full validate-shaped payload | Yes | _verdict_details produces exactly threshold/score/most_similar/matches/next_cursor/has_more, matching design.md line 950 |
| design.md confirm_duplicate StrictBool, yes/1/true -> 422 invalid_type | Yes | Matches design.md line 939 verbatim, confirmed by test |
| design.md POST /phrases/matches cursor required, limit optional strict-bounded | Yes | Matches design.md line 938 |
| design.md exact-scan (find_nearest_exact) under advisory lock for save, never HNSW | Yes | SavePhrase._attempt unchanged from Unit 3, calls find_nearest_exact |
| size:exception documentation accurate across artifacts | Yes | See size verification below |

### Size-exception verification (independently re-measured, not trusted from apply-progress.md)
```
$ git diff --numstat ea0a2c4 f12c23e -- <the 6 listed files>
7/1    main.py
134/5  router.py
23/6   container.py
280/0  test_phrases_endpoints.py
1/0    test_validate_health.py
109/0  test_endpoints_pgvector.py
-> 554 insertions / 12 deletions = 566 changed lines
```
This matches tasks.md, apply-progress.md, and PR #22 body EXACTLY -- no off-by-one discrepancy this time (unlike an earlier Unit size measurement flagged as a WARNING in a prior section of this report). Full branch diff (ea0a2c4..f454132, both commits, including openspec/ doc updates) independently measured at 919 insertions / 19 deletions (938 total), matching the batch context reported "919 additions / 19 deletions across 2 commits" exactly. The seam (moving GET /phrases + OpenAPI to Unit 7b) and the two trim rounds (890 -> 851 -> 570 -> 566) are consistently described in tasks.md Unit 7 Notes line, apply-progress.md Review-budget section, and PR #22 body -- all three agree on the numbers, the seam, and the declined 7a/7c split.

### Git and PR hygiene
- git show -s on both f12c23e and f454132: author Aaron Rojas (Aaron-Shrike GitHub account) on both, no Co-Authored-By trailer, no AI/Claude attribution in either commit message body. Clean.
- PR #22 (gh pr view 22): baseRefName develop, state OPEN, additions 919, deletions 19 -- matches the branch diff exactly. Body carries the size:exception callout, trim log, declined-split table, dependency diagram, and exact Verify output, all consistent with tasks.md/apply-progress.md.

### Unit 7b spot-check
tasks.md Unit 7b section (lines 246-253): Commit/Rollback lines present, Covers line lists exactly the 3+3+4 scenarios deferred from Unit 7 (GET /phrases x3, phrase-management List phrases x3, OpenAPI x4), both sub-tasks unchecked, "Needs: Unit 7 merged" dependency correctly stated. Confirmed genuinely unstarted (no tracked source files, see Completeness table above) -- not silently half-done.

### Issues Found

**CRITICAL**: None.

**WARNING**:

1. Order-dependent interaction between tests/contract/conftest.py DATABASE_URL placeholder/cleanup mechanism and test_endpoints_pgvector.py new os.environ.setdefault guard. When tests/contract collects before tests/integration/test_endpoints_pgvector.py (the documented Verify command order), the placeholder wins during collection and is cleaned up afterward, and the new guard is a no-op. When the order is reversed, the new guard real-default value is set first, and conftest.py own cleanup logic silently no-ops instead (since the var is already set), leaving the real-default value in os.environ for the rest of the session instead of being cleaned up. Verified empirically that both orders currently pass 50/50 with no functional divergence (contract tests never read Settings.database_url for real I/O), but the two mechanisms were authored independently and neither is aware of the other existence -- a future third file doing something similar could produce a genuinely surprising env state depending on collection order. Not a regression of the Unit 6 fake-placeholder-leak bug (both fallback values here are the same real default, never a fake one), but worth a one-line cross-reference comment in one or both files for future maintainers.

**SUGGESTION**:

1. Given list_phrases.py, test_list_phrases.py, test_openapi.py, and docs/openapi.json were all fully written and verified green before being deleted for the review-budget seam, consider committing them to a throwaway branch or gist before deleting in future similar seams (rather than relying purely on the prose reproduction notes in apply-progress.md) -- the notes here are unusually thorough and probably sufficient, but a literal diff/patch would remove any residual risk of Unit 7b implementer re-deriving something subtly different from what was already proven to work.

### Verdict

**PASS WITH WARNINGS**

All 3 Unit 7 tasks (7.1-7.3) are complete and independently re-confirmed: every named scenario in Unit 7 shipped Covers line has a passing covering test (re-run live, not trusted from the report), all three exact Verify commands reproduce their documented counts precisely (50/232/35 passed), all quality gates (ruff, mypy, lint-imports) are clean, the import-linter workaround introduces no format drift in the 409 envelope (verified byte-for-byte), the concurrent-save test is a genuine unsynchronized two-thread race that passed 5/5 standalone runs plus 3 more combined-command runs with zero flakiness, the DATABASE_URL defensive guard does not reintroduce the Unit 6 fake-placeholder pollution bug (traced through both mechanisms, verified empirically in both collection orders), the size:exception (566 changed lines) is accurately and consistently documented across tasks.md/apply-progress.md/PR #22 with an exact independent re-measurement match, no AI/Claude co-authorship appears in either commit, and Unit 7b is genuinely unstarted with no silent partial progress. The single WARNING is a latent (currently harmless) ordering fragility between two independently-written test-env-mutation mechanisms, not a functional defect.

---

## Full-System Verification Pass (all 17 units, cross-cutting)

**Change**: phrase-validation
**Scope**: this section is the requested comprehensive pass across every unit (0, 1, 2, 2b, 2c,
2d, 3a-3d, 4, 5a, 5b, 6, 6b, 7, 7b, 8, 9, 10, 11, 12, 13a-13c, 14, 15, 16, 16b) now that all are
merged to `develop`. It does not repeat the exhaustive per-unit depth already on record above
for Units 3, 4, 5a, 5b, 6, 6b and 7 (each independently re-executed and cross-checked in a prior
pass) -- those sections stand as-is and are treated as authoritative history for that scope. This
section instead (a) re-runs the full test/lint/type/import suite fresh, from a clean checkout
state, for real, (b) verifies task completeness across every unit, (c) targets the specific
cross-cutting invariants and deferred-item follow-through named in this pass's brief, and (d)
spot-verifies the units that had no prior dedicated verify section (0, 1, 2, 2b, 2c, 2d, 7b, 8, 9,
10, 11, 12, 13a-13c, 14, 15, 16, 16b).

**Correction to the task brief**: the brief this pass was launched with stated "this is the first
verify pass for this change -- no verify-report.md exists yet." That is factually incorrect --
verify-report.md already existed at 1360 lines with detailed, independently-re-executed
verification sections for Units 3, 4, 5a, 5b, 6, 6b and 7 (see above). This pass extends that file
rather than replacing it, per this skill's own graceful-handling instruction ("read it and decide
whether to extend or replace based on what's actually there").

### Task completeness (tasks.md, full re-read)

Every task checkbox from Unit B.0 through Unit 16b was read directly (not sampled) in this pass.
All are `[x]` except one: task 8.4 (`docker build -t todo-ia-api ...`, image size, p50/p95
`embed()` timing, warm-vs-cold `pytest -m slow` timing, write results to
`docs/evidence/runtime-measurements.md`) is still literally `[ ]` in tasks.md, originally BLOCKED
by "no docker in this environment." This is a real, live gap, not a stale artifact: `docker`
became available and was actually used for real in at least three later sessions (Unit 9's
follow-up calibration batch, Unit 14's compose build/smoke-test, and this pass's own build/run
below), yet task 8.4 itself was never revisited or checked off, and
`docs/evidence/runtime-measurements.md` does not exist on disk (confirmed: `docs/evidence/`
contains only `calibration.md` and `exact-scan-timings.md`). The image-size half of 8.4 is
informally captured (10.4 GB disk / 4.4 GB content, cited in ADR-008 and ADR-003, "measured Unit
16"), but the p50/p95 `embed()` latency and the warm-vs-cold `pytest -m slow` HTTP-level timing
pair were never measured or written anywhere. See Issues below.

### Real test execution (fresh, from a clean checkout, this session)

All commands below were executed directly in this session, not trusted from any prior report.

**Backend unit** (`pytest -m "not integration and not slow" -q`): 291 passed, 47 deselected --
matches the `develop` tip's expected growth from Unit 16b's own reported baseline.
`pytest tests/unit/test_decision_log.py -q` in isolation: 4 passed, 0 xfailed -- confirms the
one `xfail` present at Unit 16's own tip (README-linkage assertion) was genuinely resolved by Unit
15, not silently dropped.

**Frontend unit** (`cd apps/web && npm test`): 164 passed (10 test files) -- matches Unit 13c's
own tip count exactly, confirming zero regression through Units 14-16b (none of which touch
`apps/web`).

**Backend integration, real Postgres/pgvector via Docker Compose** (`docker compose up -d db
migrate` -- `migrate` exited 0, schema applied cleanly; `pytest -m integration -q`): 41 passed
with `DATABASE_URL` exported -- see the CRITICAL finding below, discovered by first running this
exact command from a genuinely clean shell (no `DATABASE_URL` pre-set), which is the natural state
for any reviewer following the README, and which is not how this suite has apparently ever been
exercised end-to-end before (every prior unit's own literal "Verify" line scopes only a subset of
`tests/integration/`, narrowly enough to avoid the interaction -- see below).

**Lint/type/import** (all re-run fresh): `ruff check .` -> clean. `mypy src` -> "Success: no
issues found in 43 source files" (the known pre-existing `sentence_transformers.py` Protocol
mismatch does not surface here because `sentence-transformers` itself is not installed in this
local dev venv -- same as every prior local mypy run in this project's history; see the dedicated
check below). `lint-imports` -> "Contracts: 5 kept, 0 broken."

**Full Docker Compose stack, real embedding model, this session** (`docker compose build
--progress=plain` then `docker compose up -d`, no `.env` file present, defaults sourced entirely
from `docker-compose.yml`'s `${VAR:-default}` interpolation, exactly as README.md claims): all
four services reached healthy --

```
todo-ia-db-1       healthy
todo-ia-migrate-1  Exited (0)
todo-ia-api-1      healthy
todo-ia-web-1      healthy
```

`GET /health` (curl, direct): status ok, database ok, model ready, dimensions 384, embedding_model
sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2, embedding_cache hits/misses/evictions
present -- the REAL model is loaded (not FakeEmbedder), correct dimension count, correct model id.
`GET /` on the web container: 200. `bash infra/scripts/smoke.sh` (validate -> save -> list, real
HTTP, real model, real Postgres): all three steps passed ("Smoke test passed: validate -> save ->
list all succeeded end to end."). This is the first time in this pass's own execution (not merely
re-read from apply-progress.md) that the complete stack -- real embedding model included -- was
proven to work end-to-end on `develop`'s current tip, after Units 15/16/16b landed on top of Unit
14's own original smoke-tested state; it corroborates Unit 14's own documented real run rather
than duplicating unverified claims. The stack was torn down cleanly afterward
(`docker compose down -v` -- containers, network and volume all removed, no side effects left).

### Cross-cutting invariant checks (this pass's specific brief)

**1. Embedding cache invariant ("never cache verdicts or pages", docs/architecture.md)**: the
doc section exists verbatim ("## The embedding cache invariant: never cache verdicts or pages",
docs/architecture.md line 134) and is consistent with CachingEmbeddingProvider's actual scope
(wraps only EmbeddingProvider.embed, never touches ValidatePhrase/ListMatches/SavePhrase
return values) -- already independently proven at the code+test level in this file's Unit 3, 5a, 5b
and 6b sections (cache-interplay tests, "Caching invisible to the contract" contract tests). No new
violation found.

**2. ADR-008 (exact-scan-on-save-path guarantee)**: read directly. Its claim -- SavePhrase derives
its verdict from find_nearest_exact (exact scan under the advisory lock), never HNSW, because an
approximate recall miss on save could store a duplicate as unique -- matches exactly what this
file's own Unit 5b section independently re-verified via a fresh, self-authored EXPLAIN script
and Unit 7's section independently re-verified via the save-path spy test. No drift found; the
ADR's cited pgvector tag/version/timings match Unit 4/5a's own independently-measured figures
already on record above.

**3. ADR-012 (reconciliation rule)**: read directly. Its claim -- validate takes score/
most_similar from matches[0] whenever matches exist (not from find_nearest's own result) --
matches this file's own Unit 3 "Correctness" table ("Reconciliation rule (matches[0] wins) |
Implemented | validate_phrase.py L46-49; spy test + 5-trial property test both pass"). No drift.

**4. Unit 11's deferred role="alertdialog", promised to Unit 12**: grepped the actual shipped
frontend code, not just tasks.md's prose. DuplicateAlert.tsx line 50:
`<div role="alertdialog" aria-labelledby="duplicate-alert-title">`, and
DuplicateAlert.test.tsx asserts `screen.getByRole("alertdialog")` in 7 separate test bodies
(content, percentage, confirm, cancel, 409-during-save, 409-while-confirming). Confirmed landed,
not silently dropped.

**5. Unit 6/6b's own deferred items**: Unit 6's own verify section (above) found a real CRITICAL --
the "Raw length cap" scenario's reason-mapping was wired incorrectly (string_too_long fell
through to invalid_type, no details.max_length). Re-checked the current main.py directly:
`_TOO_LONG_TYPES = {"string_too_long"}` now exists, `_reason_for` returns "too_long" for it, and
`details["max_length"]` is populated from pydantic's own ctx.max_length. A real contract test now
exercises this: tests/contract/test_framework_errors.py::test_raw_length_cap_is_422_too_long_with_max_length_detail.
Confirmed genuinely fixed and covered, not merely claimed. The Unit 6 verify section's other
WARNING (missing TDD Cycle Evidence table) is a reporting-completeness issue only, not re-checked
further here.

**6. .env.example known limitation (a)**: confirmed the file still does not exist on disk -- an
attempt to `ls .env*` in this session was itself denied by the tool-permission layer (the same
hard deny documented since Unit 0), reproducing the blocker rather than working around it, per this
pass's explicit instruction not to re-attempt a fix. README.md's own handling was read directly:
line 20's `cp .env.example .env` comment points to "the table below, copied verbatim from this
repo's own recorded intended content," and the "Environment variables" section (line 55 onward)
explicitly documents this exact absence and cross-references Settings/design.md. Confirmed
accurately reflected as a known, documented limitation, not silently missing.

**7. mypy Protocol structural mismatch in sentence_transformers.py (known limitation b)**:
confirmed still present in the adapter code (unchanged since Unit 9's follow-up batch) and still
undetectable by a local `mypy src` run in this environment, because sentence-transformers is not
installed in this dev venv (confirmed: `import sentence_transformers` -> ModuleNotFoundError),
exactly the same condition that let it slip through every prior local mypy run per
apply-progress.md's own account. No later unit (10-16b) touches this adapter file. Confirmed
still an accurately-documented, deferred, non-runtime-affecting known limitation -- this pass's
own live Docker run (see above) independently corroborates the "does not affect runtime
correctness" half of that claim: the real container, with the real installed package, embedded
phrases correctly end-to-end via smoke.sh and /health.

**8. Unit 7b's own honestly-disclosed gap** (PgVectorPhraseRepository.list_recent fix folded in,
but tests/contract_suite/repository_contract.py still has no shared scenario for list_recent on
either adapter): re-confirmed both halves directly. list_recent exists on both
PgVectorPhraseRepository (line 223) and InMemoryPhraseRepository (line 138) -- the fix genuinely
landed. Searching repository_contract.py for "list_recent" finds no matches -- the gap is still
genuinely open, exactly as disclosed, not silently missing without acknowledgment.

### New finding: `pytest -m integration` is not self-sufficient from a clean shell (regression of an already-flagged WARNING)

This file's own Unit 7 section already flagged (WARNING) an "order-dependent interaction" between
tests/contract/conftest.py's DATABASE_URL placeholder-and-cleanup mechanism and
tests/integration/test_endpoints_pgvector.py's defensive `os.environ.setdefault(...)` guard, and
concluded -- after testing both collection orderings of its own two named files -- "both orders
currently pass 50/50 with no functional divergence... not CRITICAL." That conclusion does not
hold for the actual, full, documented test commands when run from a genuinely clean environment
(no DATABASE_URL pre-set), which this pass did for the first time:

```
$ cd services/api && pytest -m integration -q          # clean shell, no DATABASE_URL set
...
ERROR tests/integration/test_endpoints_pgvector.py::test_post_phrases_returns_201_then_409_for_a_duplicate
ERROR tests/integration/test_endpoints_pgvector.py::test_concurrent_identical_saves_yield_exactly_one_201_and_one_409
ERROR tests/integration/test_endpoints_pgvector.py::test_get_phrases_returns_newest_first_against_real_postgres
38 passed, 297 deselected, 3 errors
```

Reproduced identically with Unit 7's own literal documented Verify command
(`pytest tests/contract tests/integration/test_endpoints_pgvector.py -q`), run from a clean shell:

```
$ env -u DATABASE_URL pytest tests/contract tests/integration/test_endpoints_pgvector.py -q
...
ERROR tests/integration/test_endpoints_pgvector.py::test_post_phrases_returns_201_then_409_for_a_duplicate
ERROR tests/integration/test_endpoints_pgvector.py::test_concurrent_identical_saves_yield_exactly_one_201_and_one_409
ERROR tests/integration/test_endpoints_pgvector.py::test_get_phrases_returns_newest_first_against_real_postgres
61 passed, 3 errors
```

**Root cause, traced through the actual mechanism** (not re-guessed): tests/contract/conftest.py
sets a fake placeholder DATABASE_URL only if absent, then its `pytest_collection_finish` hook --
which fires once, after ALL collection across the whole run, including
test_endpoints_pgvector.py's own module-level `os.environ.setdefault(...)` -- deletes it if it is
still exactly that placeholder. test_endpoints_pgvector.py's setdefault call is therefore a
no-op the moment tests/contract is collected first (the placeholder already won), so the variable
gets deleted by the cleanup hook before test execution begins. `_database_url()` then reads
`os.environ["DATABASE_URL"]` (bracket access, not `.get(...)` with a fallback, unlike every sibling
integration file) during the module-scoped fixture's actual execution (which happens later than
collection) and raises KeyError. The prior Unit 7 verify pass's own re-run only checked whether
this affected response correctness (it does not, since contract tests never read
Settings.database_url for real I/O) -- it did not check whether the deletion would later break
test_endpoints_pgvector.py's own fixtures, which is exactly what happens. This is why CI never
caught it: .github/workflows/ci.yml's backend-integration job sets DATABASE_URL as an
explicit job-level environment variable (confirmed by reading the workflow file directly), masking
the interaction entirely -- a fresh local reviewer following the README's own testing instructions
(`make test`, `pytest -m integration`) with no other guidance would hit this immediately.

This is a test-hermeticity / CI-masking defect, not a production runtime bug -- no application
code path is affected, and the API's actual behavior (confirmed by this pass's own live Docker
smoke test above) is correct. But it directly contradicts this project's own repeatedly-stated pass
counts for Unit 7 (50 passed) and Unit 7b (61 passed) under the literal command those units
document as their own Verify line, the moment that command is run exactly as documented without an
undocumented prerequisite. Per this skill's own decision gate ("Test command exits non-zero ->
CRITICAL"), this is classified CRITICAL below, scoped narrowly to test-suite reproducibility (not
to correctness of the shipped feature).

### Issues Found (this Full-System pass)

**CRITICAL**:
1. `pytest -m integration -q`, and Unit 7's/7b's own literally-documented Verify command
   (`pytest tests/contract tests/integration/test_endpoints_pgvector.py -q`), genuinely FAIL (3
   ERRORs, not merely a documentation nit) when run from a clean shell without DATABASE_URL
   pre-set -- the default condition for any reviewer following the README's own testing
   instructions. Masked only by CI setting DATABASE_URL as a job-level env var. Root cause traced
   above: an interaction between tests/contract/conftest.py's placeholder-cleanup hook and
   tests/integration/test_endpoints_pgvector.py's `os.environ["DATABASE_URL"]` (bracket access,
   no fallback) in its module-scoped fixture. Fix is small and well-scoped (make
   `_database_url()` use `os.environ.get("DATABASE_URL", <the same real default every sibling file
   already falls back to>)` instead of bracket access -- mirrors every other integration file in this
   codebase and removes the dependency on collection order entirely) but is a genuine, currently-live
   defect in the test suite's own claimed reproducibility, not a stale or already-superseded finding
   -- this pass independently reproduced it fresh, twice, with two different commands.

**WARNING**:
1. Task 8.4 (image size, p50/p95 embed() timing, warm-vs-cold pytest -m slow timing,
   docs/evidence/runtime-measurements.md) remains unchecked in tasks.md and its target evidence
   file does not exist, even though Docker was demonstrably available and used for real in at least
   three later sessions (Unit 9's follow-up, Unit 14, and this pass). The image-size half is
   informally captured in ADR-008/ADR-003 prose only; the latency-timing half was never captured
   anywhere. Low risk (the feature works, confirmed end-to-end with the real model by this pass's
   own smoke test), but it is a real, still-open gap against the change's own task list and a
   proposal.md Delivery-Plan-scoped deliverable, not merely a superseded historical blocker.

**SUGGESTION**:
1. Now that Docker is confirmed available in this environment, task 8.4's remaining scope (p50/p95
   embed() timing, warm-vs-cold pytest -m slow HTTP timing pair) is cheap to close in a small
   follow-up batch, reusing the same api-builder Docker stage Unit 9's follow-up already
   demonstrated working.
2. Add a one-line cross-reference comment between tests/contract/conftest.py and
   tests/integration/test_endpoints_pgvector.py (as Unit 7's own verify section already
   suggested) -- and, more directly, fix `_database_url()` to use `.get(...)` with a fallback,
   which independently removes both the collection-order fragility Unit 7 flagged AND the concrete
   failure this pass found, in one small change.

### Verdict

**PASS WITH WARNINGS, plus one CRITICAL scoped to local test-suite reproducibility (not to the
shipped product)**. All 17 units' tasks are complete except the single, honestly-still-open task
8.4 (evidence-gathering only, not a behavior gap). Every spec requirement this pass sampled across
the five capability specs has real, passing, independently-re-run test evidence; the specific
cross-cutting invariants and deferred-item follow-throughs named in this pass's brief (cache
invariant, ADR-008, ADR-012, Unit 11->12 alertdialog handoff, Unit 6/6b's raw-length-cap fix, both
named known limitations) all check out exactly as documented, with zero silent regressions found.
The full Docker Compose stack, including the real embedding model (not FakeEmbedder), was built
and run fresh in this session and passed its own end-to-end smoke test (validate -> save -> list)
against real Postgres/pgvector. The one CRITICAL finding is new, real, and reproduced independently
twice with two different commands: the backend integration suite is not hermetic from a clean shell
without an undocumented DATABASE_URL export, contradicting this project's own claimed Unit
7/7b pass counts under their own literal Verify commands -- a small, well-understood, low-risk fix
(documented above), but a genuine blocker to trusting "run the tests" as a self-sufficient
onboarding instruction until it is applied. This does not indicate any defect in the shipped
API behavior itself (independently re-proven correct, end-to-end, with the real model, by this
pass's own Docker smoke test) and does not block archive on its own merits, but should be fixed (or
explicitly accepted as a known limitation, the way .env.example and the mypy Protocol mismatch
already are) before this change is considered fully closed.

### Resolution (post-verify fix, branch `fix/verify-database-url-hermeticity`)

The CRITICAL above was fixed immediately following this verify pass. `_database_url()` in
`tests/integration/test_endpoints_pgvector.py` now reads `os.environ.get("DATABASE_URL", <the same
real default every sibling file falls back to>)` instead of unconditional bracket access, matching
`tests/contract/conftest.py`'s own docstring, which already assumed this lazy-read-with-fallback
shape. RED confirmed by reverting the fix and re-running the exact repro (`unset DATABASE_URL &&
pytest -m integration -q`) from a genuinely clean shell: 3 ERRORs, identical to this pass's own
finding. GREEN confirmed after restoring the fix: **41 passed, 0 errors**, same clean-shell
conditions. No regressions: `ruff check` clean on the changed file; full non-integration suite
`291 passed, 1 deselected`, unchanged from this pass's own count. Task 8.4 (WARNING, evidence-
gathering only) remains open and is not addressed by this fix -- tracked separately.

### Resolution (task 8.4, post-verify follow-up, branch `feat/pv-08b-runtime-measurements`)

The WARNING above was closed immediately following this verify pass, in the same session. Docker
was confirmed available (as this pass's own finding already noted) and used to close both remaining
halves of task 8.4:

- **Image size**: `docker build -t todo-ia-api services/api` (fully cached rebuild, confirming the
  image is current) + `docker images todo-ia-api` -> **10.4 GB disk / 4.4 GB content size**
  (`docker inspect --format '{{.Size}}'` -> 4,400,446,152 bytes). Same figure this pass's own prose
  already cited informally from ADR-008/ADR-003; now recorded in a dedicated evidence file and
  re-confirmed by an independent rebuild rather than trusted from a prior session's cached number.
- **`embed()` p50/p95 latency**: a one-off timing script (not a new pytest file -- simple scope per
  this follow-up's explicit instructions) run inside `todo-ia-api:latest` with the offline env vars
  set, 50 real calls against the baked model -> **p50 13.23 ms / p95 15.12 ms**. This was genuinely
  never measured anywhere before this follow-up, exactly as this pass found.
- **Warm-vs-cold HTTP timing pair**: `docker compose up -d db migrate api` (real Postgres/pgvector +
  real model), 5 cold/warm pairs each for `POST /phrases/validate` and `POST /phrases` via
  `curl -w "%{time_total}"` -> ~15 ms/request saved on cache hit (~65-68%), consistent with the raw
  `embed()` timing above. Stack torn down (`docker compose down -v`) after measurement; built images
  left cached.

`docs/evidence/runtime-measurements.md` (new) records the full numbers and methodology; ADR-003 and
ADR-011 were updated to cite the real values in place of their prior UNMEASURED/ESTIMATE language;
`tasks.md`'s 8.4 is now `[x]`. Task 8.4 is now genuinely closed -- both halves measured for real, not
estimated or fabricated. All 17 units' tasks are now complete; the one remaining verdict item from
this pass's own Verdict section is the CRITICAL DATABASE_URL hermeticity finding, already resolved
above (`fix/verify-database-url-hermeticity`).
