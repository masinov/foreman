# STATUS

## Current sprint

- Sprint: `sprint-07-codex-runner`
- Status: active
- Goal: execute shipped Codex roles through a native Foreman runner with
  persisted run metadata, session handling, and structured events

## Active branches

- `feat/claude-runner` — land the first native Claude Code runner, native
  orchestrator integration, and repo-memory rollover into the Codex runner
  sprint

## Completed this week

- identified the true product inputs for this repo:
  `docs/specs/engine-design-v3.md` and
  `docs/mockups/foreman-mockup-v6.html`
- rewrote the transplanted Apparatus docs into Foreman-specific project memory
- initialized current sprint and backlog docs for the first implementation work
- aligned the autonomous wrapper scripts with the Foreman repo layout and
  product references
- updated repo validation to match the current scaffold
- added gitignore coverage for `.foreman/`, `.codex/`, and `.claude/`
- bootstrapped `pyproject.toml`, the `foreman/` package, and a spec-aligned CLI
  shell with smoke tests for `--help`, `projects`, and `status`
- fixed the reviewed Codex supervisor so an approved slice now triggers merge
  finalization and continuation instead of terminating the run after one task
- implemented typed SQLite-backed models and persistence for projects, sprints,
  tasks, runs, and events
- added round-trip store tests plus `foreman projects --db ...` and
  `foreman status --db ...` inspection support
- shipped declarative `roles/*.toml` and `workflows/*.toml` defaults from the
  spec examples
- implemented TOML-compatible role and workflow loaders, prompt rendering, and
  transition validation
- added `foreman roles` and `foreman workflows` plus dedicated loader tests
- completed `sprint-01-foundation` and rolled repo memory forward to
  `sprint-02-orchestrator`
- implemented the first real orchestrator loop against persisted tasks, runs,
  and events
- added explicit built-ins for tests, merge, mark-done, and human-gate pause
  behavior
- added git execution helpers plus integration tests that drive one task
  through the shipped development workflow, including review denial, test
  failure carry-output loops, and fallback blocking
- completed `sprint-02-orchestrator` and rolled repo memory forward to
  `sprint-03-scaffold`
- implemented `foreman.scaffold` with generated `AGENTS.md` rendering,
  idempotent `.gitignore` updates, and minimal target-repo scaffold creation
- added `foreman init --db <path>` so the CLI can create or update persisted
  projects directly in SQLite
- added scaffold generation coverage plus store lookup by repo path for
  re-initialization behavior
- completed `sprint-03-scaffold` and rolled repo memory forward to
  `sprint-04-context-projection`
- implemented `foreman.context` so runtime `.foreman/context.md` and
  `.foreman/status.md` are rendered from persisted SQLite state
- added `_builtin:context_write` plus orchestrator-triggered runtime context
  refresh before agent steps and after task completion
- added context projection unit and orchestrator integration coverage,
  including gitignored runtime files in temporary repo fixtures
- completed `sprint-04-context-projection` and rolled repo memory forward to
  `sprint-05-human-gates`
- implemented `foreman approve --db <path>` and `foreman deny --db <path>`
  against paused human-gate tasks in SQLite
- added persisted human-decision runs plus `workflow.resumed` events for
  approval and denial history
- taught the orchestrator to resume from a persisted workflow step instead of
  always restarting from workflow entry
- added bootstrap deferred resume semantics so human-gate decisions can record
  the next step and carried output even before native runners land
- expanded orchestrator and CLI coverage for human-gate pause, approve, deny,
  immediate resume, and deferred resume behavior
- completed `sprint-05-human-gates` and rolled repo memory forward to
  `sprint-06-claude-runner`
- implemented shared native runner primitives, structured signal extraction,
  and the first Claude Code stream-json backend
- taught the orchestrator to execute shipped Claude-backed roles through the
  native runner path when no scripted executor is injected
- added runner coverage for event mapping, retry normalization, developer
  session reuse, and native orchestrator execution
- completed `sprint-06-claude-runner` and rolled repo memory forward to
  `sprint-07-codex-runner`
- implemented native Codex runner with JSON-RPC protocol support
- integrated CodexRunner into orchestrator default agent_runners
- added 10 Codex runner tests covering command building and event parsing
- completed `sprint-07-codex-runner`

