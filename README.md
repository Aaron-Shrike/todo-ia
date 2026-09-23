# todo-ia

A phrase-list app (like a todo list, but for short sentences) with **AI-backed semantic duplicate
detection**: before a phrase is saved, the API embeds it with a Hugging Face sentence-transformers
model, compares it against every stored phrase by cosine similarity, and asks the user to confirm
if a near-duplicate is found. See `docs/Reto-Tecnico-Fullstack-AI.md` for the original brief and
`docs/architecture.md` for how the system is built.

## Prerequisites

- Docker and Docker Compose (v2, the `docker compose` subcommand — this repo does not use
  `docker-compose` v1 or a `-f` flag; one root `docker-compose.yml` runs the whole stack).
- No local Python/Node toolchain is required to *run* the app — everything runs in containers. A
  local `services/api/.venv` (Python 3.11+) and `apps/web/node_modules` (Node 22) are only needed to
  run the test suites directly on the host (see "Running tests" below).

## Quickstart

```bash
cp .env.example .env   # see "Environment variables" below if .env.example is not present in your
                        # checkout — every variable and its default is documented in the table below,
                        # copied verbatim from this repo's own recorded intended content
docker compose up -d --build
```

`docker compose up` builds and starts four services: `db` (Postgres 16 + pgvector), `migrate`
(runs once, applies the schema, exits 0), `api` (FastAPI, healthcheck-gated), `web` (Next.js,
depends on `api` being healthy). First build downloads and bakes the embedding model into the `api`
image, so the first `up` is slower than subsequent ones (image layers are cached after that).

Bring it down with `docker compose down` (add `-v` to also drop the `pgdata` volume, e.g. before a
clean re-run).

### URLs

| Service | URL |
| --- | --- |
| Web UI | http://localhost:3000 |
| API | http://localhost:8000 |
| API docs (OpenAPI/Swagger) | http://localhost:8000/docs |
| API readiness | http://localhost:8000/health |

## Running tests

All targets are wired through the root `Makefile` and run against `services/api/.venv` /
`apps/web` directly (not inside containers):

| Command | What it runs |
| --- | --- |
| `make test-unit` | Backend unit/contract suite (`pytest -m "not integration and not slow"`) + frontend unit suite (`vitest run`). Fast, no Docker required. This is the command wired into `openspec/config.yaml`'s `apply`/`verify` test commands. |
| `make test` | Full backend suite (unit + integration + contract, no marker filter) + frontend unit suite. The `integration` marker needs `db` up (`docker compose up -d db migrate`). |
| `make test-slow` | Backend tests marked `slow` — real-model runs (real sentence-transformers weights, no fakes) against the ES/EN calibration fixture. |
| `make evidence` | Regenerates `docs/evidence/calibration.md` from the ES/EN fixture, scored against the real model. |

## Seeding data

