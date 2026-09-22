# Tasks: Phrase Validation with Semantic Duplicate Detection

Source of truth: `design.md` (Delivery Plan, slice order and estimates), the five specs under `specs/*/spec.md`, `proposal.md`.
Strict TDD is ON: inside every unit write RED (failing test) -> GREEN -> REFACTOR locally, then commit RED+GREEN **squashed per unit** (one green, bisectable commit per unit). Tests, docs and verification evidence ship in the same unit as the behaviour.

## Review Workload Forecast

| Field | Value |
|-------|-------|
| Estimated changed lines | ~6,090 across 21 units (largest ~380, none above 400) |
| 400-line budget risk | High (as a single change); Low per unit |
| Chained PRs recommended | Yes |
| Suggested split | 21 stacked PRs, one per unit, merged to `main` in order (below) |
| Delivery strategy | ask-on-risk (risk confirmed and resolved with the user) |
| Chain strategy | stacked-to-main |

Decision needed before apply: No
Chained PRs recommended: Yes
Chain strategy: stacked-to-main
400-line budget risk: High

Notes:
- "Decision needed before apply: No" because the ask-on-risk question was already asked and answered (stacked-to-main). Do not mix strategies afterwards.
- **Supersedes** the design's Delivery Plan wording "Feature Branch Chain / PR #1 targets the tracker branch": the user chose stacked-to-main, so there is NO tracker branch; every PR targeted `main` through Unit 3.
- **Branch strategy change effective Unit 4 (decided 2026-09-22):** every PR from Unit 4 onward targets `develop`, not `main`. `develop` is an integration branch currently identical to `main`; CI/CD (`.github/workflows/ci.yml`) only fires on push/PR against `main`, not `develop`, to save CI minutes while units land frequently. Promoting `develop` into `main` is a separate, manual step the user triggers when they want a CI-validated checkpoint (e.g. before a milestone or the eventual `sdd-archive`) — it is NOT part of any individual unit's task list. Units B.0 through 3d already merged to `main` before this decision and are left as historical record below; do not retarget them.
- The repo has no commits. Untracked `.atl/`, `docs/`, `openspec/` exist. Task B.0 below makes the root commit (planning artifacts only, no code, exempt from the code budget). Confirm whether `.atl/` should be git-ignored (default: ignore it).
- Budget is `additions + deletions`. Generated files (`docs/openapi.json`, `apps/web/src/types/api.ts`, lockfiles) are excluded from the count only if the reviewer agrees; otherwise commit lockfiles with the unit that adds the dependency and check with `git diff --stat` before opening the PR. If a unit exceeds 400, split at the seam named in its Notes instead of asking for `size:exception`.

### PR chain (stacked-to-main through Unit 3, stacked-to-develop from Unit 4)

Rule through Unit 3 (historical): branch N was cut from `main` after PR N-1 merged (or from branch N-1 when authoring ahead, then rebased onto `main` and retargeted the moment N-1 merged). PR base was ALWAYS `main`.

Rule from Unit 4 onward: branch N is cut from `develop` after PR N-1 has merged into `develop` (or from branch N-1 when authoring ahead, then rebased onto `develop` and retargeted to `develop` the moment N-1 merges). PR base is ALWAYS `develop`; a diff that shows the previous unit's changes means the base is wrong. `develop` is never merged into by anything except these unit PRs; promoting `develop` -> `main` is a separate manual action outside this table. Each PR body carries a dependency diagram with the current PR marked with the pin emoji, plus start, end, prior dependencies, follow-ups and out-of-scope.

| PR | Branch | Base | Unit | Est. lines |
|----|--------|------|------|-----------|
| B.0 | `chore/pv-bootstrap-artifacts` | `main` (root commit) | SDD/planning artifacts | n/a |
| 0 | `chore/pv-00-scaffold` | `main` | scaffold | ~150 |
| 1 | `feat/pv-01-domain-policy` | `main` | normalization + policy | ~340 |
| 2 | `feat/pv-02-ports-inmemory` | `main` | ports, fakes, contract suite | ~340 |
| 2b | `perf/pv-02b-embedding-cache` | `main` | caching decorator | ~180 |
| 2c | `feat/pv-02c-cursor-codec` | `main` | cursor codec | ~150 |
| 3 | ~~`feat/pv-03-use-cases`~~ | ~~`main`~~ | ~~use cases~~ — **superseded by the 3a-3d split below** (PR #11 closed unmerged; budget CRITICAL from `sdd-verify`) | ~~~350~~ |
| 3a | `feat/pv-03a-validate` | `main` | validate use case | ~430 |
| 3b | `feat/pv-03b-list-matches` | `feat/pv-03a-validate`* | list-matches use case | ~140 |
| 3c | `feat/pv-03c-save` | `feat/pv-03b-list-matches`* | save use case | ~390 |
| 3d | `feat/pv-03d-cache-interplay` | `feat/pv-03c-save`* | cache-interplay tests | ~125 |
| 4 | `feat/pv-04-schema-migrations` | `develop` | schema + compose db/migrate | ~340 |
| 5a | `feat/pv-05a-find-matches` | `develop` | exact keyset `find_matches` | ~330 |
| 5b | `feat/pv-05b-nearest-uow` | `develop` | `find_nearest`, exact, UoW, lock | ~350 |
| 6 | `feat/pv-06-api-foundation` | `develop` | settings, errors, CORS | ~300 |
| 6b | `feat/pv-06b-validate-health` | `develop` | validate + `/health` | ~250 |
| 7 | `feat/pv-07-save-list-matches` | `develop` | save, list, matches | ~380 |
| 8 | `feat/pv-08-embeddings-image` | `develop` | ST adapter, bounded, wiring, image | ~380 |
| 9 | `test/pv-09-calibration` | `develop` | ES/EN fixture + evidence | ~150 |
| 10 | `feat/pv-10-web-scaffold` | `develop` | web scaffold + client | ~300 |
| 11 | `feat/pv-11-web-machine-form` | `develop` | state machine + form | ~360 |
| 12 | `feat/pv-12-web-duplicate-alert` | `develop` | alert + infinite scroll | ~310 |
| 13 | `feat/pv-13-web-list-copy` | `develop` | list, badges, copy | ~290 |
| 14 | `feat/pv-14-compose-wiring` | `develop` | full compose | ~200 |
| 15 | `docs/pv-15-readme-architecture` | `develop` | README + architecture | ~300 |
| 16 | `docs/pv-16-decision-log` | `develop` | ADRs | ~340 |

*3b/3c/3d are cut authoring-ahead from the immediately preceding sub-unit's branch (same pattern
already used for 2/2d/2c/2b against an unmerged `feat/pv-02-ports-inmemory`) and MUST be rebased
onto `main` and retargeted the moment the branch they were cut from merges — each will show as
stacked on its parent in GitHub until then, which is expected, not a mistake.

### Dependency and parallelism

Merge order is strictly linear (1 PR at a time on `main`). Authoring can overlap where there is no code dependency:
- After 2 merges: **2b and 2c can be authored in parallel** (both need only the ports); 3a needs 2,
  2b, 2c (same as the original Unit 3); 3b needs 3a merged (or authored-ahead against it) for
  `_shared.py`; 3c needs 3b for the same reason; 3d needs 3a, 3b AND 3c (it exercises all three use
  cases together).
