# Proposal: Phrase Validation with Semantic Duplicate Detection

## Intent

**Business problem.** A phrase list whose only guard is exact string matching silently fills with the same idea written five different ways ("Comprar leche" / "comprar Leche" / "Buy milk"). The list loses trust as a source of truth, and the person curating it pays the cleanup cost later, by hand.

**Why now.** This is the core capability of the product: the value is not storing text, it is refusing to store the *same meaning twice* without the author knowing. Everything else (form, list, persistence) is scaffolding around that decision.

**Success.** A user writes a phrase, presses *Validar*, and gets an honest answer — the closest existing phrase plus **every** phrase above the threshold, ordered by score — then stays in control: confirm or cancel. The system never decides for them and never saves behind their back. Pressing *Guardar* directly is equally safe: the server always re-validates, and the UI narrates the staged progress ("Validando...", "Revalidando...") so the two steps stay legible.

## Target Users and Situations

| User | Situation | Urgency |
| --- | --- | --- |
| Phrase author | Adding a phrase to a list they cannot fully remember | Immediate, in-flow; must not block typing |
| List curator | Wants a clean, non-redundant list over time | Cumulative; pays the cost of every missed duplicate |
| Technical reviewer | Runs the project locally, inspects layering, tests, commit history | One session; must work with `docker compose up` |

## Scope

### In Scope

