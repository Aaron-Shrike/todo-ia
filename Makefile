.PHONY: up test test-unit test-slow evidence types lint seed

# Bring up the full stack (db, migrate, api, web). Compose wiring lands in Unit 4/14.
up:
	docker compose up -d --build

# Full suite: backend unit + integration + contract, and frontend unit.
# Requires `db` (docker compose) to be up for the `integration` marker once Unit 4 lands.
test:
	cd services/api && .venv/bin/python -m pytest -q
	cd apps/web && npm test

# Fast local/CI loop: backend unit-only (excludes `integration` and `slow`), frontend unit.
# This is the command wired into openspec/config.yaml apply/verify test_command (task 0.5).
test-unit:
	cd services/api && .venv/bin/python -m pytest -m "not integration and not slow" -q
	cd apps/web && npm test

# Real-model tests (marker `slow`); requires the sentence-transformers weights (Unit 8+).
test-slow:
	cd services/api && .venv/bin/python -m pytest -m slow -q

# Regenerates docs/evidence/calibration.md from the ES/EN fixture (Unit 9+).
evidence:
	cd services/api && .venv/bin/python -m pytest tests/slow/test_calibration.py -q

# Regenerates apps/web/src/types/api.ts from docs/openapi.json (Unit 10+).
#
# Runs openapi-typescript through an ISOLATED `npx --package` install (its own
# typescript@5.6.3, resolved only inside that temp install) instead of
# `apps/web`'s own toolchain. Verified in Unit 10: openapi-typescript's
# codegen imports the classic `ts.factory` Compiler API, which typescript@7's
# npm package (pinned in apps/web for tsc/vitest since Unit 0) does NOT
# export any more — `require('typescript')` there resolves to
# `./lib/version.cjs`, exposing only `{version, versionMajorMinor}` — so
# running it against the workspace's own typescript@7 crashes with
# `TypeError: Cannot read properties of undefined (reading
# 'createKeywordTypeNode')`. No override/alias in apps/web/package.json can
# fix this because it is not a version-range mismatch, it is a removed API
# surface; isolating the two toolchains is the actual fix. See
# apply-progress.md's Unit 10 section for the full investigation.
types:
	npx --yes --package=typescript@5.6.3 --package=openapi-typescript@7.13.0 \
		openapi-typescript docs/openapi.json -o apps/web/src/types/api.ts

# Seeds the `phrases` table with generated Peruvian-themed phrases, straight
# into Postgres (bypasses the app's per-request duplicate-detection path for
# throughput — see scripts/seed_phrases.py's module docstring). Requires the
# `api` container up (has the real embedding model baked in) and `faker`
# installed there (`docker compose exec api pip install faker`, once per
# container lifetime — not baked into the image, see pyproject.toml's `seed`
# extra). Usage: `make seed N=1000`.
seed:
	docker compose exec api python scripts/seed_phrases.py --count $(N)

# Static checks: ruff, mypy, import-linter boundary contracts.
lint:
	cd services/api && .venv/bin/ruff check src tests
	cd services/api && .venv/bin/mypy src
	cd services/api && .venv/bin/lint-imports