- **4 is independent of 1-3** (needs only 0); it can be authored any time after 0. 5a needs 2 and 4; 5b needs 5a.
- 6 needs 0 only; 6b needs 3d (the full Unit 3 use-case set), 6 and (for readiness) 5b; 7 needs 6b, 2c, 5b.
- 8 needs 2b and 7. 9 needs 8. 10 needs 7 (`docs/openapi.json`). 11 -> 12 -> 13 sequential (shared `copy.es.ts`, machine). 14 needs 8, 13. 15, 16 last (they cite measured values from 5a, 8, 9, 14).
- Bottleneck: 3a-3d (needs 2, 2b, 2c, then each other in sequence) and 7 (gates the whole web track and OpenAPI). Sole owner per unit is the apply agent; no shared-file ownership conflicts except `openspec/config.yaml` (touched by 0 only) and `docs/decisions/*` (touched by 16 only; earlier units append measured numbers to `docs/evidence/` notes, not ADRs).

---

## Unit B.0: Bootstrap commit (planning artifacts)

- [x] B.0.1 ~~Add `.gitignore` entry for `.atl/`... root commit.~~ **Superseded by prior history**: `.gitignore` already ignores `.atl/` (added in `a18d040 chore: add gitignore`), and `openspec/` + `docs/` are already tracked and merged to `main` via PR #1 (`70a4d1f`..`80283cb`, including `77ff080 chore(sdd): initialize openspec context and testing capabilities` through `dc2b403 docs(sdd): align design delivery plan with stacked-to-main`). `git status` is clean at the start of this apply batch. No new branch/commit was created for B.0 — the outcome this task exists to guarantee (planning artifacts tracked, `.atl/` ignored, clean tree) was already true. See apply-progress.md for detail.

## Unit 0: Scaffold monorepo (`chore: scaffold monorepo`, ~150)

Goal: runnable empty skeleton with test runners installed and enforced boundaries. Covers: semantic-validation "Domain isolation" (import-linter contracts declared), api-contract "Env documented" (`.env.example` complete).
- [x] 0.1 RED: `services/api/tests/unit/test_smoke.py` (asserts `import app`), `apps/web/src/smoke.test.ts` (asserts `1 === 1`) so both runners are proven executing.
- [x] 0.2 GREEN: `services/api/pyproject.toml` (deps: fastapi, pydantic-settings; dev: pytest, pytest-cov, httpx, ruff, mypy, import-linter; markers `unit`, `integration`, `contract`, `slow`), `services/api/src/app/__init__.py`, `.importlinter` with the five boundary contracts from design (similarity independence, phrases -> only `similarity.contracts`, domain purity, application not importing adapters/api, only main/container import adapters).
- [x] 0.3 GREEN: `apps/web/package.json` (vitest, typescript, prettier, eslint devDependencies; script `test`: `vitest run`), `apps/web/vitest.config.ts`. Next.js itself arrives in unit 10.
- [~] 0.4 Root `.env.example` listing EVERY var of the design Configuration table except the two image-fixed ones (`HF_HUB_OFFLINE`/`TRANSFORMERS_OFFLINE`, `SENTENCE_TRANSFORMERS_HOME`); `.gitignore`; `Makefile` targets `test`, `test-unit`, `test-slow`, `evidence`, `types`, `up`, `lint` (`ruff`, `mypy`, `lint-imports`); CI lint stub `.github/workflows/ci.yml` (lint + unit only). **`.env.example` NOT created**: the apply agent's tool permissions hard-deny writes to any `.env*` path, including `.env.example` (confirmed: `env.example` with no leading dot writes fine; `.env.example`/`.env.example.tmp` are denied outright). `.gitignore`, `Makefile` and `.github/workflows/ci.yml` ARE done. Full intended content is saved in the session scratchpad and reproduced verbatim in apply-progress.md for a human (or a session with broader permissions) to create.
- [x] 0.5 Update `openspec/config.yaml`: `testing.status: installed`, `apply.test_command` and `verify.test_command` = `make test-unit` (runs `cd services/api && pytest -m "not integration and not slow"` then `cd apps/web && npm test`), `build_command` empty until unit 10. Recorded detected versions: pytest 9.1.1, vitest 5.0.1 (also ruff 0.16.8, mypy 2.3.1, typescript 7.0.2, prettier 3.9.8, eslint 10.11.0) — see commit body and `openspec/config.yaml`.
- Verify: `make test-unit` green (2 smoke tests), `lint-imports` passes, `pytest --collect-only -q` lists 4 markers without warnings.
- Commit: `chore: scaffold monorepo with pytest, vitest and import-linter`. Rollback: revert; no runtime code exists.

## Unit 1: Normalization, clamped score, similarity policy (~340)

Commit: `feat(domain): normalization forms, clamped score and similarity policy`. Rollback: revert (pure functions, no callers yet).
Covers (phrase-management): Text normalization x7 (Trim and NFC; Zero-width and control chars stripped; Whitespace controls separate words; ZWJ and ZWNJ preserved; Comparison form re-normalizes after casefold; Emoji and RTL preserved; Idempotent), Empty text rejection: Empty string, Whitespace and invisible-only; Maximum length: Exactly at limit, One over limit, Padding does not count (domain rule on code points after trim). (semantic-validation): Cosine similarity x6 (Identical, Orthogonal, Rounding consistency, Negative clamped, Float overshoot clamped, Oracle agreement - pure-Python side), Threshold decision x5 (t-eps, t, t+eps, >4 decimals, threshold zero), Exact duplicates: Case and spacing variants (domain side).
- [x] 1.1 RED then GREEN `services/api/src/app/modules/phrases/domain/normalization.py` (`display_form`, `comparison_form`) with `tests/unit/phrases/test_normalization.py`: tables for `"Buy\tmilk"` -> `"Buy milk"`, ZWJ emoji sequence and Persian ZWNJ kept, U+200B/2060/FEFF stripped, idempotence of both forms, casefold then NFC again, length in code points after trim.
- [x] 1.2 RED then GREEN `modules/similarity/domain/cosine.py`, `vector.py`, `policy.py` (`score = round(min(1,max(0,1-d)),4)`, `Decimal` comparison, `max_distance()` = `1 - t + 1e-4`, `2.0` at t=0, `u = 1e-4` constant) with `tests/unit/similarity/test_policy.py`: table `(raw, score, is_duplicate, in_matches)` for 0.79996 -> 0.8000 true, 0.79994 -> 0.7999 false, -0.3 -> 0.0, 1.0000000002 -> 1.0, t=0.80005 vs 0.79996/0.80006.
- [x] 1.3 GREEN `modules/similarity/domain/errors.py` and `phrases/domain/errors.py` (`EmptyText`, `TooLong`, `EmbeddingUnavailable`, `EmbeddingTimeout`). **Named per design.md's error registry**: `EmptyPhraseText`/`PhraseTooLong` (not the literal `EmptyText`/`TooLong` shorthand), since design.md is authoritative for internals — see apply-progress.md.
- Verify: `cd services/api && pytest tests/unit -q` (whole unit suite < ~2 s); `lint-imports` (domain imports no fastapi/sqlalchemy/torch).

## Unit 2: Ports, unit of work, fake embedder, in-memory repository (~340)

