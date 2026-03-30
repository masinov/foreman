# ROADMAP

## Principle

Roadmap items should preserve the product identity defined in the Foreman spec:

- SQLite-backed structured state,
- declarative roles and workflows,
- spec-driven project initialization,
- explicit sprints, tasks, runs, and events,
- reviewable autonomous execution,
- repo-local context projection under `.foreman/`,
- a dashboard aligned with the mockup.

## Milestone 0: Repo reset and bootstrap

Goal: make the transplanted scaffold belong to Foreman.

Deliverables:

- Foreman-specific `AGENTS.md`
- current sprint and backlog docs
- architecture baseline and roadmap reset
- wrapper-script alignment
- repo validation that matches the actual project inputs

Status:

- completed on `chore/foreman-autonomy-bootstrap`

## Milestone 1: Core package and CLI shell

Goal: create the first runnable Python package and CLI entrypoint.

Target deliverables:

- `pyproject.toml`
- `foreman/` package scaffold
- `foreman.cli` entrypoint
- `foreman init`, `foreman projects`, and `foreman status` command stubs
- smoke tests for command wiring

Status:

- completed on `feat/cli-package-bootstrap`

## Milestone 2: Structured store and models

Goal: land the SQLite data model described in the spec.

Target deliverables:

- dataclasses or typed models for projects, sprints, tasks, runs, and events
- SQLite CRUD layer
- migration or bootstrap DDL
- tests for round-trips and query helpers

Status:

- completed on `feat/sqlite-store-baseline`

## Milestone 3: Roles, workflows, and scaffold generation

Goal: make projects configurable through TOML plus generated repo artifacts.

Target deliverables:

- role loader
- workflow loader
- prompt rendering
- scaffold generator for `AGENTS.md`, `docs/adr/`, and `.foreman/`
- `.gitignore` update helpers

Status:

- completed on `feat/init-scaffold-generator`
- role and workflow loading, prompt rendering, scaffold generation, and
  `.gitignore` update helpers are now in place

## Milestone 4: Orchestrator and built-ins

Goal: execute one task through a workflow with durable state transitions.

Target deliverables:

- task selection logic
- step transitions and loop limits
- built-ins for tests, merge, mark-done, and human gates
- context projection into `.foreman/context.md` and `.foreman/status.md`

Status:

- completed on `feat/human-gate-resume`
- directed task selection, workflow transitions, loop limits, built-ins for
  tests, merge, mark-done, human-gate pause, human-gate resume, and runtime
  context projection now exist
- bootstrap CLI approvals can defer agent-backed next steps until the native
  runner milestone lands

## Milestone 5: Claude and Codex runners

Goal: move beyond bootstrap wrappers into native runner support.

Target deliverables:

- agent runner protocol
- Claude Code backend
- Codex backend
- structured event capture
- infrastructure retry handling

Status:

- completed on `feat/codex-runner`
- the shared runner protocol, Claude Code backend, Codex backend, retry
  normalization, and orchestrator integration now exist
- native human-gate resume now proceeds immediately when the next backend and
  repo are available, while still persisting deferred state when they are not

## Milestone 6: Monitoring surfaces

Goal: expose Foreman state through CLI and a web dashboard.

Target deliverables:

- board and watch terminal views
- cost and history queries
- project, sprint, and task detail APIs
- web implementation aligned to `docs/mockups/foreman-mockup-v6.html`

Status:

- completed across `feat/monitoring-cli`, `feat/dashboard-shell`,
  `chore/sprint-11-multi-project-polish`, and
  `feat/dashboard-approve-deny-integration`
- the terminal monitoring CLI now exposes board, history, cost, and bounded
  watch snapshots directly from SQLite
- the dashboard now exposes project overview, sprint board, task detail,
  direct SQLite-backed JSON APIs, human message input, activity filtering,
  project switching, and approve or deny workflow resume actions
- live transport is still pending; the dashboard currently uses polling
  snapshots rather than a dedicated stream

## Milestone 7: Runner contract ADR baseline

Goal: accept the first explicit runtime contract for native runner sessions,
approval boundaries, and backend telemetry.

Target deliverables:

- accepted ADR for session scope and persistence
- accepted ADR for workflow-versus-runner approval handling
- accepted ADR for backend telemetry and unsupported-backend behavior

Status:

- completed on `docs/runner-session-backend-adr`
- `docs/adr/ADR-0001-runner-session-backend-contract.md` is now the active
  runner contract baseline
- cross-invocation persistent-session reload remains documented follow-up work

## Milestone 8: Session continuity

Goal: close the documented session-reuse gap from ADR-0001.

Target deliverables:

- reload last compatible native session from SQLite on fresh orchestrator
  invocations
- preserve role-level session policy across Claude Code and Codex
- add regression coverage for cross-invocation reuse and human-gate resume

Status:

- current sprint is `sprint-13-persistent-session-reload`
- no implementation has landed yet; the gap is documented and actively queued

## Near-term priorities

1. reload persisted same-role native sessions from SQLite on fresh
   orchestrator invocations
2. decide how the future dashboard activity feed should relate to the current
   polling-based `foreman watch` semantics
3. add the security review workflow variant after the session continuity work
   is in place
