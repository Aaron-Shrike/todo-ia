# Apply Progress: Saved-Phrase List Filters

Source of truth: `tasks.md` (Units 1-4), `design.md`. This file tracks
apply-phase execution batch by batch.

This copy of the file was authored from Unit 4's branch (`feat/plf-04-decision-log`,
child of tracker `feat/phrase-list-filters`), which branched directly off the
tracker and does not include Unit 1's `apply-progress.md` commit (that commit
lives on the sibling branch `feat/plf-01-backend-filters` and has not been
merged into the tracker as of this session). Per this unit's instructions,
appending a Unit-4-only section here is expected; whoever integrates the
branches should merge this section with Units 1-3's sections rather than
letting one overwrite the other.

## Unit 4: Decision log — ADR-016 — DONE

Branch: `feat/plf-04-decision-log` (child of tracker `feat/phrase-list-filters`, which is off `develop`), branched directly off the tracker (Unit 4 is independent of Units 1-3).
Commit: `a60d73f` — `docs(decisions): add ADR-016 list filters, decision log now six entries`.

### Files changed

| File | Action | What was done |
|---|---|---|
| `docs/decisions/ADR-016-list-filters.md` | Created | `type: beyond-brief` front matter; states the brief (and the pre-existing `phrase-management` "List phrases" requirement) called filtering out of scope, the decision to add `status`/`q`/`min_score` to `GET /phrases`, the rationale (support-conversation-driven need, ADR-005 cited as the established beyond-brief-additive-UX precedent), and the deferred `pg_trgm` trigger conditions (~100k rows or filtered p95 > 100ms) per `proposal.md`. |
| `services/api/tests/unit/test_decision_log.py` | Modified | Renamed `test_exactly_five_beyond_brief_adrs_at_top_level` to `test_exactly_six_beyond_brief_adrs_at_top_level`; expected count 5 -> 6; assertion message now names `ADR-001..005, ADR-016`. |
| `README.md` | Modified | "Decisions beyond the brief" section: "Five decisions" -> "Six decisions"; added an `ADR-016` row to the table; "not counted among the five above" -> "not counted among the six above". |
| `docs/decisions/technical/` count line | Not modified | Task 4.3's scope note only touched the top-level five/six count line the technical count line references; the technical-ADR count itself (ten) is unchanged by this unit. |
| `docs/architecture.md` | Modified | Monorepo-layout code comment: `# exactly five beyond-brief ADRs (ADR-001..005)` -> `# exactly six beyond-brief ADRs (ADR-001..005, ADR-016)`. Found via this task's required sweep for stale ADR-count mentions across top-level docs (not itself an assigned tasks.md line item, but within the letter of task 4.3). |
| `openspec/changes/phrase-list-filters/tasks.md` | Modified | Marked 4.1-4.3 `[x]`. |

### Deliberately NOT modified (out of Unit 4's scope, confirmed by sweep)

- `openspec/specs/phrase-management/spec.md` — still says "exactly five" / lists topics (1)-(5). This is the pre-change deployed spec; the delta at `openspec/changes/phrase-list-filters/specs/phrase-management/spec.md` already carries the six-entry MODIFIED requirement, and the top-level `specs/` copy is expected to be updated by `sdd-archive` when this change is archived, not by `sdd-apply`. Left untouched.
- `docs/decisions/technical/ADR-011-embedding-cache.md` — its classification note references "the exactly five requirement" as *historical* rationale for why the embedding cache was filed as `technical` rather than `beyond-brief` at the time it was written. That number is now stale prose (five -> six happened for an unrelated later reason), but it is inside another unit's already-shipped ADR content, not a live doc/count in the sense task 4.3 asked to sweep. Flagged here rather than edited.

### TDD Cycle Evidence

| Task | RED | GREEN | REFACTOR | Notes |
|---|---|---|---|---|
| 4.1 `ADR-016-list-filters.md` | N/A (doc creation; RED is expressed through 4.2's test) | N/A | — | Doc content authored per `proposal.md`'s Approach/ADR-016 guidance and the delta spec's "ADR-016 documents the reversal and the deferred index" scenario. |
| 4.2 decision-log test rename/count | Confirmed: ran `pytest tests/unit/test_decision_log.py -q` BEFORE creating ADR-016 -> 4 passed (baseline, 5 ADRs). After creating `ADR-016-list-filters.md` (task 4.1) but BEFORE touching the test -> reran -> `test_exactly_five_beyond_brief_adrs_at_top_level` FAILED (`assert 6 == 5`) and `test_readme_links_every_adr` FAILED (README didn't mention `ADR-016-list-filters.md` yet); 2 failed, 2 passed. | Renamed the test to `test_exactly_six_beyond_brief_adrs_at_top_level`, updated count/message, updated README (task 4.3) -> reran -> 4 passed. | ruff/mypy not re-run (docs+test-assertion-only change, no source under `services/api/src/app/` touched) | Real pytest RED->GREEN, executed in-session, exactly as tasks.md's "Strict TDD" preamble requires. |
| 4.3 README + architecture.md sweep | Implicit RED: `test_readme_links_every_adr` (see above) failed until README was updated | Confirmed GREEN in the same rerun as 4.2 above | — | `docs/architecture.md` has no dedicated test coverage; verified by `rg` sweep for "five"/ADR-count mentions across top-level docs (see below). |

### Full verification run

- `cd services/api && .venv/bin/python -m pytest tests/unit/test_decision_log.py -q` -> `4 passed` (run twice: once immediately after the GREEN edits, once again later in the session to reconfirm after an unrelated environment disruption — see Environment note below).
- `cd services/api && .venv/bin/python -m pytest -m "not integration and not slow" -q` -> `303 passed, 56 deselected` (run once, cleanly, before a concurrent agent's uncommitted work appeared in the shared working directory — see Environment note).
- Doc sweep for stale ADR-count mentions: `rg -ni "five.{0,20}(beyond|adr)|beyond.{0,20}five|exactly five"` across `*.md`/`*.py`, excluding `openspec/changes/**`. Hits: `docs/architecture.md` (fixed, this unit), `docs/decisions/technical/ADR-011-embedding-cache.md` (historical, left as-is, see above), `openspec/specs/phrase-management/spec.md` (pre-change deployed spec, left for `sdd-archive`, see above). `openspec/project.md` had no hits.

### Environment note — shared working directory across concurrent Unit agents (IMPORTANT)

This repo has **one working directory, not per-unit git worktrees**. Mid-session,
another agent's `git checkout` (observed switching HEAD to `feat/plf-03-frontend-filters`,
and at another point uncommitted edits to `services/api/src/app/modules/phrases/api/schemas.py`
and `tests/unit/phrases/test_schemas.py` appeared — apparently Unit 2's live WIP)
silently changed this branch's checked-out working-tree contents out from under
this session, without this session running any command that should have done so.
Because git carries uncommitted tracked-file changes across `checkout` when they
don't conflict with the target branch, this repeatedly moved other units' in-progress,
sometimes RED-state (mid-TDD, failing) uncommitted changes onto/off of this branch's
working tree as HEAD moved. No foreign file was ever staged or committed by this
session — `git status`/`git diff --stat` were checked before every `git add`, and
`git add` was always called with explicit paths, never `-A`/`.`. Unit 4's commit
(`a60d73f`) is confirmed to contain exactly its own 4 intended files (`git show --stat`).
**Recommendation for the orchestrator**: run concurrent apply-phase agents in isolated
`git worktree`s (one per unit branch) instead of one shared working directory, or
serialize apply phases that would otherwise run concurrently in the same directory.
