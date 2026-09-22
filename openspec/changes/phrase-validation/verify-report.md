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