Commit: `feat(domain): ports, unit of work, fake embedder and in-memory repository`. Rollback: revert (no consumers yet). If over 400, split the `find_matches` keyset out of the contract suite.
Covers: Embedding via a swappable port (Domain isolation, Swap without domain change), Keyset ordering: Tie scores across a page boundary, Displayed ties ordered by raw distance, Vector drift does not repeat or skip (in-memory), All matches reachable, Exact page boundary, One over page boundary (contract suite), Complete ordered match set: Custom page size.
- [x] 2.1 `modules/similarity/contracts.py` (`EmbeddingProvider`, `Vector`, `SimilarityPolicy`, errors) and `modules/phrases/contracts.py` (`PhraseRepository` with `find_nearest`, `find_nearest_exact`, `insert`(`add`), `list`(`list_recent`); `UnitOfWork`; `Phrase`, `NewPhrase`, `DuplicateTextConflict`) — done. `find_matches`, `Match`, `Page`, `MatchCursor` were deferred to Unit 2d for the review-budget split and are now **restored** — see Unit 2d below.
- [x] 2.2 RED then GREEN `similarity/adapters/fake.py` (`FakeEmbedder`, `call_count`, same vector object for tied texts) and `failing.py` (one-shot and permanent failure modes) — done.
- [x] 2.3 RED then GREEN `phrases/adapters/in_memory_repository.py` and an in-memory `UnitOfWork`; shared suite `tests/contract_suite/repository_contract.py` parametrized by adapter (only in-memory registered now; pgvector registered in 5a/5b) — `find_nearest`/`find_nearest_exact` scenarios done (empty -> `None`, below-threshold neighbour, distance tie -> lowest id). `find_matches` and its keyset scenarios were deferred to Unit 2d and are now **restored** — see Unit 2d below.
- Verify: `pytest tests/unit tests/contract_suite -q`; `lint-imports` — passing for the scope actually shipped in this PR.

### Unit 2d: `find_matches` keyset (deferred from Unit 2, review-budget split) — DONE

