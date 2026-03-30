# Sprint Archive: sprint-15-engine-db-discovery

- Sprint: `sprint-15-engine-db-discovery`
- Status: completed
- Goal: remove the bootstrap requirement to pass explicit `--db` paths for
  normal SQLite-backed CLI flows
- Primary references:
  - `docs/specs/engine-design-v3.md`
  - `docs/STATUS.md`
  - `foreman/cli.py`
  - `foreman/scaffold.py`
  - `tests/test_cli.py`
  - `tests/test_scaffold.py`

## Final task statuses

1. `[done]` Add engine-level database discovery
   Deliverable: Foreman now resolves a repo-local default SQLite path via a
   hidden `.foreman.db` file instead of requiring `--db` on every command.

2. `[done]` Wire CLI flows to discovery with explicit override semantics
   Deliverable: inspection, monitoring, approve or deny, dashboard startup,
   and project initialization now work without explicit `--db` for normal
   repo-local usage, while `--db PATH` still overrides discovery.

3. `[done]` Document discovery and fallback behavior
   Deliverable: repo docs now describe `.foreman.db` discovery, override
   behavior, and the remaining boundary for cross-repo or out-of-repo
   inspection.

## Deliverables

- repo-local `.foreman.db` default path for bootstrap engine state
- upward discovery from the current working directory to find an existing
  repo-local DB
- `foreman init` defaulting to `<repo>/.foreman.db` when `--db` is omitted
- scaffold `.gitignore` updates that keep `.foreman.db` uncommitted
- CLI coverage for repo-local discovery and explicit override behavior
- repo-memory rollover from engine DB discovery to security review workflow

## Demo notes

- `./venv/bin/python -m unittest tests.test_scaffold tests.test_cli -v`
- `./venv/bin/python -m unittest discover -s tests -v`
- `./venv/bin/python scripts/validate_repo_memory.py`

## Follow-ups moved forward

- `sprint-16-security-review-workflow`: make the shipped secure workflow
  variant execute end to end with orchestrator and CLI coverage
- `sprint-17-native-backend-preflight-checks`: validate backend availability
  before long-running native execution
- `sprint-18-event-retention-pruning`: implement spec-aligned pruning for old
  event rows
