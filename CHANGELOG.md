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
- the first persisted orchestrator loop in `foreman.orchestrator` plus
  explicit built-in execution seams in `foreman.builtins` and git helpers in
  `foreman.git`
- orchestrator integration coverage in `tests/test_orchestrator.py`
- scaffold generation helpers in `foreman.scaffold` plus the generated
  `templates/agents_md.md.j2` instruction template
- `foreman init --db <path>` for repo scaffold generation and persisted project
  initialization
- scaffold coverage in `tests/test_scaffold.py`
- runtime context projection in `foreman.context` for `.foreman/context.md` and
  `.foreman/status.md`
- context projection coverage in `tests/test_context.py`
- `foreman approve --db <path>` and `foreman deny --db <path>` for persisted
  human-gate decisions
- human-gate resume coverage in `tests/test_orchestrator.py` and
  `tests/test_cli.py`
- the first native Claude runner in `foreman/runner/claude_code.py`
- runner coverage in `tests/test_runner_claude.py`
- the first native Codex runner in `foreman/runner/codex.py`
- runner coverage in `tests/test_runner_codex.py`

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
- expanded the store query helpers with status filters and stable latest-run or
  event ordering for orchestrator reads
- completed `sprint-02-orchestrator`, archived it, and advanced project memory
  to the scaffold sprint
- added repo-path project lookup so re-initializing a repo updates the existing
  project record
- completed `sprint-03-scaffold`, archived it, and advanced project memory to
  the context projection sprint
- wired orchestrator agent steps and `_builtin:context_write` to share the same
  runtime context projection path
- completed `sprint-04-context-projection`, archived it, and advanced project
  memory to the human-gate sprint
- taught the orchestrator to resume from persisted human-gate workflow state
  and to defer agent-backed next steps until a native runner is available
- completed `sprint-05-human-gates`, archived it, and advanced project memory
  to the Claude runner sprint
- taught the orchestrator to execute shipped Claude-backed roles through the
  native runner path with retry normalization and session reuse
- completed `sprint-06-claude-runner`, archived it, and advanced project
  memory to the Codex runner sprint
- taught the orchestrator to execute Codex-backed roles through the native
  runner path and to resume human-gate approvals immediately when the native
  backend and repo are available
- completed `sprint-07-codex-runner`, archived it, and advanced project
  memory to the monitoring CLI sprint
