# Backlog

## Next up after the current sprint

### `todo` Context projection

- Write `.foreman/context.md` and `.foreman/status.md` before runs.
- Visible deliverable: task and sprint state is projected from SQLite into the
  gitignored runtime context path.

### `todo` Native Claude Code runner

- Implement the runner interface, session handling, event capture, and retry
  behavior for Claude Code.
- Visible deliverable: a persisted run with structured events from one Claude
  task execution.

### `todo` Native Codex runner

- Implement the runner interface, session handling, event capture, and retry
  behavior for Codex.
- Visible deliverable: a persisted run with structured events from one Codex
  task execution.

### `todo` Human gate commands

- Implement `foreman approve` and `foreman deny` with persisted pause or resume
  behavior.
- Visible deliverable: a paused workflow can resume from a human decision.

### `todo` Monitoring CLI

- Add `foreman board`, `foreman watch`, `foreman history`, and `foreman cost`.
- Visible deliverable: operators can inspect project state without opening the
  database manually.

### `todo` Dashboard implementation

- Build the project, sprint, and task views defined in
  `docs/mockups/foreman-mockup-v6.html`.
- Visible deliverable: interactive UI for project overview, sprint board, and
  live activity feed.

## Parking lot

- security review workflow variant
- optional PR summary and checkpoint automation
- event-retention pruning
- multi-project dashboard polish
