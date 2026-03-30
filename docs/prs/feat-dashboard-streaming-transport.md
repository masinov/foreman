# PR Summary: feat-dashboard-streaming-transport

## Summary

- replace polling-only dashboard activity refresh with a dedicated sprint event
  stream
- keep board state and selected task detail current by refreshing on incoming
  streamed activity instead of periodic full snapshot polling
- roll repo memory forward from dashboard streaming transport to engine DB
  discovery

## Scope

- add sprint-scoped event queries to the SQLite store
- add a dashboard server-sent events endpoint for incremental sprint activity
- switch the dashboard client to `EventSource`-driven activity updates and
  debounced task refresh
- move the dashboard server to a threaded HTTP boundary
- archive sprint 14 and define sprint 15

## Files changed

- `foreman/store.py` — added sprint-scoped recent and incremental event
  queries
- `foreman/dashboard.py` — added threaded SSE transport, event serialization,
  and live activity subscription wiring
- `tests/test_store.py` — added sprint event query coverage
- `tests/test_dashboard.py` — added dashboard stream serialization and HTML
  wiring coverage
- `docs/STATUS.md` — updated current sprint and repo state
- `docs/sprints/current.md` — rolled current sprint to engine DB discovery
- `docs/sprints/backlog.md` — reordered next-up backlog
- `docs/sprints/archive/sprint-14-dashboard-streaming-transport.md` —
  archived the completed sprint
- `README.md`, `docs/ROADMAP.md`, `docs/ARCHITECTURE.md`, `docs/TESTING.md`,
  `CHANGELOG.md` — aligned repo memory to the completed slice
- `docs/prs/feat-dashboard-streaming-transport.md` — branch summary

## Migrations

- none

## Risks

- the dashboard stream currently uses polling inside the server-side transport
  loop rather than a dedicated pub-sub layer
- `foreman watch` still renders bounded polling snapshots, so CLI and
  dashboard live semantics are not yet unified
- explicit engine DB discovery is still pending, so dashboard startup and CLI
  flows still require `--db`

## Tests

- `./venv/bin/python -m py_compile foreman/dashboard.py foreman/store.py tests/test_dashboard.py tests/test_store.py`
- `./venv/bin/python -m unittest tests.test_store tests.test_dashboard -v`
- `./venv/bin/python scripts/validate_repo_memory.py`
- `./venv/bin/python -m py_compile scripts/reviewed_codex.py scripts/reviewed_claude.py scripts/repo_validation.py scripts/validate_repo_memory.py`
- `./venv/bin/pip install -e . --no-build-isolation --no-deps`
- `./venv/bin/python -m unittest discover -s tests -v`

## Screenshots or output examples

- n/a

## Acceptance criteria satisfied

- the dashboard receives new persisted events without full-list polling
- activity and task state stay current while the page is open
- the transport boundary is documented clearly enough for the next slice to
  build on it without reverse-engineering the dashboard code

## Follow-ups

- implement `sprint-15-engine-db-discovery`
- decide whether `foreman watch` should converge on the dashboard live
  transport or remain a distinct CLI-tail implementation
