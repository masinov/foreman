# STATUS

## Current sprint

- Sprint: `sprint-01-foundation`
- Status: active
- Goal: turn the repo from a transplanted scaffold into a clean starting point
  for building Foreman's first runnable backend slices

## Active branches

- `chore/foreman-autonomy-bootstrap` — repurpose the repo memory scaffold and
  autonomous wrapper scripts for the actual Foreman project

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

## Current repo state

- No real Foreman package exists yet.
- The repository currently contains:
  - the product spec,
  - the UI mockup,
  - the Codex and Claude supervisor scripts,
  - repo-memory docs that define the next engineering slices.
- The temporary markdown sprint and status workflow is intentional bootstrap
  state. The eventual product should move operational state into SQLite as
  described in the spec.

## Ready next

1. bootstrap `pyproject.toml`, the `foreman/` package, and a CLI entrypoint
2. implement the first SQLite-backed models and store layer
3. load role and workflow definitions from TOML
4. add smoke tests for project initialization and CLI inspection commands

## Open risks

- `reviewed_codex.py` and `reviewed_claude.py` are bootstrap supervisors, not
  the Foreman product itself; their behavior should not accidentally become the
  long-term architecture.
- The repo still has no executable package or runtime test suite beyond
  scaffold validation.
- The UI mockup is static; implementing it will require decisions about API
  boundaries and event streaming that are not yet captured in ADRs.

## Open decisions

- whether the first implementation slice should land API and CLI in one package
  or start CLI-only
- whether the initial web surface should be delivered as static HTML plus JSON
  endpoints or as a richer app shell from the start
- how much of the current wrapper logic should survive once native Foreman
  runners exist
