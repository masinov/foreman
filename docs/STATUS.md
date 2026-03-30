# STATUS

## Current sprint

- Sprint: `sprint-01-foundation`
- Status: active
- Goal: turn the repo from a transplanted scaffold into a clean starting point
  for building Foreman's first runnable backend slices

## Active branches

- `feat/cli-package-bootstrap` — land the first `foreman` package scaffold,
  CLI shell, and smoke tests

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

## Current repo state

- The repository currently contains:
  - the product spec,
  - the UI mockup,
  - the initial `foreman` package scaffold and CLI shell,
  - smoke tests for the CLI bootstrap slice,
  - regression coverage for the reviewed Codex supervisor flow,
  - the Codex and Claude supervisor scripts,
  - repo-memory docs that define the next engineering slices.
- The temporary markdown sprint and status workflow is intentional bootstrap
  state. The eventual product should move operational state into SQLite as
  described in the spec.

## Ready next

1. implement the first SQLite-backed models and store layer
2. load role and workflow definitions from TOML
3. add round-trip tests for project, sprint, task, run, and event persistence
4. extend CLI inspection commands to read real store data instead of bootstrap
   placeholders

## Open risks

- `reviewed_codex.py` and `reviewed_claude.py` are bootstrap supervisors, not
  the Foreman product itself; their behavior should not accidentally become the
  long-term architecture.
- The package is currently a CLI shell with placeholder backend modules; the
  store, role loader, workflow loader, and orchestrator are still unimplemented.
- editable installs are now validated with `./venv/bin/pip install -e . --no-build-isolation`,
  so fresh environments still need the repo venv to include the packaging toolchain
  declared in `pyproject.toml`.
- The UI mockup is static; implementing it will require decisions about API
  boundaries and event streaming that are not yet captured in ADRs.

## Open decisions

- whether the initial web surface should be delivered as static HTML plus JSON
  endpoints or as a richer app shell from the start
- how much of the current wrapper logic should survive once native Foreman
  runners exist
