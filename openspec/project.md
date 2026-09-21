# Project: todo-ia

Initialized: 2026-09-21 | Persistence: openspec | Strict TDD: enabled

## Purpose

Phrase-list web app (todo-list style). Users add short sentences, view saved phrases, and press a validation button before saving. Validation uses AI embeddings to detect semantic (not just exact) duplicates and warns the user, who then confirms or cancels the save.

Source: `docs/Reto-Tecnico-Fullstack-AI.md` (fullstack technical challenge).

## Current State

Greenfield. No application code, manifests, or CI exist. Stack below is INTENDED, not detected.

## Intended Stack

| Layer | Choice |
| --- | --- |
| Frontend | React or Vue (undecided): form, list, validation state, error and confirmation messages |
| Backend | Python + FastAPI REST API with validation and consistent error shape |
| Database | PostgreSQL; script SQL or migrations; stores phrases plus validation metadata (similarity score, date, status) |
| AI | Hugging Face embedding model (or equivalent); cosine similarity; configurable threshold; returns most similar phrase and score |
| Config | Environment variables; Git/GitHub |

## Architecture Requirements

Clean layered separation: UI, business logic, data, AI integration.

## Core Flow

1. User submits a new phrase for validation.
2. Backend embeds new phrase and stored phrases, computes cosine similarity.
3. If best score is at or above the configured threshold, respond with potential duplicate, most similar phrase, and score.
4. Frontend alerts; user confirms or cancels the save.
5. Persist phrase with validation metadata.

## Deliverables

Repo (frontend + backend), SQL script or migrations, README (install, run, env vars), brief architecture and decisions write-up, evidence of Hugging Face integration (code + example of similar phrases).

## Testing Capabilities (planned, not installed)

Strict TDD Mode: enabled (user config). Re-detect after scaffolding.

| Area | Runner | Status |
| --- | --- | --- |
| Backend unit/integration | pytest (+ httpx/TestClient, pytest-cov) | Planned |
| Frontend unit/component | vitest (+ testing-library) | Planned |
| E2E | none | Not planned |
| Linter / types / formatter | ruff, mypy or pyright; eslint, tsc, prettier | Suggested only |

Priority test targets: semantic validation flow and save flow; API contracts, acceptance cases, edge cases (empty phrase, over-length, empty store, threshold boundary, model unavailable).

## Conventions

- Conventional commits, atomic history; no AI attribution in commits.
- Artifacts and code in English.
- Spec-Driven Development: behavior defined before implementation.
- Review budget: 400 changed lines per PR.

## Skills

Registry: `.atl/skill-registry.md`. No project-level skills or convention files (AGENTS.md, etc.) present.