## Current repo state

- The repository currently contains:
  - the product spec,
  - the UI mockup,
  - the initial `foreman` package scaffold and CLI shell,
  - a SQLite-backed store baseline with spec-shaped DDL and query helpers,
  - shipped default role and workflow definitions with loader validation,
  - a persisted orchestrator loop that can execute the shipped development
    workflow through agent and built-in steps,
  - a working `foreman init` path that scaffolds `AGENTS.md`, `docs/adr/`,
    `.foreman/`, and `.gitignore` updates in a target repo,
  - runtime `.foreman/context.md` and `.foreman/status.md` projection from
    SQLite before agent execution and after task completion,
  - persisted human-gate approval and denial commands with durable resume
    history and deferred-next-step support when no native runner is available,
  - the first native Claude Code runner with stream-json parsing, structured
    event mapping, infrastructure retries, and developer session reuse,
  - persisted project initialization and update behavior keyed by repo path,
  - smoke tests for the CLI bootstrap slice plus store, loader, and
    orchestrator, scaffold, and context projection coverage,
  - regression coverage for the reviewed Codex supervisor flow,
  - the Codex and Claude supervisor scripts,
  - repo-memory docs that define the next engineering slices.
- The temporary markdown sprint and status workflow is intentional bootstrap
  state. The eventual product should move operational state into SQLite as
  described in the spec.

## Ready next

1. add the first native Codex runner backend
2. expose project state through the monitoring CLI surfaces
3. define the first ADR now that runner session handling is an active runtime
   constraint
4. build the dashboard implementation aligned to the mockup

## Open risks

- `reviewed_codex.py` and `reviewed_claude.py` are bootstrap supervisors, not
  the Foreman product itself; their behavior should not accidentally become the
  long-term architecture.
- The package now has a real store, loader, orchestrator, project
  initialization path, human-gate resume commands, and a native Claude runner,
  but the Codex backend is still missing so Foreman does not yet satisfy the
  full dual-backend product commitment.
- The bootstrap CLI currently requires explicit `--db PATH` selection for
  project lifecycle commands because engine-instance configuration does not
  exist yet.
- The native Claude runner assumes a working `claude` executable in PATH and
  currently relies on runtime process errors rather than an explicit preflight
  health check.
- editable installs are now validated with
  `./venv/bin/pip install -e . --no-build-isolation`, so fresh environments
  still need the repo venv to include the packaging toolchain declared in
  `pyproject.toml`.
- Python 3.10 support currently relies on a local TOML compatibility shim and a
  pip-vendored fallback during `--no-deps` validation installs.
- The SQLite layer currently uses bootstrap DDL without a migration framework;
  schema evolution rules still need an ADR once later slices depend on them.
- The UI mockup is static; implementing it will require decisions about API
  boundaries and event streaming that are not yet captured in ADRs.

## Documented conflicts

- The shipped workflow TOML treats `_builtin:mark_done` as a terminal step with
  no outbound transition, while the orchestrator pseudocode in the spec blocks
  any missing transition. The current implementation treats a step that sets
  task status to `done` as successful workflow termination and records that
  nuance here until the spec text is clarified.
- The spec's CLI examples omit explicit database selection, while the bootstrap
  CLI currently requires `--db PATH` for `foreman init`, `foreman projects`,
  and `foreman status` because engine-level DB discovery has not been
  implemented yet.
- The spec expects `.foreman/status.md` to list open decisions, but the current
  SQLite schema has no structured decision records yet. The runtime projection
  currently emits an explicit placeholder until those records exist.
- The spec describes `foreman approve` and `foreman deny` as immediately
  resuming workflow execution. The current runtime now does that for
  Claude-backed steps, but it still persists a deferred next step when the
  resumed workflow needs a backend that Foreman cannot run yet.

## Open decisions

- whether the initial web surface should be delivered as static HTML plus JSON
  endpoints or as a richer app shell from the start
- how much of the current wrapper logic should survive once native Foreman
  runners exist
- whether project `default_model` should be validated against the selected
  agent backend instead of being passed through verbatim at runtime
