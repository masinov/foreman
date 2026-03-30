# Changelog

All notable changes to this repository should be documented here.

The repo is still pre-release, so entries currently track milestone and repo
memory changes rather than versioned product releases.

## [Unreleased]

### Added

- Foreman-specific repo instructions in `AGENTS.md`
- active sprint and backlog docs for the first Foreman implementation slice
- repository templates for PR summaries, checkpoints, and sprint archives
- `pyproject.toml` and the initial `foreman/` package scaffold
- a runnable CLI shell covering the spec-aligned command surface
- typed SQLite models and a spec-shaped `foreman.store` persistence layer for
  projects, sprints, tasks, runs, and events
- shipped declarative `roles/*.toml` and `workflows/*.toml` defaults
- a persisted orchestrator loop plus explicit built-in execution seams
- repo-local `.foreman.db` discovery with explicit `--db` override support
- `foreman init` defaulting to `<repo>/.foreman.db` for repo scaffold
  generation and persisted project initialization
- runtime context projection in `.foreman/context.md` and `.foreman/status.md`
- persisted human-gate approve and deny commands
- native Claude Code and Codex runners in `foreman/runner/`
- store-backed monitoring commands in `foreman.cli` for `board`, `history`,
  `cost`, and `watch`
- `docs/adr/ADR-0001-runner-session-backend-contract.md`
- `docs/adr/ADR-0002-dashboard-data-access-boundary.md`
- `foreman/dashboard.py` with dashboard HTML shell and direct JSON endpoints
- dashboard task detail, activity feed, human message input, activity filter,
  project switcher, and approve or deny actions
- a dedicated dashboard sprint event stream for incremental live activity
  updates
- `foreman/executor.py` and `tests/test_executor.py`
- end-to-end runtime coverage for the opt-in `development_secure` workflow
  plus secure workflow initialization coverage in the CLI
- explicit native backend preflight validation for Claude Code and Codex
- spec-aligned event-retention pruning for old project events

### Changed

- repurposed the transplanted project-memory docs from Apparatus to Foreman
- aligned the autonomous wrapper scripts and repo validation expectations with
  `docs/specs/engine-design-v3.md` and
  `docs/mockups/foreman-mockup-v6.html`
- completed `sprint-01-foundation`, `sprint-02-orchestrator`,
  `sprint-03-scaffold`, and `sprint-04-context-projection`
- completed `sprint-05-human-gates`, `sprint-06-claude-runner`, and
  `sprint-07-codex-runner`
- completed `sprint-08-monitoring-cli`, archived it, and advanced project
  memory to the runner session and backend ADR sprint
- completed `sprint-09-runner-session-backend-adr`, archived it, and advanced
  project memory to the dashboard implementation sprint
- completed `sprint-10-dashboard-implementation`, archived it, and advanced
  project memory to the multi-project dashboard polish sprint
- completed `sprint-11-multi-project-dashboard-polish`, archived it, and
  advanced project memory to the dashboard approve or deny integration sprint
- completed `sprint-12-dashboard-approve-deny-integration`, archived it, and
  advanced project memory to the persistent-session reload sprint
- completed `sprint-13-persistent-session-reload`, archived it, and advanced
  project memory to the dashboard streaming transport sprint
- completed `sprint-14-dashboard-streaming-transport`, archived it, and
  advanced project memory to the engine DB discovery sprint
- completed `sprint-15-engine-db-discovery`, archived it, and advanced project
  memory to the security review workflow sprint
- completed `sprint-16-security-review-workflow`, archived it, and advanced
  project memory to the native backend preflight sprint
- completed `sprint-17-native-backend-preflight-checks`, archived it, and
  advanced project memory to the event-retention pruning sprint
- completed `sprint-18-event-retention-pruning`, archived it, and advanced
  project memory to the watch live-tail alignment sprint
- reconciled the loose feature and recovery branches into an integrated
  mainline candidate and restored missing repo-memory artifacts from the
  runner-session ADR branch
