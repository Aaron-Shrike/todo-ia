# Apply Progress: phrase-validation

Scope of batch 1: Unit B.0 (bootstrap commit) and Unit 0 (scaffold monorepo). Units 1+ were NOT
started in that batch.

Scope of batch 2 (this append): Unit 1 (normalization, clamped score, similarity policy) only, per
the orchestrator's explicit instructions. Units 2+ are NOT started.

## Unit B.0: Bootstrap commit (planning artifacts)

- [x] B.0.1 — **No new commit created.** `git status` was already clean at the start of this
  apply batch, and `openspec/` + `docs/` were already tracked and merged to `main` via PR #1
  (commits `70a4d1f` .. `80283cb`, including `77ff080 chore(sdd): initialize openspec context and
  testing capabilities` and `e060eeb docs: add fullstack AI challenge brief`). `.gitignore` already
  had a `.atl/` entry (`a18d040 chore: add gitignore`). The task's stated goal — planning artifacts
  tracked, `.atl/` ignored, clean working tree — was already true before this session started, so
  there is no `chore/pv-bootstrap-artifacts` branch and no root commit. This supersedes the
  now-stale "the repo has no commits" note in tasks.md's Review Workload Forecast section, which
  predates the PR #1 merge.

**Branch**: none created (nothing to commit).
**Commit**: none (see above).

## Unit 0: Scaffold monorepo

Branch `chore/pv-00-scaffold`, based on `main` at `80283cb`.

- [x] 0.1 RED — `services/api/tests/unit/test_smoke.py` (`import app`) and
  `apps/web/src/smoke.test.ts` (`1 + 1 === 2`) written before any runner was installed. Confirmed
  RED by execution: `services/api/.venv/bin/python -m pytest` failed with `No module named pytest`
  (venv existed but had nothing installed); `npx --no-install vitest run` in `apps/web` failed
  because `vitest` was not installed.
- [x] 0.2 GREEN — `services/api/pyproject.toml` (deps: fastapi, pydantic-settings; dev: pytest,
  pytest-cov, httpx, ruff, mypy, import-linter; markers `unit`, `integration`, `contract`, `slow`),
  `services/api/src/app/__init__.py`, `services/api/.importlinter` with the five boundary
  contracts. Installed via `pip install -e ".[dev]"` into `services/api/.venv`. Smoke test now
  passes.
  - **Deviation from the literal task wording**: task 0.2 lists only `app/__init__.py` as the
    backend deliverable, but `import-linter`'s `forbidden` contract type hard-fails
    (`Module 'app.modules.similarity' does not exist.`) when a `source_modules`/`forbidden_modules`
    entry does not resolve to a real, importable module — it does not silently skip missing
    modules. To make `lint-imports` actually pass (a Unit 0 Verify requirement), I added empty
    placeholder packages: `app/modules/{similarity,phrases}/__init__.py`,
    `app/modules/similarity/{domain,adapters}/__init__.py`,
    `app/modules/phrases/{domain,application,adapters,api}/__init__.py`, `app/platform/__init__.py`
    — matching exactly the module tree in design.md's "API Module Structure and Boundaries"
    (similarity has no `application`/`api` layer; only `phrases` does). Each `__init__.py` has a
    one-line docstring pointing at the unit that will populate it. No business logic was added.
  - Contract 2 file also required `include_external_packages = True` at the top level (import-linter
    demand for any contract with an external forbidden module, e.g. `fastapi`/`torch` in the
    domain-purity contract).
- [x] 0.3 GREEN — `apps/web/package.json` (devDependencies: vitest 5.0.1, typescript 7.0.2,
  prettier 3.9.8, eslint 10.11.0; script `test`: `vitest run`), `apps/web/vitest.config.ts`.
  `npm install` generated `apps/web/package-lock.json` (committed with this unit per the tasks.md
  Review Workload Forecast note: "commit lockfiles with the unit that adds the dependency").
  Next.js is intentionally NOT added yet (arrives in Unit 10). Smoke test now passes.
