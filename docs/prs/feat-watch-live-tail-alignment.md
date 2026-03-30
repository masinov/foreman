# PR Summary: feat-watch-live-tail-alignment

## Summary

- replace bounded `foreman watch` snapshots with a live incremental tail
- make project, sprint, and run watch scopes explicit
- roll repo memory forward from watch alignment to migration bootstrap

## Scope

- add incremental cursor-based event reads for generic store queries
- rework `foreman watch` around recent activity plus live updates
- add explicit sprint watch support and idle-timeout driven exit behavior
- add CLI and store coverage for incremental watch delivery
- archive sprint 19 and define sprint 20

## Files changed

- `foreman/cli.py` — replaced snapshot-based watch output with a live tail
  model and added explicit sprint scope support
- `foreman/store.py` — added generic incremental event reads after one known
  cursor event
- `tests/test_cli.py` — added live watch coverage for project, sprint, run,
  and incremental post-start activity
- `tests/test_store.py` — added store coverage for generic incremental event
  reads
- `README.md`, `docs/STATUS.md`, `docs/sprints/current.md`,
  `docs/sprints/backlog.md`, `docs/ARCHITECTURE.md`, `docs/ROADMAP.md`,
  `docs/TESTING.md`, `docs/RELEASES.md`, `CHANGELOG.md` — aligned repo memory
  to the completed slice
- `docs/sprints/archive/sprint-19-watch-live-tail-alignment.md` — archived
  the completed sprint
- `docs/prs/feat-watch-live-tail-alignment.md` — branch summary

## Migrations

- none

## Risks

- project-scoped watch resolves the active sprint once at startup and does not
  auto-rebind if sprint ownership changes mid-session
- the CLI now shares the dashboard's persisted-event cursor boundary, but it
  still tails activity through direct store reads rather than the HTTP SSE
  transport
- the SQLite layer still lacks a formal migration framework, which is now the
  next slice

## Tests

- `./venv/bin/python -m py_compile foreman/cli.py foreman/store.py tests/test_cli.py tests/test_store.py`
- `./venv/bin/python -m unittest tests.test_store.ForemanStoreTests.test_list_events_can_resume_incrementally_after_one_known_event tests.test_cli.ForemanCLISmokeTests.test_watch_command_tails_project_activity_without_mutating_state tests.test_cli.ForemanCLISmokeTests.test_watch_command_can_scope_to_one_run tests.test_cli.ForemanCLISmokeTests.test_watch_command_can_scope_to_one_sprint tests.test_cli.ForemanCLISmokeTests.test_watch_command_streams_new_project_activity_until_idle_timeout -v`
- `./venv/bin/python -m unittest discover -s tests -v`
- `./venv/bin/python scripts/validate_repo_memory.py`

## Screenshots or output examples

- `foreman watch <project-id>` now prints recent persisted activity and then
  appends new event lines as they are written

## Acceptance criteria satisfied

- `foreman watch` no longer depends on bounded snapshot rendering for its core
  live-tail path
- automated tests cover the aligned watch behavior at the CLI and store
  boundary
- docs explain how CLI watch behavior relates to the dashboard stream

## Follow-ups

- implement `sprint-20-migration-framework-bootstrap`
- decide whether project-scoped watch should auto-rebind when the active
  sprint changes mid-session
