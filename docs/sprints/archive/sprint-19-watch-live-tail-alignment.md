# Sprint Archive: sprint-19-watch-live-tail-alignment

- Sprint: `sprint-19-watch-live-tail-alignment`
- Status: completed
- Goal: align `foreman watch` with the dashboard live transport and the
  spec's live-tail intent
- Primary references:
  - `docs/specs/engine-design-v3.md`
  - `docs/STATUS.md`
  - `foreman/cli.py`
  - `foreman/store.py`
  - `tests/test_cli.py`
  - `tests/test_store.py`

## Final task statuses

1. `[done]` Define the live-tail boundary for `foreman watch`
   Deliverable: the CLI now exposes explicit project, sprint, and run tail
   scopes without inheriting dashboard-only UI behavior.

2. `[done]` Replace bounded polling snapshots with incremental updates
   Deliverable: `foreman watch` now prints recent persisted activity and then
   streams new events incrementally instead of rendering repeated snapshots.

3. `[done]` Document watch and dashboard alignment
   Deliverable: repo docs now explain that the CLI and dashboard share the
   same persisted-event cursor model while using different transports.

## Deliverables

- cursor-based incremental event delivery for CLI watch scopes
- explicit `--sprint` watch support plus project and run live tails
- idle-timeout driven watch exits for tests and scripted operator flows
- store support for incremental event reads after one known event
- repo-memory rollover from watch alignment to migration bootstrap

## Demo notes

- `./venv/bin/python -m unittest tests.test_store.ForemanStoreTests.test_list_events_can_resume_incrementally_after_one_known_event tests.test_cli.ForemanCLISmokeTests.test_watch_command_tails_project_activity_without_mutating_state tests.test_cli.ForemanCLISmokeTests.test_watch_command_can_scope_to_one_run tests.test_cli.ForemanCLISmokeTests.test_watch_command_can_scope_to_one_sprint tests.test_cli.ForemanCLISmokeTests.test_watch_command_streams_new_project_activity_until_idle_timeout -v`
- `./venv/bin/python -m unittest discover -s tests -v`
- `./venv/bin/python scripts/validate_repo_memory.py`

## Follow-ups moved forward

- `sprint-20-migration-framework-bootstrap`: introduce an explicit schema
  migration path for future SQLite evolution
- `sprint-21-history-lifecycle-expansion`: extend retention and cleanup
  beyond `events` once migration infrastructure exists