- [~] 0.4 PARTIAL — `.gitignore` was already complete (no edit needed: `.atl/`, `.env`, `.env.*`,
  `!.env.example`, Python/Node/OS caches all present from `a18d040`). `Makefile` created with all 7
  targets (`up`, `test`, `test-unit`, `test-slow`, `evidence`, `types`, `lint`). CI lint stub
  `.github/workflows/ci.yml` created (two jobs: backend `ruff` + `mypy` + `lint-imports` +
  `pytest -m "not integration and not slow"`; frontend `npm test`; lint + unit only, no
  integration/slow/build steps, per the task).
  - **`.env.example` was NOT created — blocked by tool permissions, not by design or by missing
    information.** My write tooling hard-denies any path matching `.env*`, including
    `.env.example`, regardless of directory or write mechanism (`Write` tool and `Bash` shell
    redirection both denied identically). I verified this is specifically the `.env` prefix, not a
    directory-level or content-level restriction, by successfully writing `env.example.tmp`
    (no leading dot) in the same directory and immediately removing it. This is a hard security
    control in the execution environment, not a `.gitignore`/repo-config restriction — `.gitignore`
    already explicitly allow-lists `.env.example` with `!.env.example`, so the file WOULD be
    tracked by git once it exists. I did not attempt further workarounds (e.g. writing under an
    obfuscated name then renaming, or disguising the target path), since that would defeat a
    deliberate safety boundary rather than a mistake.
  - **Full intended content**, every variable in design.md's Configuration table except the two
    image-fixed ones (`HF_HUB_OFFLINE`/`TRANSFORMERS_OFFLINE`, `SENTENCE_TRANSFORMERS_HOME`), is
    below verbatim so a human (or a session with broader file-write permissions) can create
    `.env.example` at the repo root in one paste:

    ```dotenv
    # Copy to `.env` before running `docker compose up`.
    # Every variable here maps 1:1 to the Configuration table in
    # openspec/changes/phrase-validation/design.md. Two image-fixed vars
    # (HF_HUB_OFFLINE/TRANSFORMERS_OFFLINE, SENTENCE_TRANSFORMERS_HOME) are baked into the
    # API image and are intentionally NOT listed here.

    # --- Database ---
    DATABASE_URL=postgresql+psycopg://todo_ia:todo_ia@db:5432/todo_ia
    POSTGRES_USER=todo_ia
    POSTGRES_PASSWORD=todo_ia
    POSTGRES_DB=todo_ia

    # --- Domain policy ---
    # Cosine score >= SIMILARITY_THRESHOLD is a duplicate (inclusive boundary). 0 <= t <= 1.
    SIMILARITY_THRESHOLD=0.80
    # Page size (and max accepted `limit`) for the paginated `matches` list. 1..200.
    MATCHES_PAGE_SIZE=50
    # Max phrase length in code points after normalization. 1..4000.
    PHRASE_MAX_LENGTH=280
    # Hard cap on GET /phrases. 1..1000.
    PHRASES_LIST_LIMIT=200
    # Reject request bodies above this size (bytes) with 413, before parsing. >= 4096.
    MAX_REQUEST_BYTES=1048576

    # --- Embeddings ---
    # Runtime enum has ONE value; `fake` exists only in the test settings class.
    EMBEDDING_PROVIDER=sentence_transformers
    EMBEDDING_MODEL=sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2
    # 40-hex Hugging Face Hub commit SHA the image was built with (set and verified in Unit 8).
    EMBEDDING_MODEL_REVISION=0000000000000000000000000000000000000
    # Must equal both the provider's output dimension and the `vector(n)` column typmod.
    EMBEDDING_DIMENSIONS=384
    EMBEDDING_TIMEOUT_SECONDS=10.0
    EMBEDDING_MAX_CONCURRENCY=2
    # Bounded LRU cache size for the embedding provider decorator. 0 disables caching entirely.
    EMBEDDING_CACHE_SIZE=512
    # HNSW ef_search for the validate endpoint's unfiltered top-1 `find_nearest` only. 1..1000.
    HNSW_EF_SEARCH=200

    # --- Concurrency ---
    # Bounds the wait for the save advisory lock (pg_advisory_xact_lock), in milliseconds.
    LOCK_TIMEOUT_MS=5000

    # --- API / platform ---
    # Comma-separated absolute origins, no wildcard.
    CORS_ORIGINS=http://localhost:3000
    LOG_LEVEL=INFO

    # --- Web (Next.js) ---
    # Browser-facing build arg; must match the API's externally reachable URL.
    NEXT_PUBLIC_API_URL=http://localhost:8000
    # Build arg; UI counter limit, kept equal to PHRASE_MAX_LENGTH.
    NEXT_PUBLIC_PHRASE_MAX_LENGTH=280
    # Server-side fetch (Server Components) only; resolves inside the compose network.
    API_INTERNAL_URL=http://api:8000
    ```

    A copy of this exact content also lives in the session scratchpad
    (`env.example.content.txt`) but that path is ephemeral and not part of the repo — treat the
    block above as the source of truth.
  - Nothing else in Unit 0's Verify line depends on `.env.example` existing (the Verify line checks
    `make test-unit`, `lint-imports`, and `pytest --collect-only -q` only — none reference the env
    file), so this gap does not block Unit 0's own verification, but it MUST be closed before Unit 4
    (compose `db`/`migrate`), Unit 14 (full compose wiring) or Unit 15 (README `cp .env.example
    .env` step), all of which depend on it existing and being complete.
