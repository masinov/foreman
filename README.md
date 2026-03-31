# Foreman

Foreman is an autonomous development engine for turning a project spec into
reviewable implementation work through structured sprints, tasks, runs, and
human gates.

This repository is still the bootstrap memory for that product. The only
authoritative product inputs are:

- `docs/specs/engine-design-v3.md`
- `docs/mockups/foreman-mockup-v6.html`

Everything else in the repo exists to turn those two artifacts into a working
runtime without losing project memory along the way.

Bootstrap here refers to repo-memory scaffolding and incomplete feature
coverage. It does not mean product code may use throwaway architecture.

## Key references

- Agent operating instructions: `AGENTS.md`
- Project status: `docs/STATUS.md`
- Current sprint: `docs/sprints/current.md`
- Backlog: `docs/sprints/backlog.md`
- Architecture baseline: `docs/ARCHITECTURE.md`
- Roadmap: `docs/ROADMAP.md`

## Current state

The integrated pre-release baseline now contains:

- the product spec and UI mockup,
- two supervised autonomous entry points in `scripts/`,
- a runnable `foreman/` package with SQLite-backed models, store, and CLI,
- shipped declarative `roles/*.toml` and `workflows/*.toml` plus loader and
  prompt-rendering support,
- an orchestrator with built-ins for tests, merge, mark-done, human gates, and
  runtime context projection into `.foreman/`,
- repo-local `.foreman.db` discovery for normal CLI usage plus optional `--db`
  override semantics,
- `foreman init` defaulting to `<repo>/.foreman.db` for project scaffold
  generation and persisted project initialization,
- persisted human-gate approval and denial flows with deferred or immediate
  native resume depending on runtime availability,
- native Claude Code and Codex runners with structured event capture, retry
  normalization, explicit startup preflight checks, approval-policy handling,
  and persisted session reuse across fresh orchestrator invocations for
  persistent roles,
- optional startup event-retention pruning when `event_retention_days` is
  configured, while preserving history for blocked and in-progress tasks,
- an opt-in `development_secure` workflow that now runs end to end through
  code review, security review, test, and merge with durable carry-output
  semantics,
- store-backed monitoring commands for `board`, `history`, `cost`, and
  live `watch` across project, sprint, and run scopes,
- accepted ADRs for runner session and backend contract boundaries
  (`ADR-0001`), dashboard data access (`ADR-0002`), and the product web UI
  and API boundary (`ADR-0003`), plus the dashboard backend framework
  (`ADR-0004`),
- an extracted dashboard backend contract in `foreman/dashboard_api.py` for
  project, sprint, task, action, and streaming payloads,
- a FastAPI dashboard backend in `foreman/dashboard_backend.py` served by
  uvicorn,
- a current legacy dashboard shell in `foreman/dashboard.py` with project
  overview, sprint board, task detail, activity feed, human message input,
  activity filtering, project switching, approve or deny actions wired into
  orchestrator resume, and a dedicated sprint event stream for live activity
  updates,
- unit and integration coverage across store, CLI, orchestrator, runners,
  dashboard, and runner-backed executor seams.

The current repo-memory goal is to keep that baseline coherent while moving
into the next implementation gap rather than leaving finished work stranded on
feature branches.

## Implementation standard

Incremental delivery is expected. Throwaway implementation structure is not.

- production-facing code should land behind boundaries that can survive into
  the finished product,
- the mockup defines UI hierarchy and interaction intent, not permission to
  embed the product UI into backend modules,
- the accepted direction for the dashboard is now a dedicated React frontend
  consuming a Python API and streaming boundary,
- known placeholder or stub product surfaces are treated as debt to remove,
  not as acceptable steady-state architecture.

## Workflow selection

Use the default `development` workflow for standard bootstrap project setup.

Use `development_secure` when a project should require a dedicated security
review after code review and before tests and merge.

Example:

```bash
./venv/bin/foreman init /path/to/repo --name "Secure Project" --spec docs/spec.md --workflow development_secure
```

