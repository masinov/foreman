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

- partially completed on `feat/context-projection-runtime`
- directed task selection, workflow transitions, loop limits, built-ins for
  tests, merge, mark-done, human-gate pause, and runtime context projection
  now exist
- human-gate resume commands remain

## Milestone 5: Claude and Codex runners

Goal: move beyond bootstrap wrappers into native runner support.

Target deliverables:

- agent runner protocol
- Claude Code backend
- Codex backend
- structured event capture
- infrastructure retry handling

## Milestone 6: Monitoring surfaces

Goal: expose Foreman state through CLI and a web dashboard.

Target deliverables:

- board and watch terminal views
- cost and history queries
- project, sprint, and task detail APIs
- web implementation aligned to `docs/mockups/foreman-mockup-v6.html`

## Near-term priorities

1. implement human-gate approve and deny commands against paused tasks
2. add the first native Claude Code or Codex runner backend
3. expose project state through the monitoring CLI surfaces
4. capture the first ADR once human-gate or runner semantics harden
