# PR Summary: feat-persistent-session-reload

## Summary

- reload the latest compatible persisted native runner session from SQLite on
  fresh orchestrator invocations
- preserve role-level session policy so only persistent roles resume prior
  sessions
- roll repo memory forward from sprint 13 to the dashboard live transport
  sprint

## Scope

- add a store query for scoped session lookup
- teach the orchestrator-native runner path to restore persisted sessions by
  `task + role + backend`
- add regression coverage for Claude Code, Codex, and non-persistent reviewer
  behavior
- archive sprint 13 and define sprint 14

## Files changed

- `foreman/store.py` — added latest persisted session lookup by task, role,
  and backend scope
- `foreman/orchestrator.py` — seeded native runner config from persisted
  session state on fresh process starts for persistent roles
- `tests/test_store.py` — added session-scope lookup coverage
- `tests/test_orchestrator.py` — added fresh-process session reuse regression
  coverage for Claude Code, Codex, and non-persistent reviewer roles
- `docs/STATUS.md` — updated current sprint and repo state
- `docs/sprints/current.md` — rolled current sprint to dashboard live
  transport
- `docs/sprints/backlog.md` — reordered next-up backlog
- `docs/sprints/archive/sprint-13-persistent-session-reload.md` — archived the
  completed sprint
- `README.md`, `docs/ROADMAP.md`, `docs/ARCHITECTURE.md`, `docs/TESTING.md`,
  `CHANGELOG.md` — aligned repo memory to the completed slice
- `docs/prs/feat-persistent-session-reload.md` — branch summary

## Migrations

- none

## Risks

- session reuse remains keyed only by persisted `task + role + backend`; engine
  instance discovery and runner health checks are still separate gaps
- dashboard live transport is still unimplemented, so UI freshness still
  depends on bounded polling

## Tests

- `./venv/bin/python -m py_compile foreman/store.py foreman/orchestrator.py tests/test_store.py tests/test_orchestrator.py`
- `./venv/bin/python -m unittest tests.test_store tests.test_orchestrator -v`
- `./venv/bin/python scripts/validate_repo_memory.py`
- `./venv/bin/python -m py_compile scripts/reviewed_codex.py scripts/reviewed_claude.py scripts/repo_validation.py scripts/validate_repo_memory.py`
- `./venv/bin/pip install -e . --no-build-isolation --no-deps`
- `./venv/bin/python -m unittest discover -s tests -v`

## Screenshots or output examples

- n/a

## Acceptance criteria satisfied

- a fresh orchestrator invocation reuses the last compatible native session for
  persistent roles
- roles with `session_persistence = false` still start fresh sessions
- Claude Code and Codex both have automated coverage for the new behavior

## Follow-ups

- implement `sprint-14-dashboard-streaming-transport`
- remove the bootstrap requirement for explicit `--db` paths in normal CLI
  flows