## Native backend preflight

Foreman now validates native backend prerequisites before long-running agent
execution starts.

- Claude Code requires a `claude` executable in `PATH`.
- Codex requires a `codex` executable in `PATH` plus a working app-server
  initialize and thread-start handshake.
- Preflight failures stop before `agent.started`, produce one explicit failed
  run, and do not consume infrastructure retries.

Operator recovery:

1. install or repair the missing backend executable,
2. verify the backend manually from the shell,
3. rerun the blocked task or project once the backend startup path is healthy.

## Event retention

Foreman can now prune old `events` rows on orchestrator startup when a
project sets `event_retention_days`.

- pruning is project-scoped and cutoff-based,
- events for `blocked` and `in_progress` tasks are preserved regardless of
  age,
- pruning emits `engine.event_pruned` when rows are removed,
- `runs` rows are not pruned yet, so event retention is only the first layer
  of history cleanup.

## Live watch

`foreman watch` now tails persisted activity incrementally instead of
rendering repeated snapshots.

- `foreman watch <project-id>` tails the active sprint by default and falls
  back to project-wide events when no sprint is active,
- `foreman watch --sprint <sprint-id>` tails one sprint explicitly,
- `foreman watch --run <run-id>` tails one run explicitly,
- the CLI and dashboard now share the same persisted-event cursor model even
  though the dashboard still delivers it over HTTP server-sent events.

## Dashboard direction

The current inline shell in `foreman/dashboard.py` is now treated as a legacy
delivery path, not the desired product architecture.

The accepted direction is:

- Python backend modules expose JSON and streaming APIs through
  `foreman/dashboard_api.py` and `foreman/dashboard_backend.py`,
- a dedicated React frontend owns product UI rendering and state management,
- mockup alignment remains mandatory for hierarchy and interaction behavior.

## Autonomous entry points

Run all Python commands through the repo virtual environment:

```bash
./venv/bin/python scripts/reviewed_codex.py
./venv/bin/python scripts/reviewed_claude.py
```

What they do:

- `reviewed_codex.py` supervises a Codex development run against the current
  sprint docs and requests reviewer approval before accepting a completed
  slice.
- `reviewed_claude.py` does the same for Claude Code and is designed to keep
  moving through approved work until the backlog is exhausted.

Both wrappers expect these files to be current:

- `AGENTS.md`
- `docs/STATUS.md`
- `docs/sprints/current.md`
- `docs/sprints/backlog.md`
- `docs/specs/engine-design-v3.md`
- `docs/mockups/foreman-mockup-v6.html`

## Next implementation slice

The current sprint is `sprint-23-react-dashboard-foundation`.

The next recommended task is:

- replace the legacy inline dashboard shell with a dedicated React frontend
  that consumes the FastAPI backend and extracted dashboard service layer.

That work is recorded in `docs/sprints/current.md`, so a fresh agent can pick
it up without reconstructing branch history first.

## Validation

Current repo-memory validation:

```bash
./venv/bin/python scripts/validate_repo_memory.py
./venv/bin/python -m py_compile scripts/reviewed_codex.py
./venv/bin/python -m py_compile scripts/reviewed_claude.py
./venv/bin/python -m py_compile scripts/repo_validation.py
./venv/bin/python -m py_compile scripts/validate_repo_memory.py
```

Current code-level validation also includes:

```bash
./venv/bin/pip install -e . --no-build-isolation
./venv/bin/python -m unittest discover -s tests -v
./venv/bin/foreman --help
./venv/bin/foreman projects
./venv/bin/foreman status
./venv/bin/foreman roles
./venv/bin/foreman workflows
./venv/bin/foreman approve --help
./venv/bin/foreman deny --help
./venv/bin/foreman board --help
./venv/bin/foreman history --help
./venv/bin/foreman cost --help
./venv/bin/foreman watch --help
./venv/bin/foreman dashboard --help
```
