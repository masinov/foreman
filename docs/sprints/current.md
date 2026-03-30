# Current Sprint

- Sprint: `sprint-03-scaffold`
- Status: active
- Goal: create a spec-driven `foreman init` path that scaffolds a target repo
  and persists the initialized project cleanly
- Primary references:
  - `docs/specs/engine-design-v3.md`
  - `docs/mockups/foreman-mockup-v6.html`

## Included tasks

1. `[todo]` Implement repo scaffold generation for `foreman init`
   Deliverable: Foreman can create `AGENTS.md`, `docs/adr/`, `.foreman/`, and
   the necessary `.gitignore` updates in a target repository.

2. `[todo]` Persist initialized projects and workflow settings from the CLI
   Deliverable: `foreman init` writes the project record into SQLite so later
   orchestrator runs can start from the generated scaffold instead of ad hoc
   seed scripts.

3. `[todo]` Add integration coverage for scaffold generation and initialization
   Deliverable: tests prove the scaffold files, `.gitignore`, and persisted
   project state are created without touching tool-managed runtime paths.

## Excluded from this sprint

- context projection into `.foreman/` during orchestrator runs
- native Claude Code and Codex runner implementations
- human-gate approve and deny CLI commands
- dashboard and monitoring CLI surfaces

## Acceptance criteria

- `foreman init` can create the minimal repo scaffold described by the spec
- initialized projects are persisted into SQLite with enough data to support
  later orchestrator runs
- generated files align to the repo instructions model from `AGENTS.md` and do
  not treat `.foreman/` as committed project state
- docs and validation remain good enough for a fresh autonomous agent to pick
  the next slice without extra human context

## Known risks

- the scaffold slice has to bridge the bootstrap repo-memory workflow with the
  product's eventual SQLite-first source of truth without baking markdown
  planning conventions into generated projects
- generated `AGENTS.md` content needs to stay tightly aligned to the spec so it
  does not drift from the real product behavior before runner slices land

## Demo checklist

- show `foreman init` scaffolding a target repository
- show the initialized project persisted in SQLite
- show repo validation passing after the scaffold slice lands