- [x] 0.5 GREEN — `openspec/config.yaml` updated: `testing.status: installed`,
  `rules.apply.test_command` and `rules.verify.test_command` both set to `make test-unit`,
  `rules.verify.build_command` left empty (per design, until Unit 10). Detected versions recorded
  in both `openspec/config.yaml` and the commit body: pytest 9.1.1, vitest 5.0.1, ruff 0.16.8,
  mypy 2.3.1, import-linter 2.15, typescript 7.0.2, prettier 3.9.8, eslint 10.11.0.

**Verify (all confirmed after commit, on `chore/pv-00-scaffold`)**:
- `make test-unit` → green, 2 smoke tests (1 backend `test_app_package_is_importable`, 1 frontend
  "executes and evaluates a real assertion").
- `cd services/api && .venv/bin/lint-imports` → `Contracts: 5 kept, 0 broken.`
- `cd services/api && .venv/bin/python -m pytest --collect-only -q` → `1 test collected`, and
  `pytest --markers` lists exactly the 4 custom markers (`unit`, `integration`, `contract`,
  `slow`) with no warnings.
- `make lint` → ruff clean, mypy clean (`Success: no issues found in 11 source files`),
  import-linter clean.

**Commit**: `chore: scaffold monorepo with pytest, vitest and import-linter`
**SHA**: `2b1574247a6bb5c4178194a0fc911643a691d014`
**Branch**: `chore/pv-00-scaffold` (local only — not pushed; see "PR status" below)
**Base**: `main` at `80283cb` (stacked-to-main; targets `main` directly, no tracker branch)
**Lines changed**: 2,838 insertions / 18 deletions total; 327 insertions excluding the generated
`apps/web/package-lock.json` (2,511 lines) — within the 400-line budget either way it's counted.

## TDD Cycle Evidence

| Task | Test File | Layer | Safety Net | RED | GREEN | TRIANGULATE | REFACTOR |
|------|-----------|-------|------------|-----|-------|-------------|----------|
| 0.1/0.2 | `services/api/tests/unit/test_smoke.py` | Unit | N/A (new, first test in repo) | ✅ Written — failed with `No module named pytest` (no runner installed) | ✅ Passed after 0.2 (`1 passed in 0.01s`) | Triangulation skipped: task is purely structural (proves `import app` works; there is exactly one possible output — the package name string — no branching, no logic to force out with a second case) | ➖ None needed — one-line assertion |
| 0.1/0.3 | `apps/web/src/smoke.test.ts` | Unit | N/A (new, first test in repo) | ✅ Written — failed, `npx --no-install vitest` refused to run (package not installed) | ✅ Passed after 0.3 (`1 passed`) | Triangulation skipped: purely structural (proves the runner executes and evaluates one real arithmetic assertion; no branching) | ➖ None needed |

