# Sprint Archive: sprint-01-foundation

- Sprint: `sprint-01-foundation`
- Status: completed
- Goal: establish the first runnable Foreman backend foundation while keeping
  the repo autonomous-agent-ready from day one
- Primary references:
  - `docs/specs/engine-design-v3.md`
  - `docs/mockups/foreman-mockup-v6.html`

## Final task statuses

1. `[done]` Repurpose the transplanted repo scaffold for Foreman
   Deliverable: Foreman-specific docs, aligned wrapper scripts, working repo
   validation, and a concrete sprint and backlog state.

2. `[done]` Bootstrap the Python package and CLI shell
   Deliverable: `pyproject.toml`, `foreman/` package, CLI entrypoint, and smoke
   tests for `foreman --help`, `foreman projects`, and `foreman status`.

3. `[done]` Implement the SQLite model and store baseline
   Deliverable: typed project, sprint, task, run, and event models, DDL
   bootstrap, and round-trip tests for core persistence.

4. `[done]` Load declarative roles and workflows from disk
   Deliverable: TOML loaders for `roles/` and `workflows/`, plus tests for
   parsing, prompt rendering, and transition validation.

## Deliverables

- Foreman-specific repo memory and wrapper alignment
- a runnable `foreman` package and CLI command shell
- SQLite-backed persistence for projects, sprints, tasks, runs, and events
- shipped declarative role and workflow definitions with loader validation
- CLI inspection of shipped roles and workflows

## Demo notes

- `./venv/bin/python scripts/validate_repo_memory.py`
- `./venv/bin/foreman projects --db <path>`
- `./venv/bin/foreman status --db <path>`
- `./venv/bin/foreman roles`
- `./venv/bin/foreman workflows`

## Follow-ups moved forward

- `sprint-02-orchestrator`: implement the orchestrator main loop and standard
  workflow built-ins
- backlog: repo scaffold generation, context projection, native runners,
  human-gate commands, monitoring CLI, and dashboard implementation
