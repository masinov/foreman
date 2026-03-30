# PR Summary: feat/dashboard-shell

## Summary
- land the first web dashboard shell for SQLite-backed project overview, sprint board, and activity feed
- HTML UI matches mockup styling and CSS classes
- JSON API endpoints backed by existing store read models

## Scope
- new dashboard module at HTTP server with HTML + JSON API
- new `foreman dashboard` CLI command
- tests for the dashboard module
- update sprint task status

## Files changed
- `foreman/dashboard.py` — new HTTP server with embedded HTML and JSON API endpoints
- `foreman/cli.py` — added `dashboard` command with `--db`, `--host`, `--port` options
- `tests/test_dashboard.py` — 6 tests for project status, API endpoints, HTML content
- `docs/sprints/current.md` — updated task status for dashboard sprint
- `docs/STATUS.md` — updated active branch, current state
- `docs/STATUS.md` — added dashboard implementation to completed list
- `docs/checkpoints/dashboard-slice.md` — new checkpoint file

## Migrations
- none

## risks
- the dashboard uses polling for data rather than streaming (documented in STATUS.md)
- approve/deny buttons in blocked task cards are placeholders (they POST to endpoints but don action on the orchestrator)
- the HTTP server runs in-process and Python's stdlib `http.server` module

## tests
- `./venv/bin/python -m unittest tests.test_dashboard -v`
- 6 tests added, 6 tests pass

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
- [x] tests pass

## follow-ups
- surface task detail and recent activity in dashboard
- define the first dashboard data-access boundary
- implement streaming transport (currently polling)
- implement approve/deny button actions in UI

## PR notes
This is the first slice of the dashboard implementation. It establishes:
- an HTTP server serving HTML + JSON API
- the UI structure matching the mockup
- SQLite-backed data access
- CLI command to start the server