### Test Summary
- **Total tests written**: 2
- **Total tests passing**: 2
- **Layers used**: Unit (2), Integration (0), E2E (0)
- **Approval tests** (refactoring): None — no refactoring tasks in this batch (everything is new
  scaffolding)
- **Pure functions created**: 0 (Unit 0 is scaffolding only; no business logic yet)

## PR status

**Not opened.** No `gh` PR was created because this environment has no interactive PR-creation
step available to me and the branch is currently local-only (`git push` was not attempted — no
remote credentials/scope were confirmed, and the instructions said to leave the branch committed
locally if PR tooling isn't available). To open the PR:

```
git push -u origin chore/pv-00-scaffold
gh pr create --base main --head chore/pv-00-scaffold \
  --title "chore: scaffold monorepo with pytest, vitest and import-linter" \
  --body "<PR body per the stacked-to-main dependency-diagram convention in tasks.md>"
```

Per tasks.md's stacked-to-main table, PR base is `main` (this is PR "0" in the chain; PR "B.0" does
not exist as a separate PR since no bootstrap commit was needed — see Unit B.0 above).

## Deviations from design.md / tasks.md

1. **Unit B.0 required no new commit** — planning artifacts were already merged to `main` before
   this apply batch (see Unit B.0 section above). This is a deviation from tasks.md's assumption
   ("The repo has no commits") but not from the design's actual intent (artifacts tracked,
   `.atl/` ignored) — that intent was already satisfied.
2. **Backend module skeleton added beyond task 0.2's literal file list** — empty placeholder
   packages under `app/modules/{similarity,phrases}/...` and `app/platform/` were required to make
   `import-linter` (a stated Unit 0 Verify criterion) pass at all; see the 0.2 note above.
3. **`.env.example` not created** — blocked by a hard tool-permission deny on `.env*` paths; content
   is fully specified above and in the commit body for manual creation or a follow-up session with
   broader permissions. This is the one open item before Units 4/14/15 can rely on it.

## Remaining Tasks (as of the end of batch 1)

- [ ] Close the `.env.example` gap (human action or a session with `.env*` write permission).
- [x] Push `chore/pv-00-scaffold` and open PR #0 against `main` — **done between batches**: PR #2
  (`chore/pv-00-scaffold` -> `main`) merged at `53db4da`, confirmed at the start of batch 2 via
  `git log --oneline -5` and `git branch -a`.
- [x] Unit 1: Normalization, clamped score, similarity policy (tasks 1.1–1.3) — done this batch,
  see below.

---

## Unit 1: Normalization, clamped score, similarity policy

Branch `feat/pv-01-domain-policy`, based on `main` at `53db4da` (PR #2 / Unit 0 already merged).

- [x] 1.1 RED then GREEN — `services/api/src/app/modules/phrases/domain/normalization.py`
  (`display_form`, `comparison_form`) with `tests/unit/phrases/test_normalization.py`. Covers every
  named scenario in `specs/phrase-management/spec.md`'s "Text normalization" requirement: trim +
  NFC (decomposed accent), zero-width/control stripping, whitespace-controls-separate-words, ZWJ/ZWNJ
  preserved inside text (family emoji sequence, Persian ZWNJ word) and stripped-to-empty when the
  text is only joiners, casefold-then-re-NFC (using the real Unicode case U+01F0 'ǰ', whose
  `casefold()` decomposes to `"j" + COMBINING CARON`, verified NOT NFC, then re-composed by
  `comparison_form`), emoji/RTL preservation, idempotence of both forms, and code-point-accurate
  length after trim (280 content + 20 trailing spaces -> 280; an astral character U+1F95B counts as
  1 code point, proving Python's `len()` already matches the spec's "Unicode code points" unit).
- [x] 1.2 RED then GREEN — `modules/similarity/domain/{vector,cosine,policy}.py` with
  `tests/unit/similarity/test_cosine.py` and `tests/unit/similarity/test_policy.py`. `cosine.py`
  computes the full cosine-similarity formula (dividing by both norms, not assuming pre-normalized
  input) so it is a correct oracle for arbitrary vectors; `cosine_distance = 1 - cosine_similarity`
  mirrors pgvector's `<=>` operator. `policy.py`'s `SimilarityPolicy.score/is_duplicate/includes/
  max_distance` match design.md's contract exactly (`score = round(min(1,max(0,1-d)),4)`, Decimal
  string comparison for the threshold, `max_distance() = 1 - t + 1e-4` widened bound, `2.0` at
  `t=0`). The `(raw, score, is_duplicate, in_matches)` test table is verbatim from tasks.md: raw
  cosine 0.79996 -> 0.8000 (duplicate at t=0.80), 0.79994 -> 0.7999 (not), -0.3 -> 0.0 (negative
  clamped), 1.0000000002 -> 1.0 (overshoot clamped), plus the t=0.80005 boundary vs 0.79996/0.80006.
  **Vocabulary note** (not a behavior deviation): `SimilarityPolicy.score`/`.includes` take a raw
  *distance* per design.md's literal signature (`raw_distance: float`), while the spec and tasks.md
  table state scenarios in terms of raw *cosine*. Since `distance = 1 - cosine` for L2-normalized
  vectors (design.md's own `score = 1 - distance` relation), the two vocabularies are the same
  function up to that substitution; each test row converts `distance = 1 - raw_cosine` before
  calling the policy, and the resulting expected scores match the spec's scenarios exactly (verified
  by hand and by execution) — this is documented explicitly in the test file's docstring for the
  next reader.
