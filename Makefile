.PHONY: up test test-unit test-slow evidence types lint

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
types:
	cd apps/web && npx openapi-typescript ../../docs/openapi.json -o src/types/api.ts

# Static checks: ruff, mypy, import-linter boundary contracts.
lint:
	cd services/api && .venv/bin/ruff check src tests
	cd services/api && .venv/bin/mypy src
	cd services/api && .venv/bin/lint-imports
