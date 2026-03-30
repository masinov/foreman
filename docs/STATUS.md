# STATUS

## Current sprint

- Sprint: `sprint-03-scaffold`
- Status: active
- Goal: make `foreman init` create a spec-driven repo scaffold and persist the
  initialized project cleanly

## Active branches

- `feat/orchestrator-main-loop` — land the first persisted orchestrator loop,
  workflow built-ins, git execution helpers, and integration coverage for the
  shipped development workflow

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

## Current repo state

- The repository currently contains:
  - the product spec,
  - the UI mockup,
  - the initial `foreman` package scaffold and CLI shell,
  - a SQLite-backed store baseline with spec-shaped DDL and query helpers,
  - shipped default role and workflow definitions with loader validation,
  - a persisted orchestrator loop that can execute the shipped development
    workflow through agent and built-in steps,
  - smoke tests for the CLI bootstrap slice plus store, loader, and
    orchestrator coverage,
  - regression coverage for the reviewed Codex supervisor flow,
  - the Codex and Claude supervisor scripts,
  - repo-memory docs that define the next engineering slices.
- The temporary markdown sprint and status workflow is intentional bootstrap
  state. The eventual product should move operational state into SQLite as
  described in the spec.

## Ready next

1. implement `foreman init` so it scaffolds `AGENTS.md`, `docs/adr/`,
   `.foreman/`, and `.gitignore` updates in a target repo
2. persist initialized projects directly into the SQLite store from the CLI
3. project `.foreman/context.md` and `.foreman/status.md` from the store before
   workflow runs
4. define the first ADR once the scaffold or orchestrator runtime constraints
   stop being hypothetical

## Open risks

- `reviewed_codex.py` and `reviewed_claude.py` are bootstrap supervisors, not
  the Foreman product itself; their behavior should not accidentally become the
  long-term architecture.
- The package now has a real store, loader, and orchestrator layer, but
  project initialization, context projection, human-gate resume commands, and
  native runners are still unimplemented.
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

## Open decisions

- whether the initial web surface should be delivered as static HTML plus JSON
  endpoints or as a richer app shell from the start
- how much of the current wrapper logic should survive once native Foreman
  runners exist
