# Exploration: phrase-validation

## Current State
Greenfield repo: only `docs/`, `openspec/`, `.atl/`. No code, manifests, or CI. Stack is intended, not detected.

## Proposed Layout
- `backend/app/domain/`: entities, SimilarityPolicy, cosine function, ports (EmbeddingProvider, PhraseRepository). No framework imports.
- `backend/app/application/`: use cases ValidatePhrase, SavePhrase.
- `backend/app/adapters/`: embeddings (local sentence-transformers, optional HF API, fake), persistence (SQLAlchemy).
- `backend/app/api/`: routers, schemas, error handlers, DI wiring.
- `backend/migrations/`, `backend/tests/` (unit, integration, contract).
- `frontend/src/`: api/, features/phrases/, components/, vitest tests.
- `docker-compose.yml`, `.env.example`, `README.md`, `docs/architecture.md`.

## Recommendations
1. **Frontend**: React + Vite + TypeScript. Explicit validation state machine: idle | validating | duplicate | ok | error. Vue 3 is the alternative.
2. **Embeddings**: `paraphrase-multilingual-MiniLM-L12-v2` (384 dims), local, baked into the Docker image. Optional HF Inference API adapter behind the same port (`EMBEDDING_PROVIDER=hf_api`). multilingual-e5-small rejected (needs query:/passage: prefixes, clustered scores make the threshold fragile). Load model once at startup; inference in a threadpool with timeout. Default threshold 0.80, calibrated on an ES/EN fixture.
3. **Vector storage**: pgvector (`pgvector/pgvector:pg16`, `vector(384)`, `<=>` operator; similarity = 1 - distance; normalize at write). Keep a pure-Python cosine in the domain as a test oracle and an in-memory repository for fast tests. Alternative: REAL[]/JSONB with Python cosine (O(n), no extension).
4. **Migrations**: Alembic with hand-written raw SQL (`op.execute`); first migration runs `CREATE EXTENSION vector`. One-shot `migrate` Compose service. Optional exported `docs/schema.sql`.
5. **Layering**: hexagonal ports (Protocol/ABC), constructor injection, FastAPI `Depends` as composition root, `dependency_overrides` in tests. Domain errors: EmbeddingUnavailable, InvalidPhrase, DuplicateConfirmationRequired. FakeEmbedder with lookup table for exact boundary scores, plus a failing variant.
6. **Validate-then-save**: stateless with server-side re-validation.
   - `POST /phrases/validate` `{text}` -> 200 `{data:{is_duplicate, threshold, score|null, most_similar:{id,text}|null}}`, persists nothing.
   - `POST /phrases` `{text, confirm_duplicate?}` recomputes score; if score >= threshold and not confirmed -> 409 `DUPLICATE_CONFIRMATION_REQUIRED` with match and score; else 201.
   - Metadata persisted on the phrase row: `similarity_score` (nullable), `most_similar_phrase_id` (FK, nullable), `validation_status` (unique | duplicate_confirmed), `validated_at`, plus text, normalized_text, embedding, created_at.
   - Race handling: `pg_advisory_xact_lock` around check-and-insert; unique index on normalized_text -> 409 `EXACT_DUPLICATE`.
   - Also `GET /phrases`, `GET /health`. Error shape `{error:{code, message, details?}}`; 422 VALIDATION_ERROR, 503 EMBEDDING_UNAVAILABLE, 504 timeout.
7. **Edge cases** (each becomes a G/W/T scenario + test): empty/whitespace 422 (trim first); max length 280 configurable; Unicode NFC + strip zero-width/control chars (accents, emoji, RTL); exact duplicates case-insensitive; empty DB -> not duplicate, null score/match; threshold inclusive (>=), test at t, t-eps, t+eps, round to 4 decimals, validate threshold in [0,1] at startup; model failure/timeout never saves and never silently skips; /health reports readiness; model-dim vs column mismatch fails fast; concurrent inserts; frontend disables buttons in flight and resets state on text edit.
8. **Infra/tests**: Compose services db (healthcheck), migrate, backend, frontend. Env: DATABASE_URL, SIMILARITY_THRESHOLD, EMBEDDING_PROVIDER, EMBEDDING_MODEL, HF_API_TOKEN, EMBEDDING_TIMEOUT_SECONDS, PHRASE_MAX_LENGTH, CORS_ORIGINS, VITE_API_URL. Tests: unit (domain + use cases, fake embedder, in-memory repo; strict-TDD core), integration (TestClient + real Postgres/pgvector for repository), one `@pytest.mark.slow` real-model test doubling as HF evidence, OpenAPI contract test; vitest + testing-library on the frontend. Tooling: ruff, mypy/pyright, eslint, tsc, prettier.

## Risks
- Image size/build time (torch + model); mitigate with CPU wheel and build-time bake.
- Threshold miscalibration across ES/EN.
- pgvector requires Docker for reviewers.
- Semantic check-and-insert race (advisory lock; document limitation).
- Optional HF API adapter drift (mark experimental).
- 400-line review budget: plan small tasks / chained PRs.

## Open Decisions
1. Docker required for reviewers (pgvector)? Recommended: yes.
2. Confirm React over Vue.
3. Confirm threshold 0.80 and max length 280.
4. Keep optional HF API adapter or drop for scope?
5. Exact duplicates: distinct 409 EXACT_DUPLICATE or just score 1.0?

