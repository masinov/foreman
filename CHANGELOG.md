# Changelog

All notable changes to this repository should be documented here.

The repo is still pre-implementation, so entries currently track bootstrap and
scaffold changes rather than product releases.

## [Unreleased]

### Added

- Foreman-specific repo instructions in `AGENTS.md`
- active sprint and backlog docs for the first Foreman implementation slice
- repository templates for PR summaries, checkpoints, and sprint archives
- `pyproject.toml` and the initial `foreman/` package scaffold
- a runnable CLI shell covering the spec-aligned command surface
- CLI smoke tests for `foreman --help`, `foreman projects`, and
  `foreman status`
- typed SQLite models and a spec-shaped `foreman.store` persistence layer for
  projects, sprints, tasks, runs, and events
- store round-trip tests in `tests/test_store.py`
- store-backed `foreman projects --db <path>` and `foreman status --db <path>`
  inspection paths
- shipped declarative `roles/*.toml` and `workflows/*.toml` defaults
- TOML-compatible loader modules in `foreman.roles` and `foreman.workflows`
- loader tests in `tests/test_roles.py` and `tests/test_workflows.py`
- CLI inspection commands for `foreman roles` and `foreman workflows`

### Changed

- repurposed the transplanted project-memory docs from Apparatus to Foreman
- aligned the autonomous wrapper scripts and repo validation expectations with
  `docs/specs/engine-design-v3.md` and
  `docs/mockups/foreman-mockup-v6.html`
- reset the roadmap, architecture baseline, and status docs to the actual
  Foreman project
- expanded repo validation to require the package scaffold and CLI smoke test
- enhanced `scripts/reviewed_codex.py` so approved slices no longer stop the
  run immediately; the supervisor now supports explicit full-spec completion,
  post-approval merge finalization, and continuation to the next slice
- shifted the active project-memory slice from the SQLite store baseline to
  role and workflow loading
- completed `sprint-01-foundation`, archived it, and advanced project memory to
  the orchestrator sprint
