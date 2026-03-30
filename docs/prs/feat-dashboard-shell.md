# PR Summary: feat/dashboard-shell

## Summary
- land the first web dashboard shell for SQLite-backed project overview, sprint board, and activity feed
- HTML UI matches mockup styling and CSS classes
- JSON API endpoints backed by existing store read models
- Task detail panel with run history and acceptance criteria

## Scope
- new dashboard module at HTTP server with HTML + JSON API
- new `foreman dashboard` CLI command
- task detail overlay panel
- tests for the dashboard module
- update sprint task status

## Files changed
- `foreman/dashboard.py` — new HTTP server with embedded HTML and JSON API endpoints, task detail panel
- `foreman/cli.py` — added `dashboard` command with `--db`, `--host`, `--port` options
- `tests/test_dashboard.py` — 8 tests for project status, API endpoints, HTML content, task detail
- `docs/sprints/current.md` — updated task status for dashboard sprint
- `docs/STATUS.md` — updated active branch, current state
- `docs/checkpoints/dashboard-slice.md` — new checkpoint file
- `docs/adr/ADR-0002-dashboard-data-access-boundary.md` — documents direct store access pattern

## Review history
- Initial submission: missing dashboard_parser in build_parser()
- Fix: added dashboard_parser with --db, --host, --port options to build_parser()

## Migrations
- none

## risks
- the dashboard uses polling for data rather than streaming (documented in STATUS.md)
- approve/deny buttons in blocked task cards are placeholders (they POST to endpoints but don't trigger orchestrator action)
- the HTTP server runs in-process using Python's stdlib `http.server` module

## tests
- `./venv/bin/python -m unittest tests.test_dashboard -v`
- 8 tests added, 8 tests pass

## Output examples
```
$ foreman dashboard --db /path/to/foreman.db
Foreman dashboard running at http://localhost:8080/
Database: /path/to/foreman.db
Press Ctrl+C to stop.
```

## acceptance criteria satisfied
- [x] a user can load a dashboard surface that matches the mockup hierarchy
- [x] dashboard data comes from persisted SQLite state
- [x] `foreman dashboard` command starts the web server
- [x] selecting a task reveals branch, role, status, token, and run history
- [x] tests pass

## follow-ups
- implement streaming transport (currently polling)
- implement approve/deny button actions in UI
- add human message input functionality
- consider read-model projections if dashboard performance degrades

## PR notes
This is the first slice of the dashboard implementation. It establishes:
- an HTTP server serving HTML + JSON API
- the UI structure matching the mockup
- SQLite-backed data access
- CLI command to start the server
- task detail panel with run history