- Primary flow *Validate then Save*: `POST /phrases/validate` (stateless, persists nothing) then `POST /phrases` (authoritative). Saving without validating first stays safe — the server re-validates either way.
- Semantic similarity via local embeddings (sentence-transformers multilingual MiniLM, pinned by Hub commit SHA) behind an `EmbeddingProvider` port; cosine similarity with scores clamped to [0, 1] and rounded to 4 decimals; configurable threshold.
- **Embedding cache**: a bounded in-process LRU decorator over `EmbeddingProvider` (key = model id + comparison form) so matches pages 2..n and the second leg of a blind Save do not re-embed. It caches only the pure text-to-vector function — never a verdict or a match page — and changes latency only; its counters are exposed through `GET /health`.
- **Full match list**: validation returns `most_similar` (the brief's requirement) plus `matches` — ALL phrases with score >= threshold, ordered by score desc (`id` tie-break for equal raw distance; displayed 4-decimal scores may tie without being in `id` order), computed by an exact scan and keyset/cursor paginated, default page size 50 (`MATCHES_PAGE_SIZE`, configurable). No fixed top-N, no silent truncation; the response carries `next_cursor` / `has_more`.
- Server-side re-validation on save with a `confirm_duplicate` flag; `409 DUPLICATE_CONFIRMATION_REQUIRED` when unconfirmed.
- Validation metadata persisted on the phrase row: score, most similar phrase id, status, `validated_at`.
- `GET /phrases`, `GET /health` (readiness includes embedding model).
- Next.js + TypeScript UI with an explicit staged state machine: `idle | validating | revalidating | duplicate | ok | saving | error`, narrating each in-flight request (Validando... / Revalidando... / Guardando...) and never a stage after the 201; infinite scroll over the paginated match list; saved-phrase list with status badge and optional score.
- UI copy in neutral Spanish; code, identifiers, API field names, tests and docs in English (API errors are code-based, the UI owns the copy).
- Consistent response/error envelope `{error:{code, message, details?}}`.
- Alembic raw-SQL migrations; Docker Compose (Postgres + pgvector, migrate, backend, frontend); `.env.example`; README.
- **"Beyond the brief" decision log** in `docs/decisions/` (ADR-style, one entry per deviation: "the brief asked for X; we decided Y because Z"), summarized in the README. The top level holds exactly the five `beyond-brief` entries; technical ADRs live separately in `docs/decisions/technical/`. Known entries: (1) full match list with infinite scroll instead of a single most-similar phrase; (2) monorepo with independently deployable services and modular hexagonal architecture; (3) local sentence-transformers inference of the Hub checkpoint now (rather than the hosted Inference API) with an ONNX/fastembed migration path; (4) Next.js instead of plain React/Vue; (5) staged validate/re-validate progress UX.
- Tests: domain/use-case units (fake embedder, in-memory repo), integration against real Postgres, OpenAPI contract test, one slow real-model test that doubles as model-integration evidence.

### Out of Scope (Non-Goals)

- **Hugging Face Inference API adapter** — explicitly dropped; local provider only.
- **Production deployment / hosting** — local Docker Compose only.
- **Authentication, users, multi-tenancy** — the list is global and anonymous.
- **Edit and delete phrases** — create and read only.
- **Search, filtering, or sorting of `GET /phrases` beyond newest-first** (pagination is in scope only for the `matches` list).
- **Re-embedding or backfilling on model or threshold change.**
- **Clustering, near-duplicate merge suggestions, or bulk dedupe of existing data.**
- **ONNX / fastembed runtime migration** — documented as an evolution path in `docs/decisions/`, not built.
- **Rate limiting and an observability stack** (the embedding cache's counters are exposed only through `GET /health`; no shared/distributed cache).

## Capabilities

> Contract with the specs phase. `openspec/specs/` is empty (greenfield): every capability below is new.

### New Capabilities

- `phrase-management`: create and list phrases; text normalization and length rules; persisted validation metadata.
- `semantic-validation`: embedding generation, cosine similarity (clamped to [0, 1]), threshold decision, most-similar-phrase reporting, the complete above-threshold match set ordered by score desc, and the bounded embedding cache (reuse across validate, matches pages and save).
- `duplicate-confirmation`: server-side re-validation on save, confirmation flag, 409 conflict flow.
- `api-contract`: consistent success/error envelope, error codes, HTTP status mapping, keyset pagination contract (`limit`, `cursor`, `next_cursor`, `has_more`) for matches, input bounds (raw-length cap, body-size limit, strict types, strict cursor validation), CORS, health and readiness (including the operational `embedding_cache` counters).
- `phrase-ui`: form, saved-phrase list with status badge and optional score, staged validation state machine with progress narration (no stage after the 201), duplicate alert with infinite-scroll match list, confirm/cancel, Spanish error messaging.

### Modified Capabilities

None (greenfield project).

## Approach

Modular hexagonal architecture in a monorepo with independently deployable services. The domain owns the `SimilarityPolicy` and a pure-Python cosine function and knows nothing about FastAPI, SQLAlchemy or torch. Embeddings sit behind an `EmbeddingProvider` port, so the runtime is an adapter swap; persistence sits behind a `PhraseRepository` port with a pgvector-backed adapter and an in-memory adapter for fast tests. FastAPI `Depends` is the composition root; tests override it.

The flow is deliberately **stateless**: the validate call is advisory and persists nothing, and `POST /phrases` recomputes similarity server-side rather than trusting a client-supplied score. A stale or forged validation result cannot bypass the check. Because validation is stateless, match paging is keyset-based on `(raw distance asc, id asc)` (equivalently score desc); the design resolved how a page request reproduces the query vector — re-embed per page, made cheap by the embedding cache — without weakening that statelessness.

Rationale for sentence-transformers over a hosted API: no network dependency, no token, reproducible for a reviewer running offline. The cost (image size, cold start) is acknowledged and the migration trigger to ONNX/fastembed is written down as a decision-log entry in `docs/decisions/`.

## Affected Areas

| Area | Impact | Description |
| --- | --- | --- |
| `services/api/src/app/modules/{phrases,similarity}/domain/` | New | Entities, SimilarityPolicy, cosine, normalization, ports, domain errors |
| `services/api/src/app/modules/phrases/application/` | New | `ValidatePhrase`, `ListMatches`, `SavePhrase`, `ListPhrases` use cases |
| `services/api/src/app/modules/*/adapters/` | New | sentence-transformers embedder, bounded (timeout) and caching decorators, fake embedder, pgvector repository and unit of work, in-memory repository |
| `services/api/src/app/modules/phrases/api/`, `services/api/src/app/platform/` | New | Routers, schemas, error handlers, settings, DI wiring, health |
| `services/api/migrations/` | New | Alembic raw-SQL migrations, `CREATE EXTENSION vector` |
| `services/api/tests/` | New | Unit, integration, contract suites |
| `apps/web/` | New | Next.js app, API client, phrase feature, vitest tests |
| `docs/decisions/` | New | Exactly five "beyond the brief" ADR-style entries at the top level (extended on every future deviation); technical ADRs in `docs/decisions/technical/` |
| Root | New | `docker-compose.yml`, `.env.example`, `README.md`, `docs/architecture.md` |

## Business Rules

1. Phrase text MUST be normalized before validation and storage: whitespace controls become spaces, zero-width (U+200B, U+2060, U+FEFF) and other control characters are stripped, the result is NFC and trimmed; ZWJ/ZWNJ inside the text are preserved. The comparison form (casefolded, NFC again, whitespace collapsed) is what is embedded.
2. Empty or whitespace-only text MUST be rejected (422) and never embedded.
3. Phrase length MUST NOT exceed `PHRASE_MAX_LENGTH` (default 280, configurable).
4. A phrase is a potential duplicate when the best cosine score is **greater than or equal to** `SIMILARITY_THRESHOLD` (default 0.80, validated within [0,1] at startup; inclusive boundary).
5. Exact duplicates (case- and whitespace-insensitive) are ordinary duplicates with score 1.0 and MAY be confirmed and saved. There is no separate exact-duplicate error and no plain unique index on normalized text; a PARTIAL unique index (`WHERE validation_status = 'unique'`) is a database integrity backstop, so confirmed duplicates stay allowed.
6. Saving a flagged duplicate MUST require an explicit `confirm_duplicate`; the server re-validates and never trusts a client-supplied score, whether or not the user validated first.
7. The `matches` list MUST contain every phrase at or above the threshold — never a fixed top-N — ordered by score desc (raw distance asc, with a stable `id` tie-break for equal distances; scores are clamped to [0, 1] before rounding), exposed page by page via an opaque cursor. Reaching the end of the list MUST be possible; `has_more` reflects truth, not truncation.
8. The single `SIMILARITY_THRESHOLD` decides BOTH "is duplicate" and "which phrases are listed as matches"; `most_similar` is always the first element of the first page when matches exist.
9. Every persisted phrase MUST carry its validation metadata: score (nullable), most similar phrase id (nullable), status (`unique` | `duplicate_confirmed`), `validated_at`.
10. If the embedding model is unavailable or times out, the phrase MUST NOT be saved and validation MUST NOT be silently skipped.
11. Changing the threshold affects future validations only; stored phrases and their recorded metadata are immutable historical facts.

## Edge Cases (Product Level)

| Case | Expected product behavior |
| --- | --- |
| Empty list (first phrase ever) | Not a duplicate; null score, null match, empty `matches`, `has_more: false`; saves cleanly |
| Score exactly at threshold | Treated as duplicate (inclusive) and included in `matches` |
| Hundreds of matches above threshold | First page (default 50) returned with a cursor; UI loads more on scroll; nothing is silently dropped |
| Threshold set very low (or 0) | Nearly the whole list matches (a threshold of 0 admits every phrase, since scores are clamped to [0, 1]); behavior stays paginated, never a single giant payload |
| Page boundary / tie scores | Keyset order `(raw distance asc, id asc)` (tolerant of sub-ulp vector drift) guarantees no duplicated or skipped item across pages; equal displayed scores need not be in `id` order |
| Phrase saved between two match pages | Paging is advisory and may show a slightly stale set; the save-time re-validation is the authority |
| User presses Save without validating | Staged UI shows "Validando..." then "Revalidando..."; server returns 409 if it is a duplicate |
| Model down or slow | Clear, honest error; nothing saved; user can retry |
| User edits text after validating | Validation state resets; stale result is never reusable |
| User confirms a duplicate | Save succeeds and is recorded as `duplicate_confirmed` |
| Two users save similar phrases concurrently | Advisory lock serializes check-and-insert; residual race documented, not hidden |
| Mixed ES/EN phrasing of the same idea | Multilingual model should flag it; calibration fixture covers this |
| Emoji, accents, RTL text | Normalized, accepted, never crashes validation |
| Very long phrase | Rejected before embedding, with the limit stated in the message |

## Risks

| Risk | Likelihood | Mitigation |
| --- | --- | --- |
| Threshold miscalibration across ES/EN (false alarms or misses) | Med | ES/EN fixture, boundary tests, env-configurable threshold |
| Image size and cold start (torch + model) | Med | CPU-only wheel, model baked at build time, decision-log entry with migration trigger |
| Docker required for reviewers (pgvector) | Med | Single `docker compose up`, healthchecks, README quickstart |
| Semantic check-and-insert race | Low | `pg_advisory_xact_lock`; limitation documented in design |
| Match paging on a stateless endpoint (re-embed per page vs. cache) | Med | Resolved in design: re-embed per page, memoized by the embedding cache; keyset ordering fixed at `(raw distance asc, id asc)` with a drift-tolerant key |
| Low threshold turns matches into a near-full list; the exact match scan is O(n) per page (and the exact nearest-neighbour read on save is O(n) once per save) | Low | Pagination by default, configurable page size; the O(n) scans are accepted at target scale (the save verdict is exact so an approximate index miss can never let a duplicate through) and their cost is measured in the implementing slice |
| Scope creep beyond the challenge | Med | Explicit non-goals above; capabilities list is the contract |
| Work exceeds the 400-line review budget | High | Split into work units (see delivery note) |

## Rollback Plan

- **Pre-merge.** The change is additive on a greenfield repo: revert the feature branch; nothing in `main` depends on it.
- **Per work unit.** Each unit is an independent commit/PR slice with its own tests, revertible without touching earlier slices.
- **Data.** Each Alembic migration ships a working `downgrade` (drop table, then `DROP EXTENSION vector`); no pre-existing data can be lost.
- **Runtime tuning.** Similarity behavior is env-driven: raise `SIMILARITY_THRESHOLD` toward 1.0 to make validation effectively permissive without a code change or redeploy of logic.
- **Local environment.** `docker compose down -v` restores a clean state.

## Dependencies

- Docker and Docker Compose on the reviewer machine (mandatory).
- Postgres image with pgvector (exact tag verified during design).
- `sentence-transformers` multilingual MiniLM weights downloadable at image build time.
- Python 3.x + FastAPI + SQLAlchemy + Alembic; Node + Next.js + TypeScript.

## Success Criteria

- [ ] A reviewer runs `docker compose up` and reaches a working UI with no manual setup beyond `.env`.
- [ ] Semantically similar but textually different phrases (ES and EN) are flagged as duplicates with the matching phrase and score shown.
- [ ] Validation returns `most_similar` AND a `matches` list with every phrase above the threshold, ordered by score desc, paginated; the UI reaches the last match via infinite scroll.
- [ ] Unrelated phrases save without friction.
- [ ] Confirming a duplicate saves it and records `duplicate_confirmed`; cancelling saves nothing.
- [ ] `POST /phrases` re-validates server-side; a forged or stale client score cannot bypass the check.
- [ ] Saving directly (without pressing Validate) is safe and shows the staged "Validando... / Revalidando..." progress.
- [ ] The saved-phrase list shows a status badge (and optionally the score) per phrase.
- [ ] UI copy is neutral Spanish while code, identifiers and docs remain English.
- [ ] Every saved phrase carries score, most similar phrase id, status, and `validated_at`.
- [ ] Threshold, max length and match page size are environment-configurable; invalid threshold fails fast at startup.
- [ ] Embedding failure returns a clear error and saves nothing.
- [ ] Tests cover the semantic-validation and save flows, including threshold boundary, empty store, model failure, and match pagination boundaries (tie scores, last page).
- [ ] OpenAPI documents every endpoint, the pagination contract, and every error code; error envelope is consistent.
- [ ] README explains the architecture, the embedding choice, and the ONNX/fastembed evolution path.
- [ ] README covers install and run (`docker compose up`, prerequisites) and every environment variable with its default, as the brief requires.
- [ ] The top level of `docs/decisions/` contains exactly the five known "beyond the brief" entries in "the brief asked X; we decided Y because Z" form (technical ADRs live in `docs/decisions/technical/`), and every later deviation adds one.
- [ ] Commit history is atomic and conventional; each work unit is independently reviewable.

## Delivery Note

This change will **exceed the 400-line review budget** — it stands up a backend, a frontend, migrations, and Docker infrastructure from zero. It MUST be split into small, independently deliverable work units (suggested slices, refined in the design's delivery plan: domain + policy with tests → ports, fakes, cache and cursor codec → use cases → persistence, migrations and a minimal API Dockerfile → exact match query and top-1 read → API layer and error contract → embedding adapter → frontend (machine, infinite scroll, list) → Docker Compose → README → decision log).

`delivery_strategy: ask-on-risk` — `sdd-tasks` MUST forecast the budget and `sdd-apply` MUST NOT start oversized work until chained/stacked slices are resolved.