Unit 2's actual diff (contracts + 2 adapters + full contract-suite machinery, all new files) measured ~730 lines even after applying this unit's own "split `find_matches` out" escape hatch down to `find_nearest`/`find_nearest_exact` only — the ~340 estimate undersold the ports+adapter+contract-suite scope similarly to (worse than) Unit 1's. Restored here, needed before Unit 3 (`ValidatePhrase`/`ListMatches`/`SavePhrase`'s rejection path all call `find_matches`):
- [x] 2d.1 Add back `Match`, `Page`, `MatchCursor` to `modules/phrases/contracts.py` and `find_matches` to the `PhraseRepository` Protocol — restored near-verbatim from apply-progress.md's Unit 2 section, plus a resolved scoping decision for `MatchCursor` (design.md's code sample types the parameter but not the class body): it carries only `distance`/`id` (the two fields the keyset math needs), not the wire cursor's `t`/`th` binding fields, which Unit 2c/3 validate before ever constructing this type — see apply-progress.md and the type's own docstring.
- [x] 2d.2 RED then GREEN: restored `find_matches` on `InMemoryPhraseRepository` (`(floor(d/1e-6), id)` keyset, `max_distance` filter, `limit+1` has-more probe).
- [x] 2d.3 RED then GREEN: the deferred contract-suite scenarios — bit-identical tie fixture / ties across a page boundary, displayed-tie fixture (0.90001 vs 0.90004), 500-match paging, perturbed-vector paging on a fixture away from grid edges.
- Verify: `pytest tests/unit tests/contract_suite -q` (58 passed); `lint-imports` (5 kept, 0 broken).
- Branch: `feat/pv-02d-find-matches`, based on `feat/pv-02-ports-inmemory` (stacked-to-main; retarget to `main` once PR #5 merges — see apply-progress.md). Actual diff: 328 insertions / 23 deletions, 5 files — well under the 400-line budget.

## Unit 2b: Caching embedding provider (~180)

Commit: `perf(similarity): caching embedding provider decorator`. Rollback: revert, or `EMBEDDING_CACHE_SIZE=0`; every test stays green (kill-switch test). Independently revertible.
Covers: Embedding reuse: Normalization variants share an entry, Evicted entry (unit level); Cache is a pure optimization: Cold equals warm, Model identifier in key, Bounded size, Failures not cached.
- [x] 2b.1 RED then GREEN `similarity/adapters/caching.py` (`CachingEmbeddingProvider`, `OrderedDict` LRU keyed `(model_id, comparison_form)`, `threading.Lock` only around dict ops, `CacheStats(hits, misses, evictions, size, capacity)`, DEBUG log on miss, INFO log on first eviction) with `tests/unit/similarity/test_caching.py`: call counting (same text 1, different 2, different `model_id` 2), LRU vs FIFO (size=2: A,B, touch A, insert C keeps A), failures not cached (one-shot `FailingEmbedder` called twice), bit-identical after clear, thread-safety stress (`size <= capacity`), `size=0` bypass.
- [x] 2b.2 Estimate check: `tracemalloc` over a 512-entry fill; note the measured bytes/entry in the PR body (design estimate ~2 KB, unmeasured). **Measured: ~12.7 KB/entry** (~6.2x the design estimate) — see apply-progress.md for the methodology and why (`Vector = Sequence[float]`, i.e. plain Python `list[float]` objects as currently typed, cost far more per element than the design's assumed packed float32 buffer).
- Verify: `pytest tests/unit/similarity/test_caching.py -q`.

## Unit 2c: Opaque cursor codec (~150)

Commit: `feat(domain): opaque cursor codec with strict validation`. Rollback: revert (no callers).
Covers: Page consistency: Malformed cursor, Cursor bound to the query text, Cursor bound to the threshold (codec-level fields `v,t,d,i,th`); api-contract POST /phrases/matches: Malformed cursor, Cursor field violations (codec side).
- [x] 2c.1 RED then GREEN `modules/phrases/domain/cursor.py` (encode/decode base64url JSON `{v,t,d,i,th}`, size cap) with `tests/unit/phrases/test_cursor.py`, one table row per rule: bad base64url, non-object, `NaN`/`Infinity`, wrong `v`, non-string `t`, `d` negative/>2/NaN/string, `i` 0/negative/>int64/`true`, `th` <0/>1/non-finite, missing/extra key, oversized. All raise `InvalidCursor`.
- Verify: `pytest tests/unit/phrases/test_cursor.py -q` — 22 passed. Full backend suite `pytest tests/unit tests/contract_suite -q` — 80 passed; `lint-imports` 5 kept, 0 broken.
- Branch: `feat/pv-02c-cursor-codec`, based on `feat/pv-02-ports-inmemory` at `b669eea` (stacked-to-main, authoring-ahead; retarget to `main` once PR #7 merges — see apply-progress.md). PR #8, base `feat/pv-02-ports-inmemory`. Actual diff: 354 insertions / 0 deletions, 2 files — well under the 400-line budget.

## Unit 3: Validate, list-matches, save use cases (~350) — SPLIT into 3a-3d

First shipped as one PR (`feat/pv-03-use-cases`, 1083 lines) and flagged by `sdd-verify` as a
review-budget CRITICAL: 2.7x the 400-line cap, with the Notes line's own named seam ("move 409
payload build to unit 7") measured to save only ~50-70 lines — not enough to close the gap alone.
Per this file's own Review Workload Forecast rule ("If a unit exceeds 400, split at the seam named
in its Notes instead of asking for `size:exception`") and the change's `ask-on-risk` delivery
strategy, the unit was re-split into four stacked sub-unit PRs along its natural dependency seams
(`_shared.py`'s consumers) instead of shipping a `size:exception`. Original commit `55214c0` /
fix-pass commit `c1e7b2f` on the now-superseded `feat/pv-03-use-cases` branch (PR #11, closed)
contain the pre-split history; task assignment below is unchanged, only the delivery unit boundary
moved. See apply-progress.md's Unit 3 "Fix pass" section for the full measurement and the four new
branches/PRs/commit SHAs.

Covers (unchanged, now spread across 3a-3d as noted per task): Validation result shape x4 (Empty store, Best below threshold, most_similar equals first match, Statelessness), Complete ordered match set: Threshold zero, Page consistency: Phrase saved between pages, Exact duplicates: Confirmable, Model failure and timeout x3 (use-case level), Embedding reuse: Validate then pages, Validate then save, Blind save; Server-side re-validation: Similarity re-run despite warm cache, Query count on save, Save does not use the approximate read, Save catches a duplicate the approximate index would miss (spy level), Save without validating (unique/duplicate), Forged client score, Stale validation; Explicit flag: Duplicate confirmed, Flag on a non-duplicate, Exact duplicate confirmable, Cancel saves nothing (backend: no call); 409 payload: Payload completeness, Large match set on 409; Failures never save: Model down on save, Model down with confirmation, Timeout on save; Concurrency: Unique violation maps to 409 never 500, Persistent violation still yields 409, Confirmed save cannot violate the index; Persistence: Unique phrase metadata, Below-threshold neighbor is recorded, Confirmed duplicate metadata; Threshold changed via env (policy injected).

### Unit 3a: Validate use case (`feat/pv-03a-validate`, base `main`, ~430 lines)
- [x] 3.1 RED then GREEN `phrases/application/validate_phrase.py` + `_shared.py` (view types + tail rule, shared by 3a/3c): normalizes once, rejects empty/too-long before any `embed()`, opens `REPEATABLE_READ` read-only UoW, runs `find_nearest` then `find_matches`, reconciliation rule (`matches[0]` wins), tail rule, `has_more`; tests in `tests/unit/phrases/test_validate_phrase.py` (spy repo: worse `find_nearest` neighbour loses to `matches[0]`; property loop `most_similar == matches[0]` over a random corpus; threshold-injection test added in the fix pass — see apply-progress.md).
- Verify: `pytest tests/unit tests/contract_suite -q`; `lint-imports`.

### Unit 3b: List-matches use case (`feat/pv-03b-list-matches`, base `feat/pv-03a-validate`, ~140 lines)
- [x] 3.2 RED then GREEN `phrases/application/list_matches.py`: cursor decode before embedding (`FakeEmbedder.call_count == 0` on any invalid cursor, wrong `t`, wrong `th`), zero extra embeddings across pages 2..n, `find_matches` on every page; tests in `tests/unit/phrases/test_list_matches.py`.
- Verify: `pytest tests/unit tests/contract_suite -q`; `lint-imports`.

### Unit 3c: Save use case (`feat/pv-03c-save`, base `feat/pv-03b-list-matches`, ~390 lines)
- [x] 3.3 RED then GREEN `phrases/application/save_phrase.py` (+ `_uow_spies.py`'s `CountingRepo`/`ConflictRepo`, extending 3a's file): `READ_COMMITTED` UoW, advisory lock through the UoW, `find_nearest_exact` exactly once and `find_nearest` zero times (delivered as a call-counter proof, not a raising spy — see apply-progress.md deviation note), `unique` records below-threshold neighbour as `NewPhrase(score, most_similar_id)`, empty store `(None, None)`, 409 builds the full validate-shaped payload (`find_matches` page 1), `DuplicateTextConflict` -> one retry in a FRESH UoW -> 409 (always-raising repo still 409), rollback on exception, no persistence on embedder failure/timeout; tests in `tests/unit/phrases/test_save_phrase.py`.
- Verify: `pytest tests/unit tests/contract_suite -q`; `lint-imports`.

### Unit 3d: Cache-interplay tests (`feat/pv-03d-cache-interplay`, base `feat/pv-03c-save`, ~125 lines)
- [x] 3.4 Cache interplay tests `tests/unit/phrases/test_cache_interplay.py` (needs all three use cases from 3a-3c): validate then save shares one provider (`call_count == 1`), 3 pages keep `call_count == 1`, repo counters prove live queries on every request even on cache hit, response byte-identical for empty/warm/disabled cache.
- Verify: `pytest tests/unit tests/contract_suite -q`; `lint-imports` (use cases import no adapters — the unit's original Verify line, now satisfied cumulatively by 3a-3d).

## Unit 4: Schema, Alembic raw-SQL migrations, compose db/migrate, minimal API Dockerfile stage (~340)

Commit: `feat(db): phrases schema, alembic raw-sql migrations, compose db/migrate and minimal api dockerfile`. Rollback boundary of the schema: `alembic downgrade base` then revert; `docker compose down -v`.
Covers: Persistence: No plain unique index, Metadata is immutable history (no update path/columns), Embedding dimension mismatch fails fast (typmod reader; boot wiring in 8); DB uniqueness x4 (second unique rejected, confirmed accepted, different text unaffected, Migration lifecycle); Migrations: Upgrade from empty database, Downgrade to base; Persistence CHECKs (`phrases_metadata_paired`, `phrases_confirmed_has_neighbor`, `ON DELETE RESTRICT`).
- [ ] 4.0 VERIFY (unverified facts, before writing 0001): run `docker pull pgvector/pgvector:pg16` then `docker images pgvector/pgvector` (tag exists, Debian, size) and, once `db` is up, `docker compose exec db psql -U $POSTGRES_USER -d $POSTGRES_DB -c "SELECT extversion FROM pg_extension WHERE extname='vector'"` (HNSW needs >= 0.5.0). Record tag, size and version in the PR body and, later, ADR-008. If the tag or version fails, fall back to `postgres:16-alpine` + `make install` builder stage (design fallback) and update the Docker Compose table note.
- [ ] 4.1 `docker-compose.yml` (root): `db` (healthcheck `pg_isready`, volume `pgdata`, init creating `phrases_test` via `infra/db/init.sql`), `migrate` (builds `services/api`, `alembic upgrade head`, `restart: "no"`, depends on `db: service_healthy`); `services/api/Dockerfile` with a minimal `migrate` stage (no torch, no model).
- [ ] 4.2 RED then GREEN `services/api/migrations/env.py`, `alembic.ini`, `versions/0001_create_phrases.py` (SQL from design, HNSW `vector_cosine_ops`, `phrases_created_at_id_idx`, `phrases_unique_normalized_text_uidx`; fail fast if HNSW unsupported; working `downgrade`).
- [ ] 4.3 Integration tests `tests/integration/test_schema.py` (marker `integration`, `DATABASE_URL` -> `phrases_test`): raw `INSERT`s: second `unique` same `normalized_text` -> `23505` on `phrases_unique_normalized_text_uidx`; `duplicate_confirmed` same text accepted; different text accepted; paired-metadata and confirmed-needs-neighbour CHECKs reject bad rows; `upgrade head` from empty, `downgrade base` leaves no table/extension.
- Verify: `docker compose up -d db migrate && docker compose ps` (migrate exit 0); `make test` integration subset: `cd services/api && pytest -m integration tests/integration/test_schema.py -q`.

## Unit 5a: Exact keyset `find_matches` (~330)

Commit: `feat(db): exact keyset find_matches`. Rollback: revert (adapter unused by transport until 6b/7). Seam: 5a is pure query work on the 0001 schema.
Covers: Keyset match pagination: No OFFSET, Exact scan; Complete ordered match set: All matches reachable, Exact page boundary, One over page boundary, Tie scores across a page boundary, Displayed ties ordered by raw distance, Paging beyond the former approximate-index window (500 matches), Threshold zero, Custom page size; Page consistency: Vector drift does not repeat or skip; Cosine: Rounding consistency, Oracle agreement (1e-5, pgvector side), Threshold decision boundaries (0.79996/0.79994 tail rule); Threshold zero admits everything (`2.0` bound).
- [ ] 5a.1 RED then GREEN `phrases/adapters/pgvector_repository.py::find_matches`: `set_config('enable_indexscan','off',true)` at start of the method, `WHERE embedding <=> :q <= :max_distance`, `ORDER BY bucket, id`, `LIMIT limit+1`, keyset predicate on `(floor(d/1e-6), id)`, application filter with the tail rule (stop at first failing row, `has_more=false`).
- [ ] 5a.2 Register the pgvector adapter in `tests/contract_suite/repository_contract.py` (same suite as in-memory) plus `tests/integration/test_find_matches.py`: `EXPLAIN` shows no HNSW index scan and no `OFFSET`; 500 matches paged at 50 -> 10 pages, 500 distinct ids; `enable_indexscan` is `SET LOCAL` (next statement on the pooled connection sees default); perturbed-vector (1 ulp) paging; boundary test 0.79996 in / 0.79994 out and `has_more=false`; oracle equivalence vs `cosine.py` at 1e-5.
- [ ] 5a.3 VERIFY (estimate): `EXPLAIN (ANALYZE)` timings for `find_matches` on 500 and 10^4 rows; write results to `docs/evidence/exact-scan-timings.md` (input to ADR-008).
- Verify: `pytest -m integration tests/integration/test_find_matches.py tests/contract_suite -q`.

## Unit 5b: `find_nearest`, `find_nearest_exact`, unit of work, advisory lock (~350)

Commit: `feat(db): pgvector find_nearest, find_nearest_exact, unit of work and advisory lock`. Rollback: revert (use cases fall back to the in-memory adapter in tests; no transport yet). Seam if over budget: move the barrier snapshot test to its own follow-up commit inside the same unit.
Covers: Save does not use the approximate read, Save catches a duplicate the approximate index would miss, Exact scan on the save path (integration); Concurrency: Concurrent similar saves, Concurrent confirmed saves, Concurrent identical saves without confirmation, Lock wait is bounded, Lock released on failure, Unique violation maps to 409 never 500 (adapter maps only that constraint's `23505` to `DuplicateTextConflict`), Persistent violation still yields 409; Failures never save: Database failure rolls back; Validation result shape: Statelessness; Persistence: Confirmed duplicate metadata.
- [ ] 5b.0 VERIFY (unverified planner assumption): assertion `EXPLAIN (ANALYZE, BUFFERS)` with `SET enable_seqscan = off` on a 1,000-row corpus (> `ef_search` 200) shows `Index Scan using phrases_embedding_hnsw_idx` and no full `Sort` for `ORDER BY embedding <=> :q, id LIMIT 1`. If not, adopt the documented fallback (k-NN subquery re-sorted outside) and note it in the commit body. Also run `EXPLAIN` on 100/1,000/10,000 rows to record the sequential-scan estimate.
- [ ] 5b.1 RED then GREEN `find_nearest` (HNSW top-1, `hnsw.ef_search = HNSW_EF_SEARCH`, `SET LOCAL`) and `find_nearest_exact` (own `enable_indexscan = off`, same `(distance, id)` order); register both in the contract suite.
- [ ] 5b.2 RED then GREEN pgvector `UnitOfWork` (`REPEATABLE READ READ ONLY` and `READ COMMITTED`, `commit`, `rollback`), `pg_advisory_xact_lock` helper in `platform/db.py`, `SET LOCAL lock_timeout` from `LOCK_TIMEOUT_MS`, `INSERT` mapping `23505` on `phrases_unique_normalized_text_uidx` to `DuplicateTextConflict`.
- [ ] 5b.3 Integration tests `tests/integration/test_nearest_and_uow.py`: non-vacuous recall guard (1,000 rows > `ef_search`; HNSW arm forced with `enable_seqscan = off`, exact arm with `enable_indexscan = off`, hundreds of seeded queries agree); `EXPLAIN` of `find_nearest_exact` shows no HNSW even with `enable_seqscan = off` set first; statement log proves a full save (201 and 409) issues no `find_nearest`; recall-miss fixture (tiny `ef_search`, HNSW misses stored near-identical phrase, exact returns it -> 409, control asserts HNSW alone is wrong); barrier snapshot test (two `threading.Event`, `after_statement` hook, no sleeps) with `READ COMMITTED` control showing divergence; advisory-lock serialization with two real connections (real commits + truncate fixture); `lock_timeout` yields error with nothing persisted; lock released after failure; oracle at 1e-5.
- Verify: `pytest -m integration tests/integration/test_nearest_and_uow.py -q`.

## Unit 6: Settings, error envelope, framework-error handlers (~300)

Commit: `feat(api): settings, error envelope and framework-error handlers`. Rollback: revert (no business endpoint yet).
Covers: Threshold configuration validation x3 (Out of range, Non-numeric, Boundary values accepted), Threshold changed via env; Maximum length: Configurable limit, Invalid limit config, Raw input cap before normalization; api-contract: Response envelopes: Unknown route, Wrong method, Unhandled exception; Error codes: Empty text, Too long, Malformed JSON, Raw length cap, Oversized body, Provider failure and Provider timeout (registry mapping 503/504 per spec); CORS x5 (Allowed origin, Disallowed origin, Preflight allowed, Preflight disallowed, Errors carry CORS headers); Empty text rejection: Missing or non-string field; id string serialization; strict `PageLimit`.
- [ ] 6.1 RED then GREEN `platform/settings.py` (pydantic-settings, all vars of the design table with validation ranges; runtime enum for `EMBEDDING_PROVIDER` has ONE value; separate test settings class allows `fake`) + `tests/unit/platform/test_settings.py` (fail-fast on out-of-range/non-numeric, boundary 0 and 1 accepted).
- [ ] 6.2 RED then GREEN `platform/errors.py` (`DomainError` -> HTTP registry from design, envelope `{"error": {code, message, details}}`), `main.py` factory (CORS methods `GET, POST, OPTIONS`, header `Content-Type`, `allow_credentials=False`), body-size guard (`MAX_REQUEST_BYTES` -> 413 `PAYLOAD_TOO_LARGE` before parse), catch-all as an INNER middleware inside `CORSMiddleware`, `phrases/api/schemas.py` bases (id string serializer, shared strict `PageLimit`, raw length cap 4x).
- [ ] 6.3 Contract tests `tests/contract/test_framework_errors.py`: `GET /nope` 404, `DELETE /phrases` 405, forced exception 500 without stack trace, malformed JSON 422, 413, and a forced 500 for an allowed `Origin` still carrying `Access-Control-Allow-Origin` (settles the Starlette-handler-order "from memory" item; if it fails, adjust middleware order before merging).
- Verify: `pytest -m "unit or contract" tests/unit/platform tests/contract -q`.

## Unit 6b: Validate endpoint and `/health` readiness (~250)

Commit: `feat(api): validate endpoint and /health readiness`. Rollback: revert (removes the first business endpoint).
Covers: POST /phrases/validate x8 (Duplicate found, Empty store, Page 1 carries the verdict, Limit bounds, Strict integer limit, Default limit, Cursor not accepted, Nothing persisted); GET /health x3 (Ready, Model not loaded, Database down); Caching invisible: Cold and warm responses identical; Response envelopes: Success envelope; Database unreachable outside health (validate side); Error codes: Provider failure/timeout on the endpoint.
- [ ] 6b.1 RED then GREEN `phrases/api/router.py` (`POST /phrases/validate`; a `cursor` key is ignored), `phrases/container.py`, `similarity/container.py` (fake provider wiring for tests), `platform/health.py` (`{status, database, model, dimensions, embedding_model, embedding_cache}`; `model` = `"ready"|"unavailable"`, `embedding_model` = name; 503 `NOT_READY` with per-component `details`; zero embeddings issued).
- [ ] 6b.2 Contract tests `tests/contract/test_validate_health.py` with `FakeEmbedder` and the in-memory repo: verdict payload, `limit` `"10"`/`true`/`10.5` -> 422 `invalid_type`, `/health` keys, patched readiness -> 503 details, `call_count == 0`, cold vs warm byte-identical.
- Verify: `pytest tests/contract/test_validate_health.py -q`.

## Unit 7: Save, list and match paging endpoints (~380)

Commit: `feat(api): save, list and match paging endpoints`. Rollback: revert (validate/health remain). Seam if over 400: move GET /phrases + OpenAPI snapshot to a follow-up unit 7b.
Covers: POST /phrases/matches x8; POST /phrases x5 (Created unique, Conflict shape, Created confirmed, Strict boolean flag, Text stored normalized); GET /phrases x3 (List shape, Empty, Hard cap); phrase-management List phrases x3 (Newest first, Empty list, Metadata exposed) and Persistence: Unique/Confirmed metadata (over HTTP); Explicit flag: Non-boolean flag; 409 payload: Payload completeness, Large match set on 409 (120-match fixture, `next_cursor` accepted by `/phrases/matches`); Failures never save (HTTP: 503/504, DB down -> 500 `INTERNAL_ERROR`); Concurrency: Unique violation maps to 409 never 500 (HTTP); OpenAPI documentation x4 (Endpoints documented, Error responses documented, Pagination documented, Every code documented).
- [ ] 7.1 RED then GREEN `phrases/application/list_phrases.py` and routes `POST /phrases` (`StrictBool` `confirm_duplicate`, 201 body, 409 `DUPLICATE_CONFIRMATION_REQUIRED` with validate-shaped `details`), `POST /phrases/matches` (`cursor` required, `400 INVALID_CURSOR`), `GET /phrases` (no params, cap `PHRASES_LIST_LIMIT`, newest first).
- [ ] 7.2 Contract tests `tests/contract/test_phrases_endpoints.py` and `tests/contract/test_openapi.py`: every error code in OpenAPI, ids typed `string` documented opaque, `limit` optional and bounded on both endpoints, snapshot `docs/openapi.json` (regenerate via `make types`).
- [ ] 7.3 Integration test `tests/integration/test_endpoints_pgvector.py`: same happy paths against real Postgres (one 201, one 409, one concurrent-identical-save pair -> exactly one 201 and one 409).
- Verify: `pytest tests/contract tests/integration/test_endpoints_pgvector.py -q`.

## Unit 8: sentence-transformers adapter, bounded provider, cache wiring, image bake (~380)

Commit: `feat(embeddings): sentence-transformers adapter, bounded provider, cache wiring and image bake`. Rollback: revert, restore the migrate-only Dockerfile stage; tests keep using `FakeEmbedder`. Seam if over budget: split the Dockerfile bake into its own unit 8b.
Covers: Model failure and timeout: Provider raises, Provider times out, Recovery (with `BoundedEmbeddingProvider`); Embedding via a swappable port: Swap without domain change (adapter registered in `container.py` only); Embedding dimension mismatch fails fast (boot typmod check); Embedding reuse: Evicted entry, Bounded size (wired, `/health` stats); Timeout on save (real bound).
- [ ] 8.0 VERIFY the Hub commit SHA (unverified): `python -c "from huggingface_hub import model_info; print(model_info('sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2').sha)"`; set `EMBEDDING_MODEL_REVISION` in `.env.example` and the Dockerfile ARG; the build must fail on a non-40-hex value.
- [ ] 8.1 RED then GREEN `similarity/adapters/bounded.py` (`ThreadPoolExecutor` + `BoundedSemaphore`, semaphore released by the future done-callback) with `tests/unit/similarity/test_bounded.py` (controllable slow fake on `threading.Event`, no sleeps: timeout -> `EmbeddingTimeout`; slot held -> next call fails fast; release -> later call succeeds; inner call count shows no extra queue; timed-out result never cached).
- [ ] 8.2 RED then GREEN `similarity/adapters/sentence_transformers.py` (marker `slow` for the real-model test; unit tests use a stubbed model object), `similarity/container.py` order: ST -> bounded -> caching (outermost; skipped if `EMBEDDING_CACHE_SIZE=0`), lifespan warmup, dimension coherence check (typmod vs provider vs `EMBEDDING_DIMENSIONS`, boot aborts on mismatch), `model_id = EMBEDDING_MODEL@EMBEDDING_MODEL_REVISION`.
- [ ] 8.3 Extend `services/api/Dockerfile`: builder installs CPU-only torch wheel and runs `snapshot_download(repo_id, revision)` into `/opt/models`; runtime copies weights, sets `HF_HUB_OFFLINE=1`, `TRANSFORMERS_OFFLINE=1`, `SENTENCE_TRANSFORMERS_HOME=/opt/models`.
- [ ] 8.4 VERIFY (unmeasured): `docker build -t todo-ia-api services/api && docker images todo-ia-api` (image size); time `embed()` p50/p95 and a warm-vs-cold `POST /phrases/validate` + `POST /phrases` pair with the real model (`pytest -m slow`); write results to `docs/evidence/runtime-measurements.md` (baselines for ADR-003 and ADR-011; check `EMBEDDING_CACHE_SIZE` default 512 against them).
- Verify: `make test-unit`; `docker build` succeeds offline second run (`docker build --network none` of the runtime stage using cached layers), `pytest -m slow -q` loads 384-dim deterministic embeddings.

## Unit 9: ES/EN calibration fixture and integration evidence (~150)

Commit: `test(calibration): es/en fixture and integration evidence`. Rollback: revert (manual step only, not in CI).
Covers: Cross-language calibration x3 (Paraphrase pairs flagged, Unrelated pairs pass, Default changes are recorded); Exact duplicates: Case and spacing variants (real model).
- [ ] 9.1 `services/api/tests/fixtures/calibration.yaml` (categories `duplicate`, `distinct`, `expected_weakness`) and `tests/slow/test_calibration.py` (`slow`): hard assert on `duplicate`/`distinct`, report-only on `expected_weakness`.
- [ ] 9.2 `make evidence` writes the score table to `docs/evidence/calibration.md` (the brief's Hugging Face evidence deliverable). VERIFY (unmeasured): score cased pairs with and without casefolding and record both margins plus the cased-variant cosine (design estimate ~0.98); decision rule: if the margin around 0.80 is poor, change the `SIMILARITY_THRESHOLD` DEFAULT (and `.env.example`, spec, ADR-003 note) as a recorded spec change, never bend the fixture.
- Verify: `make evidence` then `git diff --stat docs/evidence/calibration.md`.

## Unit 10: Web scaffold, API client, generated types (~300)

Commit: `feat(web): scaffold, api client and generated types`. Rollback: revert (web track only).
Covers: Spanish copy table: English code, Spanish UI (identifier/comment language); Client-side input checks: Server-enforced limit (client passes server errors through); Error handling: Network failure (client normalization).
- [ ] 10.1 Scaffold Next.js + TypeScript in `apps/web/` (`app/layout.tsx`, `app/page.tsx` placeholder, `next.config.mjs`, `tsconfig.json`, `Dockerfile`, build args `NEXT_PUBLIC_API_URL`, `NEXT_PUBLIC_PHRASE_MAX_LENGTH`).
- [ ] 10.2 RED then GREEN `apps/web/src/lib/api/client.ts` (typed; `fetch` wrapper; envelope-to-`ApiError{code,status,details}`; network failures to a `NETWORK_ERROR` code) with `client.test.ts` using a hand-rolled fake fetch (no MSW); `apps/web/src/types/api.ts` generated from `docs/openapi.json` by `openapi-typescript`; `make types` drift guard (fail on diff).
- Verify: `cd apps/web && npx vitest run && npx tsc --noEmit && npm run build`; `make types && git diff --exit-code`.

## Unit 11: Validation state machine and phrase form (~360)

Commit: `feat(web): validation state machine and phrase form`. Rollback: revert (web track only).
Covers: Explicit staged state machine x3 (Validate unique, Validate duplicate, Invalid transition ignored); Staged progress narration x4 (Save directly unique, Save after validating, Save directly duplicate, Live region); Reset on text edit x3; Controls disabled in flight x2; Client-side input checks: Empty text, Over length, Counter counts code points; Error handling: Retry.
- [ ] 11.1 RED then GREEN `apps/web/src/features/phrases/machine.ts` (reducer, table-driven test over every state x event including `EDIT_TEXT` from every state; invalid transitions ignored; states `idle, validating, ok, duplicate, revalidating, saving, error`; no state after the 201).
- [ ] 11.2 RED then GREEN `PhraseForm.tsx` + `copy.es.ts` seeded with the form and progress keys ("Validando...", "Revalidando...", "Guardando...", "Frase guardada."), live region `role="status" aria-live="polite"`, code-point counter reading `NEXT_PUBLIC_PHRASE_MAX_LENGTH`; `PhraseForm.test.tsx` with a deferred-promise fake client asserting label order per scenario (blind save: Validando then Revalidando then NO label after 201; from `ok`: only Revalidando; confirm: only Guardando; 409 during `revalidating` never renders Guardando).
- Verify: `cd apps/web && npx vitest run`.

## Unit 12: Duplicate alert with infinite-scroll matches (~310)

Commit: `feat(web): duplicate alert with infinite-scroll matches`. Rollback: revert (web track only).
Covers: Duplicate alert x7 (Alert content, Percentage never overstates, Confirm, Cancel, 409 during save, 409 while confirming (defensive)); Infinite scroll x7 (Load next page on scroll, Invalid cursor restarts validation, Reach the end, No concurrent page requests, Page load failure, Deduplicate on overlap, Single page); Reset on text edit: Edit during duplicate; Cancel saves nothing.
- [ ] 12.1 RED then GREEN `percent.ts` (floored: 0.9312 -> 93, 0.9950 -> 99, 0.9999 -> 99, 0.29 -> 29, 1.0 -> 100) with unit test.
- [ ] 12.2 RED then GREEN `DuplicateAlert.tsx` and `useMatchesInfiniteScroll.ts` (IntersectionObserver sentinel, in-flight guard, dedupe by id, stop on `has_more=false`, `INVALID_CURSOR` discards matches and re-runs validation) with component tests on the typed fake client.
- Verify: `cd apps/web && npx vitest run`.

## Unit 13: Saved list, status badges, Spanish copy module (~290)

Commit: `feat(web): saved list, status badges and the spanish copy module`. Rollback: revert (web track only).
Covers: Saved phrase list x6 (Badge unique, Badge duplicate confirmed, Empty list, Refresh after save, Refresh fails after a successful save, List load failure); Spanish copy table x4 (Single source of copy, Copy values, Success message, English code Spanish UI); Error handling x4 (Model unavailable, Timeout, Network failure, Unknown code).
- [ ] 13.1 RED then GREEN complete `copy.es.ts` (verbatim values from the phrase-ui copy table; snapshot test) and `errorCopy.ts` exhaustive over the generated `ErrorCode` union incl. `INVALID_CURSOR` (test walks the union; unknown code falls back to generic copy).
- [ ] 13.2 RED then GREEN `app/page.tsx` Server Component list first paint via `API_INTERNAL_URL` with `dynamic = "force-dynamic"`/`no-store`, `PhraseList.tsx` with status badges, browser-side refetch after a 201, post-201 refresh failure leaves machine `idle`, keeps "Frase guardada." and shows the list error with Reintentar (never the `error` state).
- Verify: `cd apps/web && npx vitest run && npm run build`.

## Unit 14: Full compose wiring and healthchecks (~200)

Commit: `feat(infra): full compose wiring and healthchecks`. Rollback: revert (compose returns to db + migrate).
Covers: api-contract Env documented (compose consumes `.env`); Ready (container healthcheck uses `/health`); Model not loaded (unhealthy until warm).
- [ ] 14.1 Extend `docker-compose.yml`: `api` (build `services/api`, port 8000, `depends_on migrate: service_completed_successfully`, healthcheck `GET /health` with `start_period: 120s`, `interval: 10s`, `timeout: 5s`, `retries: 12`), `web` (build `apps/web`, build args, port 3000, `depends_on api: service_healthy`, healthcheck `GET /`), single `.env` via `env_file`, no `-f` needed.
- [ ] 14.2 VERIFY (unmeasured): `docker compose down -v && time docker compose up -d --build`, poll `docker compose ps` until `api` is `healthy`; record container-start -> healthy seconds and tune `start_period`/`retries` (120 s is an estimate). Add `infra/scripts/smoke.sh` (`curl` validate, save, list) and run it.
- Verify: `docker compose up -d --build && bash infra/scripts/smoke.sh && docker compose down -v`.

## Unit 15: README and architecture (~300)

Commit: `docs: readme and architecture`. Rollback: revert (docs only).
Covers: "Beyond the brief" decision log: README summary; api-contract Env documented (env var table); Concurrency: Limitation documented (residual semantic-duplicate race explained).
- [ ] 15.1 `README.md`: prerequisites, `cp .env.example .env`, `docker compose up`, URLs (web 3000, API 8000 `/docs`), running tests (`make test-unit`, `make test`, `make test-slow`, `make evidence`), env var table (every var in `.env.example`, defaults and ranges), summary of the five `beyond-brief` decisions linking `docs/decisions/*` and the technical ADRs in `docs/decisions/technical/`, link to `docs/evidence/calibration.md`.
- [ ] 15.2 `docs/architecture.md`: monorepo layout, hexagonal modules and import-linter contracts, the embedding microservice seam and its honest limit, three read shapes (`find_nearest`, `find_nearest_exact`, `find_matches`), keyset paging, cache invariant (never cache verdicts/pages), blind-save sequence, transactions/locking, residual risks.
- Verify: fresh-clone dry run of README steps on a clean checkout; `rg -n "TODO|TBD" README.md docs/architecture.md` returns nothing.

## Unit 16: Decision log (~340)

Commit: `docs: decision log`. Rollback: revert (docs only). Seam if over 400: technical ADRs 010-015 into unit 16b.
Covers: Decision log x4 (Five entries present, Technical ADRs are separate, README summary linkage, ONNX path documented); Concurrency: Limitation documented (ADR-006).
- [ ] 16.1 Exactly five beyond-brief ADRs in `docs/decisions/`: `ADR-001-full-match-list.md` ... `ADR-005-staged-progress.md` (front-matter `type: beyond-brief`, "brief asked / we decided / because"; ADR-003 includes the measured image size, p95 latency, casefold margins and the migration triggers plus the score-equivalence gate).
- [ ] 16.2 Technical ADRs in `docs/decisions/technical/`: ADR-006 to ADR-015 (`type: technical`); ADR-008 records the pgvector tag/version, exact-scan timings and image-size notes; ADR-011 keeps its beyond-brief framing and lives here.
- [ ] 16.3 VERIFY (unverified): fastembed support for the checkpoint, `python -c "from fastembed import TextEmbedding; print([m['model'] for m in TextEmbedding.list_supported_models()])"`; record result (fallback: manual `optimum` export) in ADR-003. Optional: `SHOW hnsw.iterative_scan;` on the pinned image for ADR-008's deferred scaling path.
- [ ] 16.4 Doc check test `tests/unit/test_decision_log.py`: `docs/decisions/*.md` (top level) count is exactly 5 and all `type: beyond-brief`; every file in `technical/` is `type: technical`; README links every ADR.
- Verify: `pytest tests/unit/test_decision_log.py -q`.

---

## Requirement-to-task traceability

Specs: SV = semantic-validation, PM = phrase-management, DC = duplicate-confirmation, AC = api-contract, UI = phrase-ui.

| Requirement | Owning unit(s) |
|-------------|----------------|
| SV Embedding via a swappable port | 0 (import-linter), 2, 8 |
| SV Cosine similarity | 1, 5a (oracle) |
| SV Threshold decision (inclusive) | 1, 5a |
| SV Threshold configuration validation | 6 |
| SV Validation result shape | 3, 6b |
| SV Complete ordered match set | 2, 5a, 3 |
| SV Page consistency and staleness | 2c, 2, 3, 5a |
| SV Exact duplicates are ordinary duplicates | 1, 3, 9 |
| SV Model failure and timeout | 3, 8 |
| SV Embedding reuse within a bounded window | 2b, 3, 8 |
| SV Embedding cache is a pure optimization | 2b, 3, 6b |
| SV Keyset match pagination | 5a, 5b |
| SV Cross-language calibration | 9 |
| DC Server-side re-validation on every save | 3, 5b, 7 |
| DC Explicit confirmation flag | 3, 7 |
| DC 409 payload | 3, 7 |
| DC Failures never save | 3, 5b, 7 |
| DC Concurrency control | 3, 5b, 7, 16 (limitation documented) |
| PM Text normalization | 1 |
| PM Empty text rejection | 1, 6 |
| PM Maximum length | 1, 6 |
| PM Phrase persistence with validation metadata | 3, 4, 7, 8 (dimension mismatch) |
| PM Database-level uniqueness | 4 |
| PM List phrases | 7 |
| PM Migrations | 4 |
| PM "Beyond the brief" decision log | 15, 16 |
| AC Response envelopes | 6, 6b |
| AC Error codes and status mapping | 6, 6b, 7 |
| AC POST /phrases/validate | 6b |
| AC POST /phrases/matches | 7 |
| AC POST /phrases | 7 |
| AC GET /phrases | 7 |
| AC GET /health | 6b, 14 |
| AC OpenAPI documentation | 7 |
| AC Caching is invisible to the contract | 6b, 7 |
| AC CORS and configuration | 0, 6, 14, 15 |
| UI Explicit staged state machine | 11 |
| UI Staged progress narration | 11 |
| UI Duplicate alert | 12 |
| UI Infinite scroll over matches | 12 |
| UI Reset on text edit | 11, 12 |
| UI Controls disabled in flight | 11 |
| UI Client-side input checks | 10, 11 |
| UI Error handling | 11 (Retry), 13 |
| UI Saved phrase list with status badge | 13 |
| UI Spanish copy table | 10, 13 |

Every requirement above has at least one owning unit. Scenario-level ownership is listed in each unit's "Covers" line.

### Scenario coverage flags (for the reviewer and for sdd-verify)

No scenario is left without an owner. Assignments the design does NOT state explicitly and that this plan decided (confirm or reassign):
- PM "Embedding dimension mismatch fails fast": typmod reader planned in unit 4, boot check wired in unit 8 (where the real provider dimension exists).
- DC/UI "Cancel saves nothing": backend = no call issued (unit 3/7 have no cancel endpoint); UI behaviour in unit 12.
- AC "OpenAPI documentation" and its four scenarios placed in unit 7 because every endpoint and error code exists only then; unit 6b snapshot would be premature.
- UI "Error handling" scenarios need the exhaustive `errorCopy`, so they land in unit 13 (unit 11 owns only the `error` state and Retry event).
- `copy.es.ts` is seeded in unit 11 and completed in unit 13 (design lists only 13); needed so unit 11 labels are not hard-coded.
- SV "Cross-language calibration" -> "Default changes are recorded" is satisfied by the decision rule in 9.2 plus ADR-003 in unit 16.
- PM "Beyond the brief" -> "ONNX path documented" and the fastembed verification are owned by 16.3.

### Unverified-fact verification tasks (each with its settling command)

| Fact | Task | Command |
|------|------|---------|
| pgvector image tag, Debian, size | 4.0 | `docker pull pgvector/pgvector:pg16 && docker images pgvector/pgvector` |
| pgvector extension version / HNSW >= 0.5.0 | 4.0 | `SELECT extversion FROM pg_extension WHERE extname='vector';` |
| Planner serves top-1 from HNSW; seq-scan estimate | 5b.0 | `EXPLAIN (ANALYZE, BUFFERS)` with `enable_seqscan = off` on 1,000 rows; repeat on 100/10,000 |
| Exact-scan cost ~10^4 rows | 5a.3 | `EXPLAIN (ANALYZE)` on 500 and 10^4 rows |
| Starlette handler order vs CORS | 6.3 | forced-500 contract test with an allowed `Origin` |
| Hub commit SHA | 8.0 | `huggingface_hub.model_info(...).sha` |
| API image size, p95 embed, cache saving | 8.4 | `docker images todo-ia-api`; `pytest -m slow` timings |
| Casefold margin and ~0.98 cased cosine | 9.2 | `make evidence` with and without casefolding |
| api healthcheck `start_period` 120 s | 14.2 | time container start -> healthy |
| fastembed support | 16.3 | `TextEmbedding.list_supported_models()` |
| `hnsw.iterative_scan` (deferred) | 16.3 (optional) | `SHOW hnsw.iterative_scan;` |