## User Decisions (confirmed in conversation)
- **Docker is mandatory** for running the project; lightweight Postgres + pgvector image (exact tag/size to be verified in design).
- **Embeddings**: `sentence-transformers` with multilingual MiniLM, local. Rationale: most recognizable and lowest compatibility risk for reviewers.
- **Evolution plan (must be documented in design/README)**: ONNX/`fastembed` is a lighter and faster CPU runtime with equivalent results. The embedder MUST live behind the `EmbeddingProvider` port so migrating is an adapter swap with no domain/application changes. Migration criteria: image size, cold start, or RAM limits in a future deployment.
- **Deployment**: local only (Docker Compose). Hostinger shared hosting is discarded; no production deploy in scope.
- **Frontend**: Next.js (React) with TypeScript.
- **Monorepo** with independently deployable services (own Dockerfile and config each).
- **Modular hexagonal architecture**: modules with clear boundaries and ports so any module (e.g. embeddings) can be extracted into a microservice later without touching the domain.

- **Exact duplicates** (case/whitespace-insensitive): treated as a regular duplicate with score 1.0; the user may confirm the save. No separate `EXACT_DUPLICATE` code. Consequence (SUPERSEDED by the partial-index decision below): do NOT add a PLAIN unique index on `normalized_text` (it would reject confirmed duplicates); the original "advisory lock only" stance is now lock plus a partial unique index.
- **Partial unique index ADOPTED (supersedes the "no unique index" consequence above; user-confirmed)**: create `UNIQUE INDEX ... ON phrases (normalized_text) WHERE validation_status = 'unique'`. It does not contradict the earlier rationale: `duplicate_confirmed` rows are outside the index so confirmed duplicates stay allowed, and an unconfirmed identical text is never inserted as `unique` because the server returns 409. Purpose is integrity (DB guarantee and backstop to the advisory lock and app bugs), NOT performance (that comes from HNSW, the embedding cache and keyset pagination). It does not cover semantic near-duplicates, which remain protected only by the advisory lock plus application logic; that residual race stays documented. A unique violation on insert must never be a 500: bounded retry through the normal path, yielding 409 `DUPLICATE_CONFIRMATION_REQUIRED`. Tracked as ADR-006 (type `technical`; the five beyond-brief entries are unchanged).
- **HF Inference API adapter DROPPED** (answers Open Decision 4): local `sentence-transformers` only; no `hf_api` provider, no `HF_API_TOKEN`. The earlier optional-adapter recommendations above are superseded.
- **Working defaults, pending calibration** (Open Decision 3): threshold `0.80` and max length `280` are working defaults, not final. The threshold default is finalized after the first measured ES/EN slow run; a changed default is a recorded spec-change trigger.
- **Architecture Decision Record required**: document "why sentence-transformers now, why/when to migrate to ONNX/fastembed" in design and README.

- **Validate/save UX (from proposal review)**: primary UI flow is Validate then Save, but the API stays safe if validation is skipped (server always re-validates, 409 without `confirm_duplicate`). The UI must make the flow feel like two distinct steps even when the user presses Save directly, showing a staged progress state with labels such as "Validating..." and "Re-validating..." (a visible loading view that narrates what is happening). The frontend state machine must model these stages explicitly.

- **Matches (supersedes the "single most similar" assumption)**: validation returns `most_similar` (required by the brief) PLUS a `matches` list with ALL phrases whose score >= threshold, ordered by score desc, not a fixed top-N. The single configurable threshold decides both "is duplicate" and "which matches are listed". Default page size 50 (configurable, e.g. `MATCHES_PAGE_SIZE`); results are paginated (cursor/keyset) and the UI loads more with infinite scroll, so the user can reach every match. The response carries pagination info (next cursor / has_more) instead of a hard truncation. Design must resolve how paging works on a stateless validate endpoint (re-embed per page vs. short-lived cache) and the keyset ordering (score desc, id tie-break).
- **"Beyond the brief" decision log (deliverable)**: wherever we deliberately go beyond or differ from the challenge text, document it as "The brief asked for X; we decided Y because Z" with justification. Lives in `docs/decisions/` (ADR-style, plus a summary section in the README). Known entries so far: (1) list of all matches above threshold with infinite scroll instead of a single most-similar phrase (brief asked for the most similar one; `most_similar` is still returned); (2) monorepo with independently deployable services and modular hexagonal architecture instead of a simple layered app; (3) sentence-transformers now with a planned ONNX/fastembed migration path; (4) Next.js instead of the suggested plain React/Vue; (5) staged validate/re-validate progress UX. Every future deviation MUST add an entry.

- **Exact read on the write path (Option 1; user-confirmed)**: the `SavePhrase` verdict (`is_duplicate`, `score`, `most_similar`) and the metadata recorded on the row MUST NOT depend on the approximate HNSW read. On save they come from an EXACT single-row nearest-neighbour scan (`find_nearest_exact`, same planner settings as `find_matches`, no HNSW), taken inside the save transaction under the advisory lock. HNSW `find_nearest` stays as the fast top-1 for the validate endpoint only (the exact `matches[0]` still wins there). Rationale: correctness of the write path over a small O(n) cost at this scale, consistent with the earlier decision that exact scans are used wherever completeness matters. The scaling path (iterative scan or an exact-verified candidate window) is deferred. This removes the former "accepted residual" risk.
- **UI language**: Spanish (explicit user request; neutral/professional Spanish, no regional slang). Code, identifiers, comments, tests, API field names and technical docs stay in English. API error messages intended for display should be code-based so the UI owns the Spanish copy.
- **List UI**: saved phrases list shows a status badge (e.g. "Duplicado confirmado") and optionally the score, as visible evidence that validation metadata is persisted.

## Ready for Proposal
Yes (remaining open: threshold/max length defaults are working values pending calibration; the HF API adapter question is closed: dropped).