`services/api/scripts/seed_phrases.py` generates and inserts realistic, Peruvian-themed phrases
(dishes, places, drinks, colloquial dichos, combined via templates with
[Faker](https://faker.readthedocs.io/)) directly into Postgres, embedding them in batches with the
real model. It bypasses the request-time save path on purpose — that path re-scans the whole table
on every insert (by design, see `duplicate-confirmation` spec), which would make seeding thousands
of rows take hours instead of minutes — so every seeded row lands as `validation_status='unique'`
with no recorded neighbour (a legitimate resting state, not a data-model shortcut). Future saves
from the UI still run the app's normal exact-scan duplicate check against this seeded corpus.

```bash
docker compose exec api pip install faker   # once per container lifetime; see pyproject.toml's `seed` extra
make seed N=1000                            # any count; generates + embeds + inserts
make seed N=20000
```

## Environment variables

Every variable below maps 1:1 to the `Settings` class (`services/api/src/app/platform/settings.py`)
and to the Configuration table in `openspec/changes/phrase-validation/design.md`. `.env.example`
lists every row below except the two image-fixed ones (`HF_HUB_OFFLINE`/`TRANSFORMERS_OFFLINE`,
`SENTENCE_TRANSFORMERS_HOME` — baked into the `api` image, never read from `.env`).
`docker-compose.yml` supplies the same defaults via `${VAR:-default}` interpolation, so the stack
runs even before `.env` exists; copying `.env.example` to `.env` only lets you override them.

| Var | Default | Notes / range |
| --- | --- | --- |
| `DATABASE_URL` | *(required)* `postgresql+psycopg://todo_ia:todo_ia@db:5432/todo_ia` | must use the `postgresql+psycopg://` scheme |
| `POSTGRES_USER` | `todo_ia` | consumed by the `db` compose service and its healthcheck |
| `POSTGRES_PASSWORD` | `todo_ia` | consumed by the `db` compose service |
| `POSTGRES_DB` | `todo_ia` | consumed by the `db` compose service |
| `SIMILARITY_THRESHOLD` | `0.80` | float, `0 <= t <= 1`; working default, calibrated in `docs/evidence/calibration.md` |
| `MATCHES_PAGE_SIZE` | `50` | int, 1..200; also the max accepted `limit` on `/phrases/matches` |
| `PHRASE_MAX_LENGTH` | `280` | int, 1..4000; raw pre-normalization cap is `4 × PHRASE_MAX_LENGTH` |
| `PHRASES_LIST_LIMIT` | `200` | int, 1..1000; max `?limit=` a client may request on `GET /phrases` |
| `PHRASES_PAGE_SIZE` | `10` | int, 1..1000; default page size for `GET /phrases` when `?limit=` is omitted |
| `MAX_REQUEST_BYTES` | `1048576` | int >= 4096; request bodies above it are rejected with 413 before parsing |
| `EMBEDDING_PROVIDER` | `sentence_transformers` | the only runtime value; `fake` exists only in the test settings class |
| `EMBEDDING_MODEL` | `sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2` | non-empty |
| `EMBEDDING_MODEL_REVISION` | `e8f8c211226b894fcb81acc59f3b34ba3efd5f42` | 40 hex characters (Hub commit SHA); also a Docker build arg baked into the image |
| `EMBEDDING_DIMENSIONS` | `384` | must equal the provider dimension **and** the `vector(n)` column typmod (checked at boot) |
| `EMBEDDING_TIMEOUT_SECONDS` | `10.0` | float > 0 |
| `EMBEDDING_MAX_CONCURRENCY` | `2` | int >= 1; executor size and semaphore of `BoundedEmbeddingProvider` |
| `EMBEDDING_CACHE_SIZE` | `512` | int >= 0; `0` disables the embedding cache |
| `HNSW_EF_SEARCH` | `200` | int, 1..1000; applies only to the validate endpoint's `find_nearest` |
| `LOCK_TIMEOUT_MS` | `5000` | int >= 1; bounds the wait for the save advisory lock |
| `CORS_ORIGINS` | `http://localhost:3000` | comma-separated absolute origins, no wildcard |
| `LOG_LEVEL` | `INFO` | enum |
| `NEXT_PUBLIC_API_URL` | `http://localhost:8000` | browser-facing, **build arg** for `web` |
| `NEXT_PUBLIC_PHRASE_MAX_LENGTH` | `280` | **build arg**; kept equal to `PHRASE_MAX_LENGTH` |
| `API_INTERNAL_URL` | `http://api:8000` | server-side fetch (Server Components) only, resolves inside the compose network |

Two variables are fixed in the `api` image and are **not** read from `.env`:
`HF_HUB_OFFLINE`/`TRANSFORMERS_OFFLINE` (`1`, runtime never downloads) and
`SENTENCE_TRANSFORMERS_HOME` (`/opt/models`, the bake target).

## Architecture

`docs/architecture.md` covers the monorepo layout, the hexagonal module structure and its
import-linter-enforced boundaries, the embedding microservice extraction seam (and its honest
limit), the three similarity read shapes, keyset pagination, the embedding cache invariant, the
save concurrency sequence, and residual risks.

## Decisions beyond the brief

The brief (`docs/Reto-Tecnico-Fullstack-AI.md`) asked for a working validation flow with a clean
layered architecture. Five decisions go beyond that literal ask, each recorded as its own ADR under
`docs/decisions/`:

| ADR | Decision |
| --- | --- |
| [`ADR-001`](docs/decisions/ADR-001-full-match-list.md) | Return the **full ordered match list**, not just the top result — a user confirming a duplicate deserves the whole picture, not a silent top-1 truncation. |
| [`ADR-002`](docs/decisions/ADR-002-modular-monorepo.md) | A **modular monorepo** with enforced import boundaries (import-linter contracts as a build failure), not a folder-layered app — the embedding module can become a microservice by swapping one adapter. |
| [`ADR-003`](docs/decisions/ADR-003-local-embedding-runtime.md) | Run the Hugging Face checkpoint **locally through sentence-transformers**, pinned by Hub commit SHA, with ONNX/fastembed documented as the migration path — reproducible offline, no token required. |
| [`ADR-004`](docs/decisions/ADR-004-nextjs-frontend.md) | **Next.js with TypeScript**, not React or Vue directly — the saved-phrase list gets a real server-rendered first paint via a Server Component, while validation stays a client-side state machine. |
| [`ADR-005`](docs/decisions/ADR-005-staged-progress.md) | **Staged progress labels** ("Validando...", "Revalidando...", "Guardando...") instead of one opaque spinner — every label narrates a request that is genuinely in flight, and none survives past the 201. |

Ten further **technical** ADRs, one level down (`docs/decisions/technical/`, not counted among the
five above), record narrower implementation decisions:

- [`ADR-006`](docs/decisions/technical/ADR-006-partial-unique-index.md) — partial unique index on `normalized_text` for identity integrity.
- [`ADR-007`](docs/decisions/technical/ADR-007-keyset-pagination.md) — keyset (never `OFFSET`) pagination for stable page semantics.
- [`ADR-008`](docs/decisions/technical/ADR-008-hnsw-exact-scan-split.md) — HNSW only for `find_nearest`, exact scans for `find_matches` and the write path.
- [`ADR-009`](docs/decisions/technical/ADR-009-browser-direct-no-bff.md) — browser calls the API directly, no BFF proxy.
- [`ADR-010`](docs/decisions/technical/ADR-010-compose-db-for-integration-tests.md) — compose `db` for integration tests instead of testcontainers.
- [`ADR-011`](docs/decisions/technical/ADR-011-embedding-cache.md) — bounded per-process embedding cache behind the `EmbeddingProvider` port.
- [`ADR-012`](docs/decisions/technical/ADR-012-two-reads-reconciliation.md) — two questions, two reads, one reconciliation rule.
- [`ADR-013`](docs/decisions/technical/ADR-013-rounding-contract.md) — rounding is the contract.
- [`ADR-014`](docs/decisions/technical/ADR-014-bigint-ids-opaque-strings.md) — `BIGINT` ids inside, opaque strings on the wire.
- [`ADR-015`](docs/decisions/technical/ADR-015-unit-of-work-isolation.md) — `UnitOfWork` port with two isolation levels.

## Calibration evidence

`docs/evidence/calibration.md` is the Hugging Face integration evidence deliverable: real scores
from the running `sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2` checkpoint against a
fixture of ES/EN duplicate, distinct and known-weakness (negation, accent-variant) phrase pairs,
regenerated by `make evidence`. It is what the `SIMILARITY_THRESHOLD=0.80` default is calibrated
against.
