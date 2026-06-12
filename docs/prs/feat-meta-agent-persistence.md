# PR Summary: feat/meta-agent-persistence

## Summary

Sprint 49 (review Phase 2 — manager hardening): the meta-agent chat panel
becomes a durable, store-backed planning partner. Sessions and turns now
persist in SQLite so chat history and Claude Code session resumption survive
dashboard restarts, every turn rebuilds a compact authoritative world-state
header, and a first-turn operating contract enumerates exactly what the manager
may do through the `foreman` CLI. The `foreman task add` command grows the
flags the contract promises so the manager's promotion/assignment surface is
honest.

## Scope

- migration 11: `meta_sessions` and `meta_turns` tables
- store methods for meta session/turn persistence with cursor paging
- store-backed rewrite of `foreman/meta_agent.py` (dropped the in-memory
  `_sessions` registry)
- `build_state_header()` compact world snapshot, regenerated every turn
- `build_operating_contract()` injected on the first turn of a session
- crash-safe assistant-turn persistence (written in `finally`, flagged
  `interrupted` on error/cancel)
- configurable manager model via `meta_agent_model` project setting
- dashboard `meta/history` endpoint gains `limit`/`before`/`has_more` paging
- `foreman task add` gains `--description`, `--sprint`, and `--depends-on`

## Files changed

- `foreman/migrations.py`
- `foreman/store.py`
- `foreman/meta_agent.py`
- `foreman/dashboard_backend.py`
- `foreman/cli.py`
- `tests/test_migrations.py`
- `tests/test_meta_agent.py` (new)
- `tests/test_cli.py`
- `tests/test_dashboard.py`
- `docs/STATUS.md`, `docs/sprints/current.md`, `docs/sprints/backlog.md`,
  `CHANGELOG.md`

## Migrations

- migration 11 — `meta_sessions`, `meta_turns`, `idx_meta_turns_project`.
  Additive, idempotent; applies cleanly on fresh and existing DBs (covered by
  `tests/test_migrations.py`).

## Risks

- Meta-agent assistant turns are persisted in a `finally` path; a hard process
  kill between the user-turn write and the finally could still drop the
  assistant turn, but normal errors, cancellation, and client disconnect are
  covered.
- The frontend meta panel renders the persisted `{"interrupted": true}` marker
  as a nameless tool chip; cosmetic only and left untouched to keep the
  committed dist in sync (no rebuild in this slice).

## Tests

- `./venv/bin/python -m unittest tests.test_meta_agent -v` (7 new)
- `./venv/bin/python -m unittest tests.test_migrations -v`
- `./venv/bin/python -m unittest tests.test_cli.ForemanCLISmokeTests.test_task_add_targets_explicit_sprint_with_description_and_dependencies -v`
- `./venv/bin/python -m unittest tests.test_dashboard.DashboardMetaAgentTests -v`
- `./venv/bin/python -m unittest discover -s tests` — 528 tests passed
- `./venv/bin/python scripts/validate_repo_memory.py`
- `git diff --check`

## Screenshots or output examples

```
$ foreman task add proj --title "Dependent" --criteria linked \
    --description "needs base" --sprint sprint-b --depends-on task-first
Created task
...
Depends on: task-first
Status: todo
```

## Acceptance criteria satisfied

- Migration 11 applies cleanly on fresh and existing DBs.
- Dashboard restart preserves chat history and session id (persisted in SQLite,
  read back through the FastAPI history endpoint).
- A scripted meta turn whose fake model output yields tool use persists turns;
  the CLI `task add --sprint --depends-on` path produces a correctly linked
  task.
- `build_state_header` has a unit test pinning the format and the 80-char
  truncation rule.

## Follow-ups

- Phase 3 (sprint 50): per-task executor overrides + escalation ladder; the
  state-header `model_override` column and the contract's `foreman task
  override` line are placeholders until that lands.
- Optionally surface meta history paging (`before`/`has_more`) in the frontend
  panel with a "load older" affordance.