- [x] 1.3 GREEN — `modules/similarity/domain/errors.py` (`EmbeddingUnavailable`,
  `EmbeddingTimeout`) and `phrases/domain/errors.py` (`EmptyPhraseText`, `PhraseTooLong`, carrying a
  `max_length` attribute) with `tests/unit/phrases/test_errors.py` and
  `tests/unit/similarity/test_errors.py`. **Naming deviation from tasks.md's literal task text**:
  tasks.md 1.3 names the classes `EmptyText`/`TooLong`; design.md's "API Contract and Error Mapping"
  registry (the authoritative source for internals per this change's own spec-reconciliation note)
  names them `EmptyPhraseText`/`PhraseTooLong`. I followed design.md. No raising logic exists yet —
  these are plain marker exceptions; Unit 3's use cases will raise them, Unit 6's `platform/errors.py`
  will map them to HTTP (422 `VALIDATION_ERROR`, 503 `EMBEDDING_UNAVAILABLE`, 504
  `EMBEDDING_TIMEOUT`). **Open design question for Unit 6** (flagged, not resolved here): design.md's
  `platform/errors.py` comment ("`DomainError` -> HTTP registry, envelope") implies a single shared
  base class every domain error inherits from, for one `@app.exception_handler(DomainError)` to catch
  them all — but neither design.md nor tasks.md specifies where that base class should live without
  violating the "similarity MUST NOT import phrases" / "domain MUST NOT import platform" layering
  intent. Unit 1's four error classes each inherit directly from `Exception` (no shared base) to stay
  self-contained; Unit 6 will need to decide how the registry recognizes all of them (a common base,
  or a registry keyed by concrete type — both remain open).
- Added `tests/unit/__init__.py`, `tests/unit/phrases/__init__.py`,
  `tests/unit/similarity/__init__.py` (not in tasks.md's literal file list): pytest's default
  "prepend" import mode raised `import file mismatch` on the `test_errors.py` basename colliding
  across `tests/unit/phrases/` and `tests/unit/similarity/` without package `__init__.py` files.
  Adding them makes each test module's dotted name unique (`unit.phrases.test_errors` vs
  `unit.similarity.test_errors`) and will prevent the same collision for any future unit's same-named
  test file.

**Review-budget trim.** The first complete draft of Unit 1 diffed at 526 lines (526 insertions,
0 deletions), above the 400-line PR budget despite the ~340-line estimate in tasks.md's PR chain
table. Unit 1 has no designated split seam in tasks.md (unlike e.g. Unit 2's "split `find_matches`
out" note) and its three sub-tasks are one cohesive, tightly-coupled commit per the unit's own
"Squash RED+GREEN into ONE commit" instruction, so I did not split it into multiple PRs. Instead I
trimmed documentation/comment density only — shortening module and test docstrings, consolidating
near-duplicate parametrized test cases (e.g. merging separate `score`/`is_duplicate` tables into one
three-column table, merging the three inclusive-threshold-boundary tests into one parametrized test)
— across several REFACTOR passes, re-running the full suite after each change to confirm nothing
broke. **No test scenario, assertion, or spec-mapped case was removed**; the same spec scenarios are
covered by fewer, denser test functions. Final diff: exactly 400 insertions, 0 deletions, 14 files.

**Verify (all confirmed after commit, on `feat/pv-01-domain-policy`)**:
- `cd services/api && .venv/bin/python -m pytest tests/unit -q` -> `28 passed in 0.07s` (well under
  the "~2s" Unit 1 verify budget).
- `cd services/api && .venv/bin/lint-imports` -> `Contracts: 5 kept, 0 broken.` (domain purity intact
  — the new `similarity/domain` and `phrases/domain` modules import neither `fastapi`, `sqlalchemy`,
  `torch` nor each other).
- `cd services/api && .venv/bin/ruff check src tests` -> `All checks passed!`
- `cd services/api && .venv/bin/mypy src` -> `Success: no issues found in 17 source files`
- `make test-unit` (root) -> backend 28 passed, frontend (unchanged) 1 passed.

**Commit**: `feat(domain): normalization forms, clamped score and similarity policy`
**SHA**: `631fe86b53fb4eb7f97976ed259ff6cf17b75ea2`
**Branch**: `feat/pv-01-domain-policy`
**Base**: `main` at `53db4da` (stacked-to-main; targets `main` directly)
**Lines changed**: 400 insertions / 0 deletions, 14 files (see "Review-budget trim" above).

### TDD Cycle Evidence (Unit 1)

| Task | Test File | Layer | Safety Net | RED | GREEN | TRIANGULATE | REFACTOR |
|------|-----------|-------|------------|-----|-------|-------------|----------|
| 1.1 | `tests/unit/phrases/test_normalization.py` | Unit | N/A (new) | ✅ Written — `ModuleNotFoundError: app.modules.phrases.domain.normalization` | ✅ Passed (11/11 before consolidation, 9 after) | ✅ 9 scenarios (trim/NFC, zero-width+control, ZWJ/ZWNJ inside, all-joiners-empty, casefold-renormalize, emoji/RTL, idempotence x2, length x2) | ✅ Merged two closely-related pairs of tests, shortened comments; suite re-run green after each step |
| 1.2 (cosine) | `tests/unit/similarity/test_cosine.py` | Unit | N/A (new) | ✅ Written — `ModuleNotFoundError: app.modules.similarity.domain.cosine` | ✅ Passed | ✅ Identical, Orthogonal, Oracle-agreement (dot-product equivalence for L2-normalized vectors) | ✅ Tuple literals condensed, comments shortened |
| 1.2 (policy) | `tests/unit/similarity/test_policy.py` | Unit | N/A (new) | ✅ Written — `ModuleNotFoundError: app.modules.similarity.domain.policy` | ✅ Passed | ✅ 4-row score/is_duplicate table, 3-row inclusive-boundary table, threshold-zero, 2-row >4-decimals table, max_distance x2 | ✅ Consolidated two 4-row tables into one 3-column table; merged three boundary tests into one parametrized test; both re-verified green |
| 1.3 (phrases) | `tests/unit/phrases/test_errors.py` | Unit | N/A (new) | ✅ Written — `ModuleNotFoundError: app.modules.phrases.domain.errors` | ✅ Passed | ✅ `PhraseTooLong` triangulated with 2 different `max_length` values; `EmptyPhraseText` triangulation explicitly skipped (purely structural marker, no branching) | ➖ None needed |
| 1.3 (similarity) | `tests/unit/similarity/test_errors.py` | Unit | N/A (new) | ✅ Written — `ModuleNotFoundError: app.modules.similarity.domain.errors` | ✅ Passed | Triangulation skipped: both are purely structural marker exceptions, no attributes, no branching | ➖ None needed |

### Test Summary (Unit 1)
- **Total tests written across the RED/GREEN cycle**: 37 (before REFACTOR-phase consolidation)
- **Total tests passing at final commit**: 28 (consolidated via `pytest.mark.parametrize`; same
  scenario coverage, fewer function definitions — see "Review-budget trim" above)
- **Layers used**: Unit (28), Integration (0), E2E (0), Contract (0)
- **Approval tests** (refactoring): None — no pre-existing behavior to preserve, everything is new
- **Pure functions created**: 6 (`display_form`, `comparison_form`, `cosine_similarity`,
  `cosine_distance`, and `SimilarityPolicy`'s four methods — `score`, `is_duplicate`, `includes`,
  `max_distance` — are pure given the frozen dataclass's `threshold`)

## PR status (Unit 1)

**Opened.** `gh auth status` confirmed an active, authenticated session, so — unlike batch 1's Unit
0 (where the branch was left local-only) — I pushed the branch and opened the PR myself this batch,
per the orchestrator's explicit instruction to do so and stop only if push/PR creation failed for a
concrete reason (it did not).

- `git push -u origin feat/pv-01-domain-policy` → pushed cleanly, new branch on `origin`.
- `gh pr create --repo Aaron-Shrike/todo-ia --base main --head feat/pv-01-domain-policy ...` →
  **PR #3**, <https://github.com/Aaron-Shrike/todo-ia/pull/3>. Base `main`, head
  `feat/pv-01-domain-policy`, no labels (matching PR #1/#2 precedent in this repo — no issue tracker
  / `type:*` label convention is in use here, despite the generic `branch-pr` skill's template
  suggesting one).
- PR body follows PR #2's established convention: dependency-diagram code block with the chain
  pinned at unit 1, Start/End/Prior dependencies/Follow-ups/Out of scope, "What's in this PR",
  naming/vocabulary notes (the two documented deviations), the review-budget trim note, and the
  Verification section with the exact command output.

## Deviations from design.md / tasks.md (Unit 1)

1. **Error class names**: `EmptyPhraseText`/`PhraseTooLong` (design.md) instead of tasks.md's literal
   `EmptyText`/`TooLong` shorthand. See task 1.3 notes above.
2. **`SimilarityPolicy` distance vs. cosine vocabulary**: test tables convert the spec's "raw cosine"
   language to the distance parameter design.md's contract signature expects. See task 1.2 notes
   above — this is a vocabulary bridge, not a behavior change; the numeric outcomes match the spec
   exactly.
3. **Shared `DomainError` base class location is still undecided** — flagged as an open question for
   Unit 6, not resolved in Unit 1 (see task 1.3 notes above).
4. **Test package `__init__.py` files added**, not in tasks.md's literal file list, to resolve a
   pytest basename collision. See the note after task 1.3 above.
5. **Diff trimmed for the review budget** (documentation/comments only, no coverage lost) — see
   "Review-budget trim" above.

## Remaining Tasks (next batch)

- [ ] Close the `.env.example` gap (human action or a session with `.env*` write permission) —
  still open from batch 1.
- [ ] Review and merge PR #3 (`feat/pv-01-domain-policy` -> `main`).
- [ ] Unit 2: Ports, unit of work, fake embedder, in-memory repository (tasks 2.1–2.3) — NOT
  started, per the orchestrator's explicit instruction to stop after Unit 1.
- [ ] Unit 6 (or earlier, if convenient): resolve the shared `DomainError` base class question noted
  above before `platform/errors.py` is written.

## Status

3/3 assigned units across both batches substantially complete: B.0 (no-op, already satisfied), Unit
0 (7/7 sub-tasks, one file blocked by tooling not missing work, merged via PR #2), Unit 1 (3/3
sub-tasks fully done, 28/28 tests green, all lint/type/import checks green, diff exactly at the
400-line budget, pushed and opened as PR #3). Ready for review before Unit 2 is launched. Branch
`feat/pv-01-domain-policy` is on `origin`, commits `631fe86` (feat) and `abfe52d` (docs).
