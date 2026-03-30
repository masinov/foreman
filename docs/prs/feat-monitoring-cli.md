# PR Summary: feat/monitoring-cli

## Summary

- implement the monitoring CLI surfaces promised by the active sprint:
  `foreman board`, `foreman history`, `foreman cost`, and `foreman watch`
- add store-backed monitoring read models so CLI aggregation logic stays
  consistent and testable
- roll repo memory forward from the monitoring CLI sprint to the runner
  session and backend ADR sprint

## Scope

- CLI handlers, parser wiring, and output formatting for the monitoring
  command set
- store helpers for recent event slices, run totals, per-task rollups, and
  sprint-scoped task counts
- subprocess CLI coverage plus store query coverage for the new monitoring
  reads
- sprint archive, checkpoint, changelog, and roadmap updates

## Files changed

- `foreman/cli.py`
- `foreman/store.py`
- `tests/test_cli.py`
- `tests/test_store.py`
- `README.md`
- `docs/STATUS.md`
- `docs/sprints/current.md`
- `docs/sprints/backlog.md`
- `docs/sprints/archive/sprint-08-monitoring-cli.md`
- `docs/checkpoints/monitoring-cli.md`
- `docs/prs/feat-monitoring-cli.md`
- `docs/ARCHITECTURE.md`
- `docs/ROADMAP.md`
- `docs/TESTING.md`
- `docs/RELEASES.md`
- `CHANGELOG.md`

## Migrations

- none

## Risks

- `foreman watch` currently uses bounded polling snapshots rather than a live
  event stream
- the monitoring commands still require explicit `--db PATH`
- Codex runs may report tokens with `cost_usd=0.0`, so cost views must keep
  showing persisted values instead of inferred pricing

## Tests

- `./venv/bin/python -m py_compile foreman/cli.py foreman/store.py tests/test_cli.py tests/test_store.py`
- `./venv/bin/python -m unittest tests.test_store tests.test_cli -v`
- `./venv/bin/python -m unittest discover -s tests -v`
- `./venv/bin/python scripts/validate_repo_memory.py`

## Screenshots or output examples

- `foreman board --db <path>` now renders the active sprint as terminal
  status columns with token and branch context
- `foreman watch --run <run-id> --db <path>` now renders a bounded recent
  activity slice for a single persisted run

## Acceptance criteria satisfied

- `foreman board` exposes the active sprint task board directly from SQLite
- `foreman history` and `foreman cost` expose recent runs, events, and usage
  summaries without opening the database manually
- `foreman watch` provides a useful polling view of active project activity
- docs and validation are rolled forward to the runner ADR sprint

## Follow-ups

- implement `sprint-09-runner-session-backend-adr`
- build the first dashboard slice aligned to the mockup after the ADR lands
