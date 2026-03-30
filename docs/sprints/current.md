# Current Sprint

- Sprint: `sprint-01-foundation`
- Status: active
- Goal: establish the first runnable Foreman backend foundation while keeping
  the repo autonomous-agent-ready from day one
- Primary references:
  - `docs/specs/engine-design-v3.md`
  - `docs/mockups/foreman-mockup-v6.html`

## Included tasks

1. `[done]` Repurpose the transplanted repo scaffold for Foreman
   Deliverable: Foreman-specific docs, aligned wrapper scripts, working repo
   validation, and a concrete sprint and backlog state.

2. `[done]` Bootstrap the Python package and CLI shell
   Deliverable: `pyproject.toml`, `foreman/` package, CLI entrypoint, and smoke
   tests for `foreman --help`, `foreman projects`, and `foreman status`.

3. `[todo]` Implement the SQLite model and store baseline
   Deliverable: typed project, sprint, task, run, and event models, DDL
   bootstrap, and round-trip tests for core persistence.

4. `[todo]` Load declarative roles and workflows from disk
   Deliverable: TOML loaders for `roles/` and `workflows/`, plus tests for
   parsing, prompt rendering, and transition validation.

## Excluded from this sprint

- full web dashboard implementation
- native runner integrations beyond bootstrap supervisor alignment
- cost analytics and advanced event querying

## Acceptance criteria

- the repo has a runnable `foreman` package skeleton
- core SQLite state can be created and queried locally
- roles and workflows can be loaded from TOML
- docs and validation remain good enough for a fresh autonomous agent to pick
  the next slice without extra human context

## Known risks

- the bootstrap wrapper scripts may diverge from the eventual native runner
  design if left unchecked
- package layout decisions made too early could make later CLI or API splitting
  harder

## Demo checklist

- show the repo validation passing
- show the CLI entrypoint responding
- show a test proving the SQLite bootstrap path works
